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
    BudgetItem,
    Customer,
    Payment,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderItem,
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


@finance_bp.route("/plan-fact-analysis")
@login_required
@finance_required
def plan_fact_analysis():
    period = request.args.get("period", datetime.now().strftime("%Y-%m"))
    start_date, end_date = get_period_bounds(period)
    budget_items = BudgetItem.query.filter_by(period=period).all()

    planned_by_category = defaultdict(float)
    for item in budget_items:
        planned_by_category[(item.item_type, item.category)] += item.planned_amount

    actual_income = calculate_income(start_date, end_date)
    actual_expenses = calculate_actual_expenses(start_date, end_date)

    analysis = [
        {
            "category": "Продажи",
            "type": "income",
            "planned": planned_by_category.get(("income", "Продажи"), 0),
            "actual": actual_income,
            "variance": actual_income - planned_by_category.get(("income", "Продажи"), 0),
        },
        {
            "category": "Закупки",
            "type": "expense",
            "planned": planned_by_category.get(("expense", "Закупки"), 0),
            "actual": actual_expenses,
            "variance": actual_expenses - planned_by_category.get(("expense", "Закупки"), 0),
        },
    ]

    for (item_type, category), planned_value in sorted(planned_by_category.items()):
        if category in {"Продажи", "Закупки"}:
            continue
        analysis.append(
            {
                "category": category,
                "type": item_type,
                "planned": planned_value,
                "actual": 0,
                "variance": -planned_value,
            }
        )

    total_planned = sum(item["planned"] for item in analysis)
    total_actual = sum(item["actual"] for item in analysis)
    return render_template(
        "finance/plan_fact.html",
        period=period,
        start_date=start_date,
        end_date=end_date,
        analysis=analysis,
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
