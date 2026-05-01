import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func

from app.models import (
    BudgetItem,
    BudgetLine,
    BudgetScenario,
    CashAccount,
    CashCalendarItem,
    CashTransaction,
    Customer,
    FinanceArticle,
    FixedAsset,
    IndirectExpense,
    InventoryBatch,
    Loan,
    Payment,
    PaymentRequest,
    PlanFactDeviation,
    PurchaseOrder,
    SalesOrder,
    SalesOrderItem,
    Supplier,
    db,
)


CASH_GROUP_LABELS = {
    "operational": "Операционная деятельность",
    "investment": "Инвестиционная деятельность",
    "financial": "Финансовая деятельность",
}


def get_period_bounds(period):
    try:
        start_date = datetime.strptime(period, "%Y-%m")
    except ValueError:
        start_date = datetime.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    end_date = (start_date + timedelta(days=32)).replace(day=1)
    return start_date, end_date


def period_months(year):
    return [f"{year}-{month:02d}" for month in range(1, 13)]


def get_default_cash_account(create=False):
    account = (
        CashAccount.query.filter_by(is_active=True)
        .order_by(CashAccount.account_type.asc(), CashAccount.id.asc())
        .first()
    )
    if account is None and create:
        account = CashAccount(
            name="Демо расчетный счет",
            account_type="demo",
            bank_name="Учебный банк",
            account_number="DEMO-0001",
            currency="RUB",
            opening_balance=0,
            opening_date=datetime(2025, 1, 1),
            is_active=True,
        )
        db.session.add(account)
        db.session.flush()
    return account


def get_finance_article(name, cash_flow_group="operational", pnl_group="other", create=False):
    if not name:
        return None
    article = FinanceArticle.query.filter_by(name=name).first()
    if article is None and create:
        article = FinanceArticle(
            name=name,
            report_type="both",
            cash_flow_group=cash_flow_group,
            pnl_group=pnl_group,
            is_active=True,
        )
        db.session.add(article)
        db.session.flush()
    return article


def guess_finance_article(direction, purpose=""):
    text = (purpose or "").lower()
    if direction == "incoming":
        return get_finance_article("Продажи", "operational", "revenue", create=True)
    if any(word in text for word in ["оборуд", "станок", "актив"]):
        return get_finance_article("Оборудование", "investment", "other", create=True)
    if any(word in text for word in ["кредит", "займ", "процент"]):
        return get_finance_article("Кредит", "financial", "other", create=True)
    if any(word in text for word in ["аренд"]):
        return get_finance_article("Аренда", "operational", "opex", create=True)
    if any(word in text for word in ["зарп", "фот", "оклад"]):
        return get_finance_article("Зарплата", "operational", "opex", create=True)
    if any(word in text for word in ["налог", "усн"]):
        return get_finance_article("Налоги", "operational", "tax", create=True)
    if any(word in text for word in ["закуп", "постав", "материал", "сырье"]):
        return get_finance_article("Закупки", "operational", "cogs", create=True)
    return get_finance_article("Прочие расходы", "operational", "other", create=True)


def calculate_cash_balance(as_of):
    if not isinstance(as_of, datetime):
        as_of = datetime.combine(as_of, datetime.max.time())

    balance = 0.0
    for account in CashAccount.query.filter(
        CashAccount.is_active.is_(True),
        CashAccount.opening_date <= as_of,
    ).all():
        balance += float(account.opening_balance or 0)

    transactions = CashTransaction.query.filter(
        CashTransaction.status == "executed",
        CashTransaction.date <= as_of,
    ).all()
    for tx in transactions:
        balance += tx.signed_amount()
    return balance


def _calculate_opening_balance(start_date):
    balance = 0.0
    for account in CashAccount.query.filter(
        CashAccount.is_active.is_(True),
        CashAccount.opening_date <= start_date,
    ).all():
        balance += float(account.opening_balance or 0)

    transactions = CashTransaction.query.filter(
        CashTransaction.status == "executed",
        CashTransaction.date < start_date,
    ).all()
    for tx in transactions:
        balance += tx.signed_amount()
    return balance


def calculate_cogs_fifo(start_date, end_date, strategy="fifo"):
    cogs = 0.0
    batch_cache = {}

    sales_items = (
        SalesOrderItem.query.join(SalesOrder)
        .filter(
            SalesOrder.order_date >= start_date,
            SalesOrder.order_date < end_date,
            SalesOrder.status == "completed",
        )
        .all()
    )

    for item in sales_items:
        if item.cost_price and item.cost_price > 0:
            cogs += float(item.quantity * item.cost_price)
            continue

        product_id = item.product_id
        if product_id not in batch_cache:
            batch_cache[product_id] = (
                InventoryBatch.query.filter_by(product_id=product_id)
                .order_by(InventoryBatch.received_date.asc(), InventoryBatch.id.asc())
                .all()
            )

        remaining = item.quantity
        for batch in batch_cache[product_id]:
            available = batch.available_quantity()
            if available <= 0:
                continue
            take = min(remaining, available)
            freight = batch.transport_cost / batch.quantity if batch.quantity else 0
            cogs += take * (batch.unit_cost + freight)
            remaining -= take
            if remaining <= 0:
                break

        if remaining > 0:
            cogs += remaining * float(item.cost_price or 0)

    return cogs


def calculate_pnl(period):
    start_date, end_date = get_period_bounds(period)
    revenue = (
        db.session.query(func.sum(SalesOrder.total_amount))
        .filter(
            SalesOrder.order_date >= start_date,
            SalesOrder.order_date < end_date,
            SalesOrder.status == "completed",
        )
        .scalar()
        or 0
    )
    revenue = float(revenue)
    cogs = float(calculate_cogs_fifo(start_date, end_date))
    opex = float(
        db.session.query(func.sum(IndirectExpense.amount))
        .filter(IndirectExpense.period == period)
        .scalar()
        or 0
    )
    tax = revenue * 0.06
    gross_profit = revenue - cogs
    operating_profit = gross_profit - opex
    net_profit = operating_profit - tax
    return {
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "operating_expenses": opex,
        "operating_profit": operating_profit,
        "usn_tax": tax,
        "net_profit": net_profit,
        "gross_margin_pct": (gross_profit / revenue * 100) if revenue else 0,
        "operating_margin_pct": (operating_profit / revenue * 100) if revenue else 0,
        "net_margin_pct": (net_profit / revenue * 100) if revenue else 0,
        "method_note": (
            "P&L считается по начислению: выручка берется из выполненных заказов "
            "по дате заказа, себестоимость - из cost_price или FIFO, налог - учебное "
            "допущение УСН 6% от выручки."
        ),
    }


def _tx_to_movement(tx):
    group = tx.article.cash_flow_group if tx.article else "operational"
    return {
        "date": tx.date,
        "amount": abs(float(tx.amount or 0)),
        "direction": tx.direction,
        "article": tx.article.name if tx.article else "Без статьи",
        "article_id": tx.article_id,
        "group": group or "operational",
        "kind": "actual" if tx.status == "executed" else "planned",
        "source": tx.source or "manual",
        "status": tx.status,
        "counterparty": tx.counterparty
        or (tx.customer.name if tx.customer else None)
        or (tx.supplier.name if tx.supplier else None)
        or "",
        "description": tx.description or "",
        "external_ref": tx.external_ref,
    }


def _has_calendar_item_for_po(order, scheduled_date):
    return CashCalendarItem.query.filter_by(
        date=scheduled_date,
        amount=order.total_amount,
        supplier_id=order.supplier_id,
        direction="outgoing",
    ).first() is not None


def collect_cash_movements(start_date, end_date, include_adapters=True):
    movements = []
    transactions = CashTransaction.query.filter(
        CashTransaction.date >= start_date,
        CashTransaction.date < end_date,
        CashTransaction.status != "cancelled",
    ).all()
    external_refs = {
        ref
        for (ref,) in CashTransaction.query.with_entities(CashTransaction.external_ref)
        .filter(CashTransaction.external_ref.isnot(None))
        .all()
    }
    movements.extend(_tx_to_movement(tx) for tx in transactions)

    if not include_adapters:
        return movements

    sales_article = get_finance_article("Продажи", "operational", "revenue", create=True)
    purchase_article = get_finance_article("Закупки", "operational", "cogs", create=True)

    for payment in Payment.query.filter(
        Payment.payment_date >= start_date,
        Payment.payment_date < end_date,
        Payment.status == "completed",
    ).all():
        ref = f"payment:{payment.id}"
        if ref in external_refs:
            continue
        movements.append(
            {
                "date": payment.payment_date,
                "amount": float(payment.amount or 0),
                "direction": "incoming",
                "article": sales_article.name,
                "article_id": sales_article.id,
                "group": "operational",
                "kind": "actual",
                "source": "sales",
                "status": "executed",
                "counterparty": payment.sales_order.customer.name if payment.sales_order else "",
                "description": f"Оплата заказа {payment.sales_order.order_number}",
                "external_ref": ref,
            }
        )

    for order in PurchaseOrder.query.filter(
        PurchaseOrder.order_date >= start_date - timedelta(days=60),
        PurchaseOrder.order_date < end_date,
    ).all():
        if order.is_paid:
            ref = f"purchase_order:{order.id}"
            if ref in external_refs:
                continue
            movements.append(
                {
                    "date": order.order_date,
                    "amount": float(order.total_amount or 0),
                    "direction": "outgoing",
                    "article": purchase_article.name,
                    "article_id": purchase_article.id,
                    "group": "operational",
                    "kind": "actual",
                    "source": "purchase",
                    "status": "executed",
                    "counterparty": order.supplier.name if order.supplier else "",
                    "description": f"Оплата закупки {order.order_number}",
                    "external_ref": ref,
                }
            )
            continue

        scheduled_date = order.order_date + timedelta(days=30)
        if scheduled_date < start_date or scheduled_date >= end_date:
            continue
        if _has_calendar_item_for_po(order, scheduled_date):
            continue
        movements.append(
            {
                "date": scheduled_date,
                "amount": float(order.total_amount or 0),
                "direction": "outgoing",
                "article": purchase_article.name,
                "article_id": purchase_article.id,
                "group": "operational",
                "kind": "planned",
                "source": "purchase",
                "status": "planned",
                "counterparty": order.supplier.name if order.supplier else "",
                "description": f"Плановая оплата закупки {order.order_number}",
                "external_ref": f"purchase_order_plan:{order.id}",
            }
        )

    for item in CashCalendarItem.query.filter(
        CashCalendarItem.date >= start_date,
        CashCalendarItem.date < end_date,
    ).all():
        movements.append(
            {
                "date": item.date,
                "amount": float(item.amount or 0) * float(item.probability or 1),
                "direction": item.direction,
                "article": CASH_GROUP_LABELS.get(item.cash_type, "Платежный календарь"),
                "article_id": None,
                "group": item.cash_type or "operational",
                "kind": "actual" if item.status == "executed" else "planned",
                "source": "calendar",
                "status": item.status,
                "counterparty": "",
                "description": item.comment or "",
                "external_ref": f"calendar:{item.id}",
            }
        )

    for request_item in PaymentRequest.query.filter(
        PaymentRequest.due_date >= start_date,
        PaymentRequest.due_date < end_date,
        PaymentRequest.status.in_(["pending", "approved"]),
    ).all():
        article = request_item.article
        movements.append(
            {
                "date": request_item.due_date,
                "amount": float(request_item.amount or 0),
                "direction": request_item.direction,
                "article": article.name if article else "Платежные заявки",
                "article_id": request_item.article_id,
                "group": article.cash_flow_group if article else "operational",
                "kind": "planned",
                "source": "payment_request",
                "status": request_item.status,
                "counterparty": (
                    request_item.supplier.name
                    if request_item.supplier
                    else request_item.customer.name
                    if request_item.customer
                    else ""
                ),
                "description": request_item.comment or "",
                "external_ref": f"payment_request_plan:{request_item.id}",
            }
        )

    return movements


def build_cash_flow_report(period):
    start_date, end_date = get_period_bounds(period)
    opening_balance = _calculate_opening_balance(start_date)
    movements = collect_cash_movements(start_date, end_date)

    daily = defaultdict(
        lambda: {
            "actual_incoming": 0.0,
            "actual_outgoing": 0.0,
            "planned_incoming": 0.0,
            "planned_outgoing": 0.0,
        }
    )
    groups = defaultdict(lambda: {"incoming": 0.0, "outgoing": 0.0, "net": 0.0})

    for movement in movements:
        day_key = movement["date"].date()
        direction_key = "incoming" if movement["direction"] == "incoming" else "outgoing"
        kind_key = "actual" if movement["kind"] == "actual" else "planned"
        daily[day_key][f"{kind_key}_{direction_key}"] += movement["amount"]
        if kind_key == "actual":
            group = movement["group"] or "operational"
            if direction_key == "incoming":
                groups[group]["incoming"] += movement["amount"]
                groups[group]["net"] += movement["amount"]
            else:
                groups[group]["outgoing"] += movement["amount"]
                groups[group]["net"] -= movement["amount"]

    rows = []
    running_balance = opening_balance
    projected_balance = opening_balance
    first_gap_date = None
    day = start_date
    while day < end_date:
        day_key = day.date()
        values = daily[day_key]
        fact_net = values["actual_incoming"] - values["actual_outgoing"]
        plan_net = values["planned_incoming"] - values["planned_outgoing"]
        running_balance += fact_net
        projected_balance += fact_net + plan_net
        if first_gap_date is None and projected_balance < 0:
            first_gap_date = day_key
        rows.append(
            {
                "date": day_key,
                "incoming": values["actual_incoming"],
                "outgoing_paid": values["actual_outgoing"],
                "outgoing_scheduled": values["planned_outgoing"],
                "planned_incoming": values["planned_incoming"],
                "actual_incoming": values["actual_incoming"],
                "actual_outgoing": values["actual_outgoing"],
                "planned_outgoing": values["planned_outgoing"],
                "net_actual": fact_net,
                "net_planned": plan_net,
                "projected_gap": fact_net + plan_net,
                "running_balance": running_balance,
                "projected_balance": projected_balance,
            }
        )
        day += timedelta(days=1)

    active_rows = [
        row
        for row in rows
        if row["actual_incoming"]
        or row["actual_outgoing"]
        or row["planned_incoming"]
        or row["planned_outgoing"]
    ]

    group_rows = []
    for group_key in ["operational", "investment", "financial"]:
        values = groups[group_key]
        group_rows.append(
            {
                "key": group_key,
                "label": CASH_GROUP_LABELS[group_key],
                "incoming": values["incoming"],
                "outgoing": values["outgoing"],
                "net": values["net"],
            }
        )

    return {
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "opening_balance": opening_balance,
        "closing_balance": running_balance,
        "projected_closing_balance": projected_balance,
        "first_gap_date": first_gap_date,
        "rows": rows,
        "active_rows": active_rows,
        "group_rows": group_rows,
        "total_incoming": sum(row["actual_incoming"] for row in rows),
        "total_outgoing_paid": sum(row["actual_outgoing"] for row in rows),
        "total_outgoing_scheduled": sum(row["planned_outgoing"] for row in rows),
        "total_planned_incoming": sum(row["planned_incoming"] for row in rows),
        "method_note": "Cash Flow и БДДС считаются по оплатам и движению денег.",
    }


def build_cash_calendar_report(start_date, days=30):
    if not isinstance(start_date, datetime):
        start_date = datetime.combine(start_date, datetime.min.time())
    end_date = start_date + timedelta(days=days)
    period = start_date.strftime("%Y-%m")
    report = build_cash_flow_report(period)
    rows = [
        row
        for row in report["rows"]
        if start_date.date() <= row["date"] < end_date.date()
    ]
    first_gap_date = next(
        (row["date"] for row in rows if row["projected_balance"] < 0),
        None,
    )
    return {
        "rows": rows,
        "ending_balance": rows[-1]["projected_balance"] if rows else report["projected_closing_balance"],
        "critical_dates": [row["date"] for row in rows if row["projected_balance"] < 0],
        "first_gap_date": first_gap_date,
    }


def calculate_management_balance(snapshot_date):
    if not isinstance(snapshot_date, datetime):
        snapshot_date = datetime.combine(snapshot_date, datetime.max.time())
    else:
        snapshot_date = datetime.combine(snapshot_date.date(), datetime.max.time())

    cash_amount = calculate_cash_balance(snapshot_date)
    inventory_value = sum(
        batch.available_quantity() * batch.unit_cost
        for batch in InventoryBatch.query.filter(InventoryBatch.received_date <= snapshot_date).all()
    )

    receivables = 0.0
    for order in SalesOrder.query.filter(
        SalesOrder.order_date <= snapshot_date,
        SalesOrder.status == "completed",
    ).all():
        paid = sum(
            payment.amount
            for payment in order.payments
            if payment.status == "completed" and payment.payment_date <= snapshot_date
        )
        receivables += max(0.0, float(order.total_amount or 0) - float(paid or 0))

    fixed_assets = sum(
        asset.carrying_amount
        for asset in FixedAsset.query.filter(
            FixedAsset.is_active.is_(True),
            FixedAsset.purchase_date <= snapshot_date,
        ).all()
    )

    payables = sum(
        float(order.total_amount or 0)
        for order in PurchaseOrder.query.filter(
            PurchaseOrder.order_date <= snapshot_date,
            PurchaseOrder.is_paid.is_(False),
        ).all()
    )

    loans = sum(
        float(loan.outstanding_amount or 0)
        for loan in Loan.query.filter(
            Loan.is_active.is_(True),
            Loan.start_date <= snapshot_date,
        ).all()
    )

    assets = [
        {"name": "Деньги", "amount": cash_amount},
        {"name": "Дебиторская задолженность", "amount": receivables},
        {"name": "Запасы", "amount": inventory_value},
        {"name": "Основные средства", "amount": fixed_assets},
    ]
    liabilities = [
        {"name": "Кредиторская задолженность", "amount": payables},
        {"name": "Займы и кредиты", "amount": loans},
    ]
    total_assets = sum(row["amount"] for row in assets)
    total_liabilities = sum(row["amount"] for row in liabilities)
    equity = total_assets - total_liabilities

    for row in assets:
        row["pct"] = (row["amount"] / total_assets * 100) if total_assets else 0
    for row in liabilities:
        row["pct"] = (row["amount"] / total_liabilities * 100) if total_liabilities else 0

    return {
        "snapshot_date": snapshot_date.date(),
        "assets_structure": assets,
        "liabilities_structure": liabilities,
        "inventory_value": inventory_value,
        "cash_amount": cash_amount,
        "receivables": receivables,
        "fixed_assets": fixed_assets,
        "payables": payables,
        "loans": loans,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "equity": equity,
        "check_equal": abs(total_assets - total_liabilities - equity) < 1e-2,
        "method_note": "Упрощенная управленческая методика для учебного проекта.",
    }


def _actual_cash_by_article(start_date, end_date):
    data = defaultdict(float)
    for movement in collect_cash_movements(start_date, end_date):
        if movement["kind"] != "actual":
            continue
        amount = movement["amount"]
        if movement["direction"] == "outgoing":
            amount = -amount
        data[movement["article"]] += amount
    return data


def build_budget_report(year=None, scenario_id=None):
    year = int(year or datetime.now().year)
    scenarios = (
        BudgetScenario.query.filter_by(year=year)
        .order_by(BudgetScenario.status.asc(), BudgetScenario.name.asc(), BudgetScenario.version.desc())
        .all()
    )
    selected = None
    if scenario_id:
        selected = BudgetScenario.query.get(scenario_id)
    if selected is None:
        selected = next((item for item in scenarios if item.status == "approved"), None)
    if selected is None and scenarios:
        selected = scenarios[0]

    months = period_months(year)
    lines = []
    if selected:
        lines = BudgetLine.query.filter_by(scenario_id=selected.id).all()

    matrix = defaultdict(lambda: {month: 0.0 for month in months})
    for line in lines:
        category = line.article.name if line.article else line.category or "Без статьи"
        if line.period in months:
            matrix[category][line.period] += float(line.amount or 0)

    if not matrix:
        for item in BudgetItem.query.filter(BudgetItem.period.like(f"{year}-%")).all():
            matrix[item.category][item.period] += float(item.planned_amount or 0)

    totals_by_month = {month: 0.0 for month in months}
    for category, values in matrix.items():
        for month in months:
            totals_by_month[month] += values[month]

    selected_period = datetime.now().strftime("%Y-%m")
    start_date, end_date = get_period_bounds(selected_period)
    actuals = _actual_cash_by_article(start_date, end_date)
    plan_fact_rows = []
    for category, month_values in sorted(matrix.items()):
        planned = month_values.get(selected_period, 0.0)
        actual = abs(actuals.get(category, 0.0))
        variance = actual - planned
        variance_pct = (variance / planned * 100) if planned else 0
        severity = "danger" if abs(variance_pct) >= 20 else "warning" if abs(variance_pct) >= 10 else "normal"
        plan_fact_rows.append(
            {
                "category": category,
                "planned": planned,
                "actual": actual,
                "variance": variance,
                "variance_pct": variance_pct,
                "severity": severity,
            }
        )

    return {
        "year": year,
        "months": months,
        "scenarios": scenarios,
        "selected_scenario": selected,
        "matrix": dict(matrix),
        "totals_by_month": totals_by_month,
        "plan_fact_rows": plan_fact_rows,
        "selected_period": selected_period,
    }


def build_plan_fact_report(period):
    start_date, end_date = get_period_bounds(period)
    scenario = (
        BudgetScenario.query.filter_by(year=start_date.year, status="approved")
        .order_by(BudgetScenario.version.desc())
        .first()
    )
    planned_by_category = defaultdict(float)
    if scenario:
        for line in BudgetLine.query.filter_by(scenario_id=scenario.id, period=period).all():
            category = line.article.name if line.article else line.category or "Без статьи"
            planned_by_category[category] += float(line.amount or 0)
    else:
        for item in BudgetItem.query.filter_by(period=period).all():
            planned_by_category[item.category] += float(item.planned_amount or 0)

    actuals = _actual_cash_by_article(start_date, end_date)
    categories = sorted(set(planned_by_category) | set(actuals))
    analysis = []
    for category in categories:
        planned = planned_by_category.get(category, 0.0)
        actual = abs(actuals.get(category, 0.0))
        variance = actual - planned
        variance_pct = (variance / planned * 100) if planned else 0
        severity = "danger" if abs(variance_pct) >= 20 else "warning" if abs(variance_pct) >= 10 else "normal"
        analysis.append(
            {
                "category": category,
                "type": "mixed",
                "planned": planned,
                "actual": actual,
                "variance": variance,
                "variance_pct": variance_pct,
                "flexed": planned,
                "severity": severity,
            }
        )

    deviations = (
        PlanFactDeviation.query.filter_by(period=period)
        .order_by(PlanFactDeviation.created_at.desc())
        .all()
    )
    total_planned = sum(item["planned"] for item in analysis)
    total_actual = sum(item["actual"] for item in analysis)
    return {
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "scenario": scenario,
        "analysis": analysis,
        "deviations": deviations,
        "deviations_alpha": [
            {"category": item["category"], "variance_pct": item["variance_pct"]}
            for item in analysis
            if abs(item["variance_pct"]) >= 20
        ],
        "total_planned": total_planned,
        "total_actual": total_actual,
        "total_variance": total_actual - total_planned,
        "cash_gap": build_cash_flow_report(period)["projected_closing_balance"],
    }


def build_dashboard(period):
    pnl = calculate_pnl(period)
    balance = calculate_management_balance(pnl["end_date"] - timedelta(days=1))
    cash_flow = build_cash_flow_report(period)
    budget = build_plan_fact_report(period)
    budget_plan = budget["total_planned"]
    budget_actual = budget["total_actual"]
    budget_variance_pct = ((budget_actual - budget_plan) / budget_plan * 100) if budget_plan else 0
    equity = balance["equity"]
    roe = (pnl["net_profit"] * 12 / equity * 100) if equity else 0
    fixed_costs = pnl["operating_expenses"]
    breakeven = (
        fixed_costs / (pnl["gross_profit"] / pnl["revenue"])
        if pnl["revenue"] and pnl["gross_profit"] > 0
        else 0
    )
    strength_buffer = ((pnl["revenue"] - breakeven) / pnl["revenue"] * 100) if pnl["revenue"] else 0
    return {
        **pnl,
        "cash_balance": cash_flow["closing_balance"],
        "cash_gap_date": cash_flow["first_gap_date"],
        "receivables": balance["receivables"],
        "payables": balance["payables"],
        "assets": balance["total_assets"],
        "liabilities": balance["total_liabilities"],
        "equity": equity,
        "inventory_value": balance["inventory_value"],
        "budget_variance_pct": budget_variance_pct,
        "budget_variance": budget_actual - budget_plan,
        "roe": roe,
        "breakeven": breakeven,
        "strength_buffer": strength_buffer,
    }


def _parse_demo_date(value):
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return datetime.now()


def _demo_bank_rows():
    return [
        {
            "date": "2026-04-03",
            "account": "Расчетный счет",
            "amount": "145000",
            "direction": "incoming",
            "counterparty": "ООО Северный офис",
            "purpose": "Оплата мебели по договору DEMO-01",
            "external_ref": "bank-demo-2026-04-03-001",
        },
        {
            "date": "2026-04-06",
            "account": "Расчетный счет",
            "amount": "82000",
            "direction": "outgoing",
            "counterparty": "Бизнес-центр",
            "purpose": "Аренда шоурума",
            "external_ref": "bank-demo-2026-04-06-002",
        },
        {
            "date": "2026-04-15",
            "account": "Расчетный счет",
            "amount": "42000",
            "direction": "outgoing",
            "counterparty": "ИФНС demo",
            "purpose": "УСН 6% учебное демо",
            "external_ref": "bank-demo-2026-04-15-003",
        },
    ]


def import_bank_demo(file_storage=None):
    rows = []
    if file_storage and getattr(file_storage, "filename", ""):
        raw = file_storage.stream.read()
        text = raw.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        rows = _demo_bank_rows()

    imported = 0
    skipped = 0
    for row in rows:
        external_ref = (row.get("external_ref") or "").strip()
        if not external_ref:
            external_ref = "|".join(
                [
                    row.get("date", ""),
                    row.get("account", ""),
                    row.get("amount", ""),
                    row.get("direction", ""),
                    row.get("counterparty", ""),
                ]
            )
        if CashTransaction.query.filter_by(external_ref=external_ref).first():
            skipped += 1
            continue

        date = _parse_demo_date(row.get("date"))
        account_name = (row.get("account") or "Расчетный счет").strip()
        account = CashAccount.query.filter_by(name=account_name).first()
        if account is None:
            account = CashAccount(
                name=account_name,
                account_type="demo",
                bank_name="Demo bank import",
                currency="RUB",
                opening_balance=0,
                opening_date=date,
                is_active=True,
            )
            db.session.add(account)
            db.session.flush()

        amount = float(str(row.get("amount") or "0").replace(" ", "").replace(",", "."))
        direction = (row.get("direction") or "").strip().lower()
        if not direction:
            direction = "incoming" if amount >= 0 else "outgoing"
        amount = abs(amount)
        purpose = row.get("purpose") or row.get("description") or ""
        article = guess_finance_article(direction, purpose)
        db.session.add(
            CashTransaction(
                account_id=account.id,
                date=date,
                amount=amount,
                direction=direction,
                article_id=article.id if article else None,
                counterparty=(row.get("counterparty") or "").strip(),
                source="demo_bank",
                status="executed",
                description=purpose,
                external_ref=external_ref,
            )
        )
        imported += 1

    db.session.commit()
    return {"imported": imported, "skipped": skipped}


def import_1c_demo(period=None):
    period = period or datetime.now().strftime("%Y-%m")
    start_date, end_date = get_period_bounds(period)
    account = get_default_cash_account(create=True)
    sales_article = get_finance_article("Продажи", "operational", "revenue", create=True)
    purchase_article = get_finance_article("Закупки", "operational", "cogs", create=True)

    rows = []
    for order in SalesOrder.query.filter(
        SalesOrder.order_date >= start_date,
        SalesOrder.order_date < end_date,
        SalesOrder.status == "completed",
    ).limit(5):
        rows.append(
            {
                "date": order.order_date,
                "amount": order.total_amount,
                "direction": "incoming",
                "article": sales_article,
                "counterparty": order.customer.name if order.customer else "",
                "description": f"1C demo: реализация {order.order_number}",
                "external_ref": f"1c-sales:{order.order_number}",
            }
        )

    for order in PurchaseOrder.query.filter(
        PurchaseOrder.order_date >= start_date,
        PurchaseOrder.order_date < end_date,
    ).limit(5):
        rows.append(
            {
                "date": order.order_date,
                "amount": order.total_amount,
                "direction": "outgoing",
                "article": purchase_article,
                "counterparty": order.supplier.name if order.supplier else "",
                "description": f"1C demo: поступление {order.order_number}",
                "external_ref": f"1c-purchase:{order.order_number}",
            }
        )

    imported = 0
    skipped = 0
    for row in rows:
        if CashTransaction.query.filter_by(external_ref=row["external_ref"]).first():
            skipped += 1
            continue
        db.session.add(
            CashTransaction(
                account_id=account.id,
                date=row["date"],
                amount=float(row["amount"] or 0),
                direction=row["direction"],
                article_id=row["article"].id,
                counterparty=row["counterparty"],
                source="1c",
                status="confirmed",
                description=row["description"],
                external_ref=row["external_ref"],
            )
        )
        imported += 1

    db.session.commit()
    return {"imported": imported, "skipped": skipped}


def mock_fns_check(counterparty):
    value = (counterparty or "").strip()
    checksum = sum(ord(ch) for ch in value)
    statuses = [
        ("active", "Действующий контрагент"),
        ("review", "Требуется ручная проверка реквизитов"),
        ("blocked", "Учебный риск: найдено совпадение в демо-списке"),
    ]
    code, label = statuses[checksum % len(statuses)] if value else statuses[1]
    return {
        "counterparty": value or "Не указан",
        "status": code,
        "label": label,
        "source": "local-mock",
        "checked_at": datetime.now(),
    }


def create_demo_payment_request(user_id=None):
    article = get_finance_article("Закупки", "operational", "cogs", create=True)
    supplier = Supplier.query.order_by(Supplier.id.asc()).first()
    request_item = PaymentRequest(
        date=datetime.now(),
        due_date=datetime.now() + timedelta(days=5),
        amount=125000,
        direction="outgoing",
        article_id=article.id,
        supplier_id=supplier.id if supplier else None,
        status="pending",
        priority="high",
        comment="Демо-заявка на оплату поставщику. Банк не вызывается.",
        created_by=user_id,
    )
    db.session.add(request_item)
    db.session.commit()
    return request_item


def mark_payment_request_paid(request_item, user_id=None):
    account = get_default_cash_account(create=True)
    external_ref = f"payment_request:{request_item.id}"
    tx = CashTransaction.query.filter_by(external_ref=external_ref).first()
    if tx is None:
        tx = CashTransaction(
            account_id=account.id,
            date=datetime.now(),
            amount=float(request_item.amount or 0),
            direction=request_item.direction,
            article_id=request_item.article_id,
            supplier_id=request_item.supplier_id,
            customer_id=request_item.customer_id,
            counterparty=(
                request_item.supplier.name
                if request_item.supplier
                else request_item.customer.name
                if request_item.customer
                else ""
            ),
            source="manual",
            status="executed",
            description=f"Оплата по демо-заявке #{request_item.id}",
            external_ref=external_ref,
        )
        db.session.add(tx)
    request_item.status = "paid"
    request_item.approved_by = request_item.approved_by or user_id
    request_item.approved_at = request_item.approved_at or datetime.now()
    db.session.commit()
    return tx
