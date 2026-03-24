import io
import json
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps

from flask import flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from app.finance import finance_bp
from app.models import (
    BalanceSnapshot,
    BudgetItem,
    CashCalendarItem,
    CompanyProfile,
    Customer,
    IndirectExpense,
    InventoryBatch,
    Payment,
    PlanFactDeviation,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderItem,
    Stock,
    Supplier,
    db,
)


def finance_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not (
            current_user.is_finance or current_user.is_admin
        ):
            flash(
                "Финансовый модуль доступен бухгалтерии и администраторам.",
                "danger",
            )
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapper


def get_period_bounds(period):
    try:
        start_date = datetime.strptime(period, "%Y-%m")
    except ValueError:
        start_date = datetime.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    end_date = (start_date + timedelta(days=32)).replace(day=1)
    return start_date, end_date


def calculate_income(start_date, end_date):
    value = (
        db.session.query(func.sum(Payment.amount))
        .filter(
            Payment.payment_date >= start_date,
            Payment.payment_date < end_date,
            Payment.status == "completed",
        )
        .scalar()
    )
    return float(value or 0)


def calculate_actual_expenses(start_date, end_date):
    value = (
        db.session.query(func.sum(PurchaseOrderItem.quantity * PurchaseOrderItem.unit_cost))
        .join(PurchaseOrder)
        .filter(
            PurchaseOrder.order_date >= start_date,
            PurchaseOrder.order_date < end_date,
        )
        .scalar()
    )
    return float(value or 0)


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
        planned = float(item.quantity * item.cost_price)
        if item.cost_price and item.cost_price > 0:
            cogs += planned
            continue

        product_id = item.product_id
        if product_id not in batch_cache:
            batch_cache[product_id] = (
                InventoryBatch.query.filter_by(product_id=product_id)
                .order_by(InventoryBatch.received_date)
                .all()
            )

        remaining = item.quantity
        for batch in batch_cache[product_id]:
            available = batch.available_quantity()
            if available <= 0:
                continue
            take = min(remaining, available)
            batch_unit_cost = batch.unit_cost + (batch.transport_cost / batch.quantity if batch.quantity else 0)
            cogs += take * batch_unit_cost
            remaining -= take
            if remaining <= 0:
                break

        if remaining > 0:
            cogs += remaining * (item.cost_price or 0)

    return cogs


def calculate_period_customer_income(start_date, end_date):
    customer_income = defaultdict(float)
    payments = (
        Payment.query.join(SalesOrder)
        .filter(
            Payment.payment_date >= start_date,
            Payment.payment_date < end_date,
            Payment.status == "completed",
        )
        .all()
    )
    for payment in payments:
        customer_income[payment.sales_order.customer.name] += payment.amount
    return customer_income


def calculate_period_supplier_payables(start_date, end_date):
    supplier_payables = defaultdict(float)
    orders = PurchaseOrder.query.filter(
        PurchaseOrder.order_date >= start_date,
        PurchaseOrder.order_date < end_date,
    ).all()
    for order in orders:
        supplier_payables[order.supplier.name] += order.total_amount
    return supplier_payables


def get_indirect_expense_map(period):
    data = defaultdict(float)
    for item in IndirectExpense.query.filter_by(period=period).all():
        data[item.category] += item.amount
    return data


@finance_bp.route("/")
@login_required
@finance_required
def index():
    current_period = datetime.now().strftime("%Y-%m")
    start_date, end_date = get_period_bounds(current_period)
    total_income = calculate_income(start_date, end_date)
    total_expenses = calculate_actual_expenses(start_date, end_date)
    current_liquidity = total_income - total_expenses

    period_rows = []
    for period in ["2026-01", "2026-02", "2026-03"]:
        period_start, period_end = get_period_bounds(period)
        income = calculate_income(period_start, period_end)
        expenses = calculate_actual_expenses(period_start, period_end)
        period_rows.append(
            {
                "period": period,
                "income": income,
                "expenses": expenses,
                "balance": income - expenses,
            }
        )

    unpaid_purchase_orders = PurchaseOrder.query.filter_by(is_paid=False).count()
    unpaid_purchase_amount = sum(
        order.total_amount for order in PurchaseOrder.query.filter_by(is_paid=False).all()
    )

    return render_template(
        "finance/index.html",
        payments_count=Payment.query.count(),
        purchase_orders_count=PurchaseOrder.query.count(),
        sales_orders_count=SalesOrder.query.count(),
        total_income=total_income,
        total_expenses=total_expenses,
        current_liquidity=current_liquidity,
        current_period=current_period,
        period_rows=period_rows,
        unpaid_purchase_orders=unpaid_purchase_orders,
        unpaid_purchase_amount=unpaid_purchase_amount,
    )


@finance_bp.route("/incoming-payments")
@login_required
@finance_required
def incoming_payments():
    page = request.args.get("page", 1, type=int)
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    q = request.args.get("q", "").strip()

    query = Payment.query.join(SalesOrder).join(Customer)
    if date_from:
        try:
            query = query.filter(Payment.payment_date >= datetime.strptime(date_from, "%Y-%m-%d"))
        except ValueError:
            flash("Некорректная дата начала периода.", "warning")
    if date_to:
        try:
            query = query.filter(
                Payment.payment_date < datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            )
        except ValueError:
            flash("Некорректная дата окончания периода.", "warning")
    if q:
        query = query.filter(
            or_(
                SalesOrder.order_number.ilike(f"%{q}%"),
                Payment.fiscal_receipt_number.ilike(f"%{q}%"),
                Customer.name.ilike(f"%{q}%"),
            )
        )

    payments = query.order_by(Payment.payment_date.desc()).paginate(page=page, per_page=20)
    filtered_payments = query.all()
    return render_template(
        "finance/payments/incoming.html",
        payments=payments,
        date_from=date_from,
        date_to=date_to,
        q=q,
        total_amount=sum(payment.amount for payment in filtered_payments),
        completed_count=sum(1 for payment in filtered_payments if payment.status == "completed"),
    )


@finance_bp.route("/outgoing-payments")
@login_required
@finance_required
def outgoing_payments():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()

    query = PurchaseOrder.query.join(Supplier)
    if q:
        query = query.filter(
            or_(
                PurchaseOrder.order_number.ilike(f"%{q}%"),
                Supplier.name.ilike(f"%{q}%"),
            )
        )
    if status == "paid":
        query = query.filter(PurchaseOrder.is_paid.is_(True))
    elif status == "unpaid":
        query = query.filter(PurchaseOrder.is_paid.is_(False))

    purchase_orders = query.order_by(PurchaseOrder.order_date.desc()).paginate(page=page, per_page=20)
    filtered = query.all()
    return render_template(
        "finance/payments/outgoing.html",
        purchase_orders=purchase_orders,
        q=q,
        status=status,
        pending_amount=sum(order.total_amount for order in filtered if not order.is_paid),
        paid_amount=sum(order.total_amount for order in filtered if order.is_paid),
        pending_count=sum(1 for order in filtered if not order.is_paid),
    )


@finance_bp.route("/outgoing-payments/<int:po_id>/mark-paid", methods=["POST"])
@login_required
@finance_required
def mark_purchase_order_paid(po_id):
    purchase_order = PurchaseOrder.query.get_or_404(po_id)
    purchase_order.is_paid = True
    purchase_order.status = "completed"
    db.session.commit()
    flash(
        f"Заказ поставщику {purchase_order.order_number} отмечен как оплаченный.",
        "success",
    )
    return redirect(url_for("finance.outgoing_payments"))


@finance_bp.route("/budget")
@login_required
@finance_required
def budget():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    items = (
        BudgetItem.query.filter_by(period=period)
        .order_by(BudgetItem.item_type, BudgetItem.category)
        .all()
    )
    income_items = [item for item in items if item.item_type == "income"]
    expense_items = [item for item in items if item.item_type == "expense"]
    total_income_plan = sum(item.planned_amount for item in income_items)
    total_expense_plan = sum(item.planned_amount for item in expense_items)

    return render_template(
        "finance/budget/index.html",
        period=period,
        income_items=income_items,
        expense_items=expense_items,
        current_period=datetime.now().strftime("%Y-%m"),
        total_income_plan=total_income_plan,
        total_expense_plan=total_expense_plan,
        planned_balance=total_income_plan - total_expense_plan,
    )


@finance_bp.route("/budget/add", methods=["GET", "POST"])
@login_required
@finance_required
def add_budget_item():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))

    if request.method == "POST":
        category = request.form.get("category", "").strip()
        if not category:
            flash("Категория обязательна.", "danger")
            return redirect(url_for("finance.add_budget_item", period=period))

        budget_item = BudgetItem(
            period=request.form.get("period", period),
            item_type=request.form.get("item_type", "expense"),
            category=category,
            planned_amount=float(request.form.get("planned_amount", 0) or 0),
        )
        db.session.add(budget_item)
        db.session.commit()

        flash("Статья бюджета добавлена.", "success")
        return redirect(url_for("finance.budget", period=budget_item.period))

    return render_template("finance/budget/add.html", period=period)


@finance_bp.route("/plan-fact-analysis", methods=["GET", "POST"])
@login_required
@finance_required
def plan_fact_analysis():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    start_date, end_date = get_period_bounds(period)
    budget_items = BudgetItem.query.filter_by(period=period).all()

    if request.method == "POST":
        item_name = request.form.get("item_name", "").strip()
        reason = request.form.get("reason", "").strip()
        deviation_val = float(request.form.get("deviation", 0) or 0)
        if item_name and reason:
            deviation = PlanFactDeviation(
                period=period,
                item_name=item_name,
                planned_value=float(request.form.get("planned", 0) or 0),
                actual_value=float(request.form.get("actual", 0) or 0),
                deviation=deviation_val,
                deviation_pct=float(request.form.get("deviation_pct", 0) or 0),
                reason=reason,
                entered_by=current_user.id,
            )
            db.session.add(deviation)
            db.session.commit()
            flash("Причина отклонения сохранена", "success")
        else:
            flash("Заполните имя статьи и причину отклонения", "warning")
        return redirect(url_for("finance.plan_fact_analysis", period=period))

    planned_by_category = defaultdict(float)
    for item in budget_items:
        planned_by_category[(item.item_type, item.category)] += item.planned_amount

    actual_income = calculate_income(start_date, end_date)
    actual_expenses = calculate_actual_expenses(start_date, end_date)
    indirect_map = get_indirect_expense_map(period)

    flex_factor = (
        actual_income / planned_by_category.get(("income", "Продажи"), actual_income or 1)
    ) if planned_by_category.get(("income", "Продажи"), 0) else 1

    analysis = [
        {
            "category": "Продажи",
            "type": "income",
            "planned": planned_by_category.get(("income", "Продажи"), 0),
            "actual": actual_income * 0.75,
            "variance": actual_income * 0.75 - planned_by_category.get(("income", "Продажи"), 0),
            "flexed": planned_by_category.get(("income", "Продажи"), 0) * flex_factor,
        },
        {
            "category": "Корпоративные проекты",
            "type": "income",
            "planned": planned_by_category.get(("income", "Корпоративные проекты"), 0),
            "actual": actual_income * 0.15,
            "variance": actual_income * 0.15 - planned_by_category.get(("income", "Корпоративные проекты"), 0),
            "flexed": planned_by_category.get(("income", "Корпоративные проекты"), 0) * flex_factor,
        },
        {
            "category": "Сборка и доставка",
            "type": "income",
            "planned": planned_by_category.get(("income", "Сборка и доставка"), 0),
            "actual": actual_income * 0.10,
            "variance": actual_income * 0.10 - planned_by_category.get(("income", "Сборка и доставка"), 0),
            "flexed": planned_by_category.get(("income", "Сборка и доставка"), 0) * flex_factor,
        },
        {
            "category": "Закупки",
            "type": "expense",
            "planned": planned_by_category.get(("expense", "Закупки"), 0),
            "actual": actual_expenses,
            "variance": actual_expenses - planned_by_category.get(("expense", "Закупки"), 0),
            "flexed": planned_by_category.get(("expense", "Закупки"), 0) * flex_factor,
        },
    ]

    for (item_type, category), planned_value in sorted(planned_by_category.items()):
        if category in {"Продажи", "Корпоративные проекты", "Сборка и доставка", "Закупки"}:
            continue
        if item_type == "income":
            if category == "Корпоративные проекты":
                actual_value = actual_income * 0.15
            elif category == "Сборка и доставка":
                actual_value = actual_income * 0.10
            else:
                actual_value = actual_income * 0.05
        else:
            actual_value = float(indirect_map.get(category, 0))
        flexed_value = planned_value * flex_factor
        variance = actual_value - planned_value
        analysis.append(
            {
                "category": category,
                "type": item_type,
                "planned": planned_value,
                "actual": actual_value,
                "variance": variance,
                "flexed": flexed_value,
            }
        )

    deviations = PlanFactDeviation.query.filter_by(period=period).order_by(PlanFactDeviation.created_at.desc()).all()
    total_planned = sum(item["planned"] for item in analysis)
    total_actual = sum(item["actual"] for item in analysis)

    deviations_alpha = []
    for item in analysis:
        planned = item.get("planned", 0) or 0
        variance_pct = (item.get("variance", 0) / planned * 100) if planned else 0
        if abs(variance_pct) >= 20:
            deviations_alpha.append({"category": item["category"], "variance_pct": variance_pct})

    return render_template(
        "finance/plan_fact.html",
        period=period,
        start_date=start_date,
        end_date=end_date,
        analysis=analysis,
        deviations=deviations,
        deviations_alpha=deviations_alpha,
        total_planned=total_planned,
        total_actual=total_actual,
        total_variance=total_actual - total_planned,
        cash_gap=actual_income - actual_expenses,
    )


@finance_bp.route("/profitability-report")
@login_required
@finance_required
def profitability_report():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    start_date, end_date = get_period_bounds(period)

    revenue = calculate_income(start_date, end_date)
    cogs = (
        db.session.query(func.sum(SalesOrderItem.quantity * SalesOrderItem.cost_price))
        .join(SalesOrder)
        .filter(
            SalesOrder.order_date >= start_date,
            SalesOrder.order_date < end_date,
            SalesOrder.status == "completed",
        )
        .scalar()
        or 0
    )
    cogs = float(cogs)
    gross_profit = revenue - cogs
    operating_expenses = calculate_actual_expenses(start_date, end_date)
    usn_tax = revenue * 0.06
    operating_profit = gross_profit - operating_expenses
    net_profit = operating_profit - usn_tax

    return render_template(
        "finance/profitability.html",
        period=period,
        start_date=start_date,
        end_date=end_date,
        revenue=revenue,
        cogs=cogs,
        gross_profit=gross_profit,
        operating_expenses=operating_expenses,
        operating_profit=operating_profit,
        usn_tax=usn_tax,
        net_profit=net_profit,
        gross_margin_pct=(gross_profit / revenue * 100) if revenue else 0,
        net_margin_pct=(net_profit / revenue * 100) if revenue else 0,
        cogs_note="Для MVP себестоимость фиксируется в момент продажи в поле cost_price.",
    )


@finance_bp.route("/indirect-expenses", methods=["GET", "POST"])
@login_required
@finance_required
def indirect_expenses():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    if request.method == "POST":
        category = request.form.get("category", "").strip()
        amount = float(request.form.get("amount", 0) or 0)
        description = request.form.get("description", "").strip()
        if not category or amount <= 0:
            flash("Категория и сумма обязательны.", "warning")
            return redirect(url_for("finance.indirect_expenses", period=period))
        exp = IndirectExpense(period=period, category=category, amount=amount, description=description)
        db.session.add(exp)
        db.session.commit()
        flash("Косвенная статья добавлена.", "success")
        return redirect(url_for("finance.indirect_expenses", period=period))

    items = IndirectExpense.query.filter_by(period=period).order_by(IndirectExpense.category.asc()).all()
    return render_template("finance/indirect_expenses.html", period=period, items=items)


@finance_bp.route("/indirect-expenses/<int:expense_id>/delete", methods=["POST"])
@login_required
@finance_required
def delete_indirect_expense(expense_id):
    expense = IndirectExpense.query.get_or_404(expense_id)
    period = expense.period
    db.session.delete(expense)
    db.session.commit()
    flash("Косвенная статья удалена.", "success")
    return redirect(url_for("finance.indirect_expenses", period=period))


@finance_bp.route("/cash-calendar", methods=["GET", "POST"])
@login_required
@finance_required
def cash_calendar():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    start_date, end_date = get_period_bounds(period)

    if request.method == "POST":
        date_str = request.form.get("date")
        amount = float(request.form.get("amount", 0) or 0)
        direction = request.form.get("direction")
        cash_type = request.form.get("cash_type")
        counterparty_id = request.form.get("counterparty_id") or None
        supplier_id = request.form.get("supplier_id") or None
        probability = float(request.form.get("probability", 1.0) or 1.0)
        comment = request.form.get("comment", "").strip()

        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            flash("Неправильная дата", "warning")
            return redirect(url_for("finance.cash_calendar", period=period))

        item = CashCalendarItem(
            date=date,
            amount=amount,
            direction=direction,
            cash_type=cash_type,
            counterparty_id=counterparty_id,
            supplier_id=supplier_id,
            status="planned",
            probability=probability,
            comment=comment,
        )
        db.session.add(item)
        db.session.commit()
        flash("Элемент календаря сохранён.", "success")
        return redirect(url_for("finance.cash_calendar", period=period))

    items = CashCalendarItem.query.filter(CashCalendarItem.date >= start_date, CashCalendarItem.date < end_date).order_by(CashCalendarItem.date).all()
    return render_template("finance/cash_calendar.html", period=period, items=items)


@finance_bp.route("/cash-calendar/<int:item_id>/delete", methods=["POST"])
@login_required
@finance_required
def delete_cash_calendar_item(item_id):
    item = CashCalendarItem.query.get_or_404(item_id)
    period = item.date.strftime("%Y-%m")
    db.session.delete(item)
    db.session.commit()
    flash("Элемент календаря удалён.", "success")
    return redirect(url_for("finance.cash_calendar", period=period))


@finance_bp.route("/cash-flow")
@login_required
@finance_required
def cash_flow():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    start_date, end_date = get_period_bounds(period)

    incoming_map = defaultdict(float)
    for payment in Payment.query.filter(
        Payment.payment_date >= start_date,
        Payment.payment_date < end_date,
        Payment.status == "completed",
    ).all():
        incoming_map[payment.payment_date.date()] += payment.amount

    outgoing_paid_map = defaultdict(float)
    outgoing_scheduled_map = defaultdict(float)
    for order in PurchaseOrder.query.filter(
        PurchaseOrder.order_date >= start_date,
        PurchaseOrder.order_date < end_date,
    ).all():
        if order.is_paid:
            outgoing_paid_map[order.order_date.date()] += order.total_amount
        else:
            outgoing_scheduled_map[order.order_date.date()] += order.total_amount

    rows = []
    running_balance = 0
    day = start_date
    while day < end_date:
        day_key = day.date()
        incoming = incoming_map.get(day_key, 0)
        outgoing_paid = outgoing_paid_map.get(day_key, 0)
        outgoing_scheduled = outgoing_scheduled_map.get(day_key, 0)
        running_balance += incoming - outgoing_paid
        rows.append(
            {
                "date": day_key,
                "incoming": incoming,
                "outgoing_paid": outgoing_paid,
                "outgoing_scheduled": outgoing_scheduled,
                "net_actual": incoming - outgoing_paid,
                "projected_gap": incoming - outgoing_paid - outgoing_scheduled,
                "running_balance": running_balance,
            }
        )
        day += timedelta(days=1)

    active_rows = [
        row
        for row in rows
        if row["incoming"] or row["outgoing_paid"] or row["outgoing_scheduled"]
    ]

    return render_template(
        "finance/cash_flow.html",
        period=period,
        rows=rows,
        active_rows=active_rows,
        total_incoming=sum(row["incoming"] for row in rows),
        total_outgoing_paid=sum(row["outgoing_paid"] for row in rows),
        total_outgoing_scheduled=sum(row["outgoing_scheduled"] for row in rows),
        closing_balance=running_balance,
    )


@finance_bp.route("/settlements")
@login_required
@finance_required
def settlements():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    start_date, end_date = get_period_bounds(period)

    customer_rows = []
    for customer in Customer.query.order_by(Customer.name.asc()).all():
        orders = [
            order
            for order in customer.sales_orders
            if start_date <= order.order_date < end_date
        ]
        if not orders:
            continue
        billed = sum(order.total_amount for order in orders)
        paid = sum(
            payment.amount
            for order in orders
            for payment in order.payments
            if start_date <= payment.payment_date < end_date
            and payment.status == "completed"
        )
        customer_rows.append(
            {
                "name": customer.name,
                "type": customer.type,
                "orders_count": len(orders),
                "billed": billed,
                "paid": paid,
                "debt": billed - paid,
            }
        )

    supplier_rows = []
    for supplier in Supplier.query.order_by(Supplier.name.asc()).all():
        orders = [
            order
            for order in supplier.purchase_orders
            if start_date <= order.order_date < end_date
        ]
        if not orders:
            continue
        accrued = sum(order.total_amount for order in orders)
        paid = sum(order.total_amount for order in orders if order.is_paid)
        supplier_rows.append(
            {
                "name": supplier.name,
                "orders_count": len(orders),
                "accrued": accrued,
                "paid": paid,
                "payable": accrued - paid,
            }
        )

    customer_rows.sort(key=lambda row: row["debt"], reverse=True)
    supplier_rows.sort(key=lambda row: row["payable"], reverse=True)

    return render_template(
        "finance/settlements.html",
        period=period,
        customer_rows=customer_rows,
        supplier_rows=supplier_rows,
        total_customer_billed=sum(row["billed"] for row in customer_rows),
        total_customer_paid=sum(row["paid"] for row in customer_rows),
        total_supplier_accrued=sum(row["accrued"] for row in supplier_rows),
        total_supplier_paid=sum(row["paid"] for row in supplier_rows),
        top_customer_income=sorted(
            calculate_period_customer_income(start_date, end_date).items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5],
        top_supplier_payables=sorted(
            calculate_period_supplier_payables(start_date, end_date).items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5],
    )


def calculate_bdr_pivot(start_date, end_date):
    data = []
    line_items = (
        SalesOrderItem.query.join(SalesOrder)
        .filter(
            SalesOrder.order_date >= start_date,
            SalesOrder.order_date < end_date,
            SalesOrder.status == "completed",
        )
        .all()
    )

    pivot = defaultdict(lambda: {"revenue": 0.0, "cogs": 0.0, "quantity": 0})
    for item in line_items:
        segment = item.sales_order.segment or "retail"
        group = item.product_group or "Общие"
        rev = item.quantity * item.unit_price
        cogs = item.quantity * item.cost_price
        pivot[(segment, group)]["revenue"] += rev
        pivot[(segment, group)]["cogs"] += cogs
        pivot[(segment, group)]["quantity"] += item.quantity

    for (segment, group), values in pivot.items():
        gp = values["revenue"] - values["cogs"]
        data.append(
            {
                "segment": segment,
                "group": group,
                "revenue": values["revenue"],
                "cogs": values["cogs"],
                "gross_profit": gp,
                "gross_margin_pct": (gp / values["revenue"] * 100) if values["revenue"] else 0,
                "markup_pct": (gp / values["cogs"] * 100) if values["cogs"] else 0,
                "quantity": values["quantity"],
            }
        )
    return data


@finance_bp.route("/bdr")
@login_required
@finance_required
def bdr_report():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    start_date, end_date = get_period_bounds(period)
    pivot = calculate_bdr_pivot(start_date, end_date)
    total_revenue = sum(x["revenue"] for x in pivot)
    total_cogs = calculate_cogs_fifo(start_date, end_date)
    total_profit = total_revenue - total_cogs

    # Сводная строка по сегментам и группам
    return render_template(
        "finance/bdr.html",
        period=period,
        pivot=pivot,
        total_revenue=total_revenue,
        total_cogs=total_cogs,
        total_profit=total_profit,
    )


def _build_cash_calendar_rows(start_date, end_date):
    incoming = defaultdict(float)
    outgoing = defaultdict(float)

    # Фактические платежи, уже произведенные
    for payment in Payment.query.filter(
        Payment.payment_date >= start_date,
        Payment.payment_date < end_date,
    ).all():
        if payment.status == "completed":
            incoming[payment.payment_date.date()] += payment.amount

    # Фактические расходы (оплаченные закупки)
    for order in PurchaseOrder.query.filter(
        PurchaseOrder.order_date >= start_date,
        PurchaseOrder.order_date < end_date,
    ).all():
        if order.is_paid:
            outgoing[order.order_date.date()] += order.total_amount

    # Плановые платежи для неоплаченных закупок (30 дней от заказа)
    for order in PurchaseOrder.query.filter(PurchaseOrder.order_date < end_date).all():
        if not order.is_paid:
            pay_date = (order.order_date + timedelta(days=30)).date()
            if pay_date < end_date.date():
                outgoing[pay_date] += order.total_amount * 0.95

    # Ожидаемые поступления от дебиторки (14 дней от заказа)
    for so in SalesOrder.query.filter(SalesOrder.order_date < end_date).all():
        accrued = so.total_amount or 0
        paid = sum(p.amount for p in so.payments if p.status == "completed" and p.payment_date < end_date)
        due = max(0, accrued - paid)
        if due > 0:
            collect_date = (so.order_date + timedelta(days=14)).date()
            if collect_date < end_date.date():
                incoming[collect_date] += due * 0.8

    # Позиции платежного календаря
    for item in CashCalendarItem.query.filter(
        CashCalendarItem.date >= start_date,
        CashCalendarItem.date < end_date,
    ).all():
        d = item.date.date()
        if item.direction == "incoming":
            incoming[d] += item.amount * item.probability
        else:
            outgoing[d] += item.amount * item.probability

    # Начальный остаток = сумма полученных платежей до начала периода
    running_balance = (
        db.session.query(func.sum(Payment.amount))
        .filter(Payment.status == "completed", Payment.payment_date < start_date)
        .scalar()
        or 0
    )

    rows = []
    day = start_date
    while day < end_date:
        d = day.date()
        inc = incoming.get(d, 0)
        out = outgoing.get(d, 0)
        running_balance += inc - out
        rows.append(
            {
                "date": d,
                "incoming": inc,
                "outgoing": out,
                "net": inc - out,
                "balance": running_balance,
                "is_gap": running_balance < 0,
            }
        )
        day += timedelta(days=1)

    return rows


@finance_bp.route("/bdds/calendar")
@login_required
@finance_required
def bdds_calendar():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    start_date, end_date = get_period_bounds(period)
    rows = _build_cash_calendar_rows(start_date, end_date)
    closing_balance = rows[-1]["balance"] if rows else 0

    return render_template(
        "finance/bdds_calendar.html",
        period=period,
        rows=rows,
        closing_balance=closing_balance,
    )


@finance_bp.route("/bdds/forecast")
@login_required
@finance_required
def bdds_forecast():
    base_date = datetime.now().date()
    start_date = datetime.combine(base_date, datetime.min.time())
    end_date = start_date + timedelta(days=30)
    rows = _build_cash_calendar_rows(start_date, end_date)

    if rows:
        saturdays = [r for r in rows if r["balance"] < 0][-3:]
        critical_dates = [r["date"] for r in rows if r["balance"] < 0]
    else:
        critical_dates = []

    return render_template(
        "finance/bdds_forecast.html",
        rows=rows,
        ending_balance=rows[-1]["balance"] if rows else 0,
        critical_dates=critical_dates,
    )


@finance_bp.route("/help")
@login_required
@finance_required
def finance_help():
    return render_template("finance/help.html")


@finance_bp.route("/management-balance")
@login_required
@finance_required
def management_balance():
    date_str = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    try:
        snapshot_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        snapshot_date = datetime.now()

    inventory_value = 0
    for batch in InventoryBatch.query.all():
        inventory_value += batch.available_quantity() * batch.unit_cost

    cash_amount = (
        db.session.query(func.sum(Payment.amount))
        .filter(Payment.status == "completed", Payment.payment_date <= snapshot_date)
        .scalar()
        or 0
    )

    receivables = 0
    for order in SalesOrder.query.filter(SalesOrder.order_date <= snapshot_date).all():
        accrued = order.total_amount
        paid = sum(p.amount for p in order.payments if p.status == "completed" and p.payment_date <= snapshot_date)
        receivables += max(0, accrued - paid)

    payables = 0
    for order in PurchaseOrder.query.filter(PurchaseOrder.order_date <= snapshot_date).all():
        if not order.is_paid:
            payables += order.total_amount

    total_assets = inventory_value + cash_amount + receivables
    total_liabilities = payables
    equity = total_assets - total_liabilities

    return render_template(
        "finance/management_balance.html",
        snapshot_date=snapshot_date.date(),
        inventory_value=inventory_value,
        cash_amount=cash_amount,
        receivables=receivables,
        payables=payables,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        equity=equity,
        check_equal=(abs(total_assets - total_liabilities - equity) < 1e-2),
    )


@finance_bp.route("/dashboard")
@login_required
@finance_required
def dashboard():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    start_date, end_date = get_period_bounds(period)

    revenue = calculate_income(start_date, end_date)
    cogs = (
        db.session.query(func.sum(SalesOrderItem.quantity * SalesOrderItem.cost_price))
        .join(SalesOrder)
        .filter(
            SalesOrder.order_date >= start_date,
            SalesOrder.order_date < end_date,
            SalesOrder.status == "completed",
        )
        .scalar()
        or 0
    )
    gross_profit = revenue - cogs
    operating_expenses = calculate_actual_expenses(start_date, end_date)
    net_profit = gross_profit - operating_expenses

    cash_flow_end = (
        db.session.query(func.sum(Payment.amount))
        .filter(Payment.status == "completed", Payment.payment_date < end_date)
        .scalar()
        or 0
    )

    # Составим управленческий набор статей активов аналогично management_balance
    inventory_value = sum(batch.available_quantity() * batch.unit_cost for batch in InventoryBatch.query.all())
    cash_amount = (
        db.session.query(func.sum(Payment.amount))
        .filter(Payment.status == "completed", Payment.payment_date < end_date)
        .scalar()
        or 0
    )

    receivables = 0
    for order in SalesOrder.query.filter(SalesOrder.order_date <= end_date).all():
        accrued = order.total_amount
        paid = sum(p.amount for p in order.payments if p.status == "completed" and p.payment_date <= end_date)
        receivables += max(0, accrued - paid)

    assets = total_assets = inventory_value + cash_amount + receivables
    liabilities = payables = sum(order.total_amount for order in PurchaseOrder.query.filter_by(is_paid=False).all())
    equity = total_assets - liabilities
    roe = (net_profit * 12 / equity * 100) if equity else 0

    fixed_costs = sum(exp.amount for exp in IndirectExpense.query.filter_by(period=period).all())
    breakeven = (fixed_costs / (gross_profit / revenue) if revenue and gross_profit > 0 else 0)
    strength_buffer = ((revenue - breakeven) / revenue * 100) if revenue else 0

    return render_template(
        "finance/dashboard.html",
        period=period,
        net_profit=net_profit,
        cash_balance=cash_flow_end,
        roe=roe,
        breakeven=breakeven,
        strength_buffer=strength_buffer,
        revenue=revenue,
        inventory_value=inventory_value,
        payables=payables,
        assets=assets,
        liabilities=liabilities,
        equity=equity,
    )


@finance_bp.route("/export-1c", methods=["POST"])
@login_required
@finance_required
def export_1c():
    period = request.form.get("period", datetime.now().strftime("%Y-%m"))
    start_date, end_date = get_period_bounds(period)

    sales_orders = SalesOrder.query.filter(
        SalesOrder.order_date >= start_date,
        SalesOrder.order_date < end_date,
    ).all()
    purchase_orders = PurchaseOrder.query.filter(
        PurchaseOrder.order_date >= start_date,
        PurchaseOrder.order_date < end_date,
    ).all()

    payload = {
        "export_date": datetime.now().isoformat(),
        "period": period,
        "sales_orders": [],
        "purchase_orders": [],
    }

    for order in sales_orders:
        payload["sales_orders"].append(
            {
                "order_number": order.order_number,
                "customer": order.customer.name,
                "order_date": order.order_date.isoformat(),
                "status": order.status,
                "total_amount": order.total_amount,
                "items": [
                    {
                        "sku": item.product.sku,
                        "name": item.product.name,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                        "cost_price": item.cost_price,
                    }
                    for item in order.items
                ],
            }
        )

    for order in purchase_orders:
        payload["purchase_orders"].append(
            {
                "order_number": order.order_number,
                "supplier": order.supplier.name,
                "order_date": order.order_date.isoformat(),
                "status": order.status,
                "total_amount": order.total_amount,
                "is_paid": order.is_paid,
                "items": [
                    {
                        "sku": item.product.sku,
                        "name": item.product.name,
                        "quantity": item.quantity,
                        "unit_cost": item.unit_cost,
                    }
                    for item in order.items
                ],
            }
        )

    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return send_file(
        io.BytesIO(content),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"mebelgrad_exchange_{period}.json",
    )


# ============================================================================
# PRINT ENDPOINTS / ПЕЧАТЬ ОТЧЁТОВ
# ============================================================================

@finance_bp.route("/dashboard/print")
@login_required
@finance_required
def dashboard_print():
    """Печать финансового дашборда"""
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    show_seal = request.args.get("show_seal", "1") in ["1", "true", "on"]
    show_signatures = request.args.get("show_signatures", "1") in ["1", "true", "on"]
    
    start_date, end_date = get_period_bounds(period)
    
    revenue = calculate_income(start_date, end_date)
    cogs = (
        db.session.query(func.sum(SalesOrderItem.quantity * SalesOrderItem.cost_price))
        .join(SalesOrder)
        .filter(
            SalesOrder.order_date >= start_date,
            SalesOrder.order_date < end_date,
            SalesOrder.status == "completed",
        )
        .scalar()
        or 0
    )
    gross_profit = revenue - cogs
    operating_expenses = calculate_actual_expenses(start_date, end_date)
    net_profit = gross_profit - operating_expenses
    
    inventory_value = sum(batch.available_quantity() * batch.unit_cost for batch in InventoryBatch.query.all())
    cash_amount = (
        db.session.query(func.sum(Payment.amount))
        .filter(Payment.status == "completed", Payment.payment_date < end_date)
        .scalar()
        or 0
    )
    
    receivables = 0
    for order in SalesOrder.query.filter(SalesOrder.order_date <= end_date).all():
        accrued = order.total_amount
        paid = sum(p.amount for p in order.payments if p.status == "completed" and p.payment_date <= end_date)
        receivables += max(0, accrued - paid)
    
    assets = total_assets = inventory_value + cash_amount + receivables
    liabilities = payables = sum(order.total_amount for order in PurchaseOrder.query.filter_by(is_paid=False).all())
    equity = total_assets - liabilities
    roe = (net_profit * 12 / equity * 100) if equity else 0
    
    fixed_costs = sum(exp.amount for exp in IndirectExpense.query.filter_by(period=period).all())
    breakeven = (fixed_costs / (gross_profit / revenue) if revenue and gross_profit > 0 else 0)
    strength_buffer = ((revenue - breakeven) / revenue * 100) if revenue else 0
    
    company = CompanyProfile.query.first()
    
    return render_template(
        "finance/print/dashboard_print.html",
        company=company,
        period=period,
        net_profit=net_profit,
        cash_balance=cash_amount,
        roe=roe,
        breakeven=breakeven,
        strength_buffer=strength_buffer,
        revenue=revenue,
        inventory_value=inventory_value,
        cash_balance_detail=cash_amount,
        payables=payables,
        assets=assets,
        liabilities=liabilities,
        equity=equity,
        show_seal=show_seal,
        show_signatures=show_signatures,
        now=datetime.now(),
    )


@finance_bp.route("/management-balance/print")
@login_required
@finance_required
def management_balance_print():
    """Печать баланса по управленческому учету"""
    date_str = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    show_seal = request.args.get("show_seal", "1") in ["1", "true", "on"]
    show_signatures = request.args.get("show_signatures", "1") in ["1", "true", "on"]
    
    try:
        snapshot_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        snapshot_date = datetime.now()
    
    inventory_value = 0
    for batch in InventoryBatch.query.all():
        inventory_value += batch.available_quantity() * batch.unit_cost
    
    cash_amount = (
        db.session.query(func.sum(Payment.amount))
        .filter(Payment.status == "completed", Payment.payment_date <= snapshot_date)
        .scalar()
        or 0
    )
    
    receivables = 0
    for order in SalesOrder.query.filter(SalesOrder.order_date <= snapshot_date).all():
        accrued = order.total_amount
        paid = sum(p.amount for p in order.payments if p.status == "completed" and p.payment_date <= snapshot_date)
        receivables += max(0, accrued - paid)
    
    payables = 0
    for order in PurchaseOrder.query.filter(PurchaseOrder.order_date <= snapshot_date).all():
        if not order.is_paid:
            payables += order.total_amount
    
    total_assets = inventory_value + cash_amount + receivables
    total_liabilities = payables
    equity = total_assets - total_liabilities
    
    company = CompanyProfile.query.first()
    
    return render_template(
        "finance/print/management_balance_print.html",
        company=company,
        snapshot_date=snapshot_date.date(),
        inventory_value=inventory_value,
        cash_amount=cash_amount,
        receivables=receivables,
        payables=payables,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        equity=equity,
        check_equal=(abs(total_assets - total_liabilities - equity) < 1e-2),
        show_seal=show_seal,
        show_signatures=show_signatures,
        now=datetime.now(),
    )


@finance_bp.route("/plan-fact-analysis/print")
@login_required
@finance_required
def plan_fact_analysis_print():
    """Печать анализа плана и факта"""
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    show_seal = request.args.get("show_seal", "1") in ["1", "true", "on"]
    show_signatures = request.args.get("show_signatures", "1") in ["1", "true", "on"]
    
    start_date, end_date = get_period_bounds(period)
    budget_items = BudgetItem.query.filter_by(period=period).all()
    
    planned_by_category = defaultdict(float)
    for item in budget_items:
        planned_by_category[(item.item_type, item.category)] += item.planned_amount
    
    actual_income = calculate_income(start_date, end_date)
    actual_expenses = calculate_actual_expenses(start_date, end_date)
    indirect_map = get_indirect_expense_map(period)
    
    flex_factor = (
        actual_income / planned_by_category.get(("income", "Продажи"), actual_income or 1)
    ) if planned_by_category.get(("income", "Продажи"), 0) else 1
    
    analysis = [
        {
            "category": "Продажи",
            "type": "income",
            "planned": planned_by_category.get(("income", "Продажи"), 0),
            "actual": actual_income * 0.75,
            "variance": actual_income * 0.75 - planned_by_category.get(("income", "Продажи"), 0),
            "flexed": planned_by_category.get(("income", "Продажи"), 0) * flex_factor,
        },
        {
            "category": "Корпоративные проекты",
            "type": "income",
            "planned": planned_by_category.get(("income", "Корпоративные проекты"), 0),
            "actual": actual_income * 0.15,
            "variance": actual_income * 0.15 - planned_by_category.get(("income", "Корпоративные проекты"), 0),
            "flexed": planned_by_category.get(("income", "Корпоративные проекты"), 0) * flex_factor,
        },
        {
            "category": "Сборка и доставка",
            "type": "income",
            "planned": planned_by_category.get(("income", "Сборка и доставка"), 0),
            "actual": actual_income * 0.10,
            "variance": actual_income * 0.10 - planned_by_category.get(("income", "Сборка и доставка"), 0),
            "flexed": planned_by_category.get(("income", "Сборка и доставка"), 0) * flex_factor,
        },
        {
            "category": "Закупки",
            "type": "expense",
            "planned": planned_by_category.get(("expense", "Закупки"), 0),
            "actual": actual_expenses,
            "variance": actual_expenses - planned_by_category.get(("expense", "Закупки"), 0),
            "flexed": planned_by_category.get(("expense", "Закупки"), 0) * flex_factor,
        },
    ]
    
    for (item_type, category), planned_value in sorted(planned_by_category.items()):
        if category in {"Продажи", "Корпоративные проекты", "Сборка и доставка", "Закупки"}:
            continue
        if item_type == "income":
            if category == "Корпоративные проекты":
                actual_value = actual_income * 0.15
            elif category == "Сборка и доставка":
                actual_value = actual_income * 0.10
            else:
                actual_value = actual_income * 0.05
        else:
            actual_value = float(indirect_map.get(category, 0))
        flexed_value = planned_value * flex_factor
        variance = actual_value - planned_value
        analysis.append(
            {
                "category": category,
                "type": item_type,
                "planned": planned_value,
                "actual": actual_value,
                "variance": variance,
                "flexed": flexed_value,
            }
        )
    
    deviations = PlanFactDeviation.query.filter_by(period=period).order_by(PlanFactDeviation.created_at.desc()).all()
    total_planned = sum(item["planned"] for item in analysis)
    total_actual = sum(item["actual"] for item in analysis)
    
    deviations_alpha = []
    for item in analysis:
        planned = item.get("planned", 0) or 0
        variance_pct = (item.get("variance", 0) / planned * 100) if planned else 0
        if abs(variance_pct) >= 20:
            deviations_alpha.append({"category": item["category"], "variance_pct": variance_pct})
    
    company = CompanyProfile.query.first()
    
    return render_template(
        "finance/print/plan_fact_print.html",
        company=company,
        period=period,
        start_date=start_date,
        end_date=end_date,
        analysis=analysis,
        deviations=deviations,
        deviations_alpha=deviations_alpha,
        total_planned=total_planned,
        total_actual=total_actual,
        total_variance=total_actual - total_planned,
        cash_gap=actual_income - actual_expenses,
        show_seal=show_seal,
        show_signatures=show_signatures,
        now=datetime.now(),
    )


@finance_bp.route("/cash-flow/print")
@login_required
@finance_required
def cash_flow_print():
    """Печать отчета о кассовых потоках"""
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    show_seal = request.args.get("show_seal", "1") in ["1", "true", "on"]
    show_signatures = request.args.get("show_signatures", "1") in ["1", "true", "on"]
    
    start_date, end_date = get_period_bounds(period)
    
    incoming_map = defaultdict(float)
    for payment in Payment.query.filter(
        Payment.payment_date >= start_date,
        Payment.payment_date < end_date,
        Payment.status == "completed",
    ).all():
        incoming_map[payment.payment_date.date()] += payment.amount
    
    outgoing_paid_map = defaultdict(float)
    outgoing_scheduled_map = defaultdict(float)
    for order in PurchaseOrder.query.filter(
        PurchaseOrder.order_date >= start_date,
        PurchaseOrder.order_date < end_date,
    ).all():
        if order.is_paid:
            outgoing_paid_map[order.order_date.date()] += order.total_amount
        else:
            outgoing_scheduled_map[order.order_date.date()] += order.total_amount
    
    rows = []
    running_balance = 0
    day = start_date
    while day < end_date:
        day_key = day.date()
        incoming = incoming_map.get(day_key, 0)
        outgoing_paid = outgoing_paid_map.get(day_key, 0)
        outgoing_scheduled = outgoing_scheduled_map.get(day_key, 0)
        running_balance += incoming - outgoing_paid
        rows.append(
            {
                "date": day_key,
                "incoming": incoming,
                "outgoing_paid": outgoing_paid,
                "outgoing_scheduled": outgoing_scheduled,
                "net_actual": incoming - outgoing_paid,
                "projected_gap": incoming - outgoing_paid - outgoing_scheduled,
                "running_balance": running_balance,
            }
        )
        day += timedelta(days=1)
    
    active_rows = [
        row
        for row in rows
        if row["incoming"] or row["outgoing_paid"] or row["outgoing_scheduled"]
    ]
    
    company = CompanyProfile.query.first()
    
    return render_template(
        "finance/print/cash_flow_print.html",
        company=company,
        period=period,
        rows=rows,
        active_rows=active_rows,
        total_incoming=sum(row["incoming"] for row in rows),
        total_outgoing_paid=sum(row["outgoing_paid"] for row in rows),
        total_outgoing_scheduled=sum(row["outgoing_scheduled"] for row in rows),
        closing_balance=running_balance,
        show_seal=show_seal,
        show_signatures=show_signatures,
        now=datetime.now(),
    )


@finance_bp.route("/bdds/forecast/print")
@login_required
@finance_required
def bdds_forecast_print():
    """Печать прогноза денежных потоков"""
    show_seal = request.args.get("show_seal", "1") in ["1", "true", "on"]
    show_signatures = request.args.get("show_signatures", "1") in ["1", "true", "on"]
    
    base_date = datetime.now().date()
    start_date = datetime.combine(base_date, datetime.min.time())
    end_date = start_date + timedelta(days=30)
    rows = _build_cash_calendar_rows(start_date, end_date)
    
    if rows:
        saturdays = [r for r in rows if r["balance"] < 0][-3:]
        critical_dates = [r["date"] for r in rows if r["balance"] < 0]
    else:
        critical_dates = []
    
    company = CompanyProfile.query.first()
    
    return render_template(
        "finance/print/bdds_forecast_print.html",
        company=company,
        rows=rows,
        ending_balance=rows[-1]["balance"] if rows else 0,
        critical_dates=critical_dates,
        show_seal=show_seal,
        show_signatures=show_signatures,
        now=datetime.now(),
    )


@finance_bp.route("/settlements/print")
@login_required
@finance_required
def settlements_print():
    """Печать расчетов с контрагентами"""
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    show_seal = request.args.get("show_seal", "1") in ["1", "true", "on"]
    show_signatures = request.args.get("show_signatures", "1") in ["1", "true", "on"]
    
    start_date, end_date = get_period_bounds(period)
    
    customer_rows = []
    for customer in Customer.query.order_by(Customer.name.asc()).all():
        orders = [
            order
            for order in customer.sales_orders
            if start_date <= order.order_date < end_date
        ]
        if not orders:
            continue
        billed = sum(order.total_amount for order in orders)
        paid = sum(
            payment.amount
            for order in orders
            for payment in order.payments
            if start_date <= payment.payment_date < end_date
            and payment.status == "completed"
        )
        customer_rows.append(
            {
                "name": customer.name,
                "type": customer.type,
                "orders_count": len(orders),
                "billed": billed,
                "paid": paid,
                "debt": billed - paid,
            }
        )
    
    supplier_rows = []
    for supplier in Supplier.query.order_by(Supplier.name.asc()).all():
        orders = [
            order
            for order in supplier.purchase_orders
            if start_date <= order.order_date < end_date
        ]
        if not orders:
            continue
        accrued = sum(order.total_amount for order in orders)
        paid = sum(order.total_amount for order in orders if order.is_paid)
        supplier_rows.append(
            {
                "name": supplier.name,
                "orders_count": len(orders),
                "accrued": accrued,
                "paid": paid,
                "payable": accrued - paid,
            }
        )
    
    customer_rows.sort(key=lambda row: row["debt"], reverse=True)
    supplier_rows.sort(key=lambda row: row["payable"], reverse=True)
    
    company = CompanyProfile.query.first()
    
    return render_template(
        "finance/print/settlements_print.html",
        company=company,
        period=period,
        customer_rows=customer_rows,
        supplier_rows=supplier_rows,
        total_customer_billed=sum(row["billed"] for row in customer_rows),
        total_customer_paid=sum(row["paid"] for row in customer_rows),
        total_supplier_accrued=sum(row["accrued"] for row in supplier_rows),
        total_supplier_paid=sum(row["paid"] for row in supplier_rows),
        top_customer_income=sorted(
            calculate_period_customer_income(start_date, end_date).items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5],
        top_supplier_payables=sorted(
            calculate_period_supplier_payables(start_date, end_date).items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5],
        show_seal=show_seal,
        show_signatures=show_signatures,
        now=datetime.now(),
    )


@finance_bp.route("/budget/print")
@login_required
@finance_required
def budget_print():
    """Печать бюджета доходов и расходов"""
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    show_seal = request.args.get("show_seal", "1") in ["1", "true", "on"]
    show_signatures = request.args.get("show_signatures", "1") in ["1", "true", "on"]
    
    items = (
        BudgetItem.query.filter_by(period=period)
        .order_by(BudgetItem.item_type, BudgetItem.category)
        .all()
    )
    income_items = [item for item in items if item.item_type == "income"]
    expense_items = [item for item in items if item.item_type == "expense"]
    total_income_plan = sum(item.planned_amount for item in income_items)
    total_expense_plan = sum(item.planned_amount for item in expense_items)
    
    company = CompanyProfile.query.first()
    
    return render_template(
        "finance/print/budget_print.html",
        company=company,
        period=period,
        income_items=income_items,
        expense_items=expense_items,
        total_income_plan=total_income_plan,
        total_expense_plan=total_expense_plan,
        planned_balance=total_income_plan - total_expense_plan,
        show_seal=show_seal,
        show_signatures=show_signatures,
        now=datetime.now(),
    )


@finance_bp.route("/bdr/print")
@login_required
@finance_required
def bdr_report_print():
    """Печать анализа рентабельности по сегментам"""
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    show_seal = request.args.get("show_seal", "1") in ["1", "true", "on"]
    show_signatures = request.args.get("show_signatures", "1") in ["1", "true", "on"]
    
    start_date, end_date = get_period_bounds(period)
    pivot = calculate_bdr_pivot(start_date, end_date)
    total_revenue = sum(x["revenue"] for x in pivot)
    total_cogs = calculate_cogs_fifo(start_date, end_date)
    total_profit = total_revenue - total_cogs
    
    company = CompanyProfile.query.first()
    
    return render_template(
        "finance/print/bdr_print.html",
        company=company,
        period=period,
        pivot=pivot,
        total_revenue=total_revenue,
        total_cogs=total_cogs,
        total_profit=total_profit,
        show_seal=show_seal,
        show_signatures=show_signatures,
        now=datetime.now(),
    )
