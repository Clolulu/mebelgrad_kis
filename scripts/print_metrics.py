from app import create_app
from app.finance.routes import (
    get_period_bounds,
    calculate_income,
    calculate_actual_expenses,
    _build_cash_calendar_rows,
)
from app.models import (
    InventoryBatch,
    Payment,
    PurchaseOrder,
    SalesOrder,
    SalesOrderItem,
    IndirectExpense,
)
from app import db
from datetime import datetime, timedelta


def fmt(x):
    return f"{x:,.2f} ₽"


def main():
    app = create_app()
    with app.app_context():
        period = "2026-03"
        start_date, end_date = get_period_bounds(period)

        revenue = calculate_income(start_date, end_date)
        expenses = calculate_actual_expenses(start_date, end_date)

        # cogs
        cogs = (
            db.session.query(db.func.sum(SalesOrderItem.quantity * SalesOrderItem.cost_price))
            .join(SalesOrder)
            .filter(SalesOrder.order_date >= start_date, SalesOrder.order_date < end_date, SalesOrder.status == "completed")
            .scalar() or 0
        )

        gross_profit = revenue - cogs
        net_profit = gross_profit - expenses

        # management balance on 2026-03-23
        snapshot_date = datetime(2026, 3, 23)
        inventory_value = sum(b.available_quantity() * b.unit_cost for b in InventoryBatch.query.all())
        cash_amount = (
            db.session.query(db.func.sum(Payment.amount)).filter(Payment.status == "completed", Payment.payment_date <= snapshot_date).scalar() or 0
        )
        receivables = 0
        for order in SalesOrder.query.filter(SalesOrder.order_date <= snapshot_date).all():
            accrued = order.total_amount
            paid = sum(p.amount for p in order.payments if p.status == "completed" and p.payment_date <= snapshot_date)
            receivables += max(0, accrued - paid)
        payables = sum(order.total_amount for order in PurchaseOrder.query.filter(PurchaseOrder.order_date <= snapshot_date).all() if not order.is_paid)

        total_assets = inventory_value + cash_amount + receivables
        total_liabilities = payables
        equity = total_assets - total_liabilities

        print("Executive Summary")
        print("Период:", period)
        print("Чистая прибыль", fmt(net_profit))
        print("Свободный денежный остаток", fmt(cash_amount))
        roe = (net_profit * 12 / equity * 100) if equity else 0
        print("ROE", f"{roe:.2f} %")

        fixed_costs = sum(e.amount for e in IndirectExpense.query.filter_by(period=period).all())
        breakeven = (fixed_costs / (gross_profit / revenue) if revenue and gross_profit > 0 else 0)
        strength_buffer = ((revenue - breakeven) / revenue * 100) if revenue else 0
        print("Точка безубыточности", fmt(breakeven))
        print("Запас прочности", f"{strength_buffer:.2f} %")
        print()
        print("Ключевые метрики")
        print("Выручка:", fmt(revenue))
        print("Запасы:", fmt(inventory_value))
        print("Кредиторка:", fmt(total_liabilities))
        print("Активы:", fmt(total_assets))
        print("Пассивы:", fmt(total_liabilities))
        print("Капитал:", fmt(equity))
        print()
        print("Управленческий баланс на 2026-03-23")
        print("Запасы", fmt(inventory_value))
        print("Денежные средства", fmt(cash_amount))
        print("Дебиторка", fmt(receivables))
        print("Кредиторка", fmt(total_liabilities))
        print("Активы", fmt(total_assets))
        print("Пассивы", fmt(total_liabilities))
        print("Собственный капитал", fmt(equity))
        print("Баланс равен:", abs(total_assets - total_liabilities - equity) < 1e-2)

        # cash forecast 30 days
        base_date = datetime(2026, 3, 23).date()
        start = datetime.combine(base_date, datetime.min.time())
        end = start + timedelta(days=30)
        rows = _build_cash_calendar_rows(start, end)
        print()
        print("Прогноз движения денежных средств на 30 дней")
        print("Ожидаемый остаток:", fmt(rows[-1]["balance"]) if rows else fmt(0))


if __name__ == "__main__":
    main()
