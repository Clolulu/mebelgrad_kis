import unittest
from datetime import datetime, timedelta

from app import create_app, db
from app.models import (
    User,
    Customer,
    Supplier,
    Product,
    InventoryBatch,
    SalesOrder,
    SalesOrderItem,
    Payment,
    PurchaseOrder,
    PlanFactDeviation,
    CashCalendarItem,
)
from app.finance.routes import calculate_cogs_fifo


class FinanceModuleTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()

        with self.app.app_context():
            # create_app already вызывает db.create_all() и seed_database()
            user = User.query.filter_by(username="finance").first()
            if user is None:
                user = User(username="finance", email="finance@mebelgrad.local", is_finance=True)
                user.set_password("finance123")
                db.session.add(user)

            customer = Customer.query.filter_by(name="ООО Тест").first()
            if customer is None:
                customer = Customer(name="ООО Тест", type="legal_entity")
                db.session.add(customer)

            supplier = Supplier.query.filter_by(name="ООО Снаб").first()
            if supplier is None:
                supplier = Supplier(name="ООО Снаб", inn="1234567890")
                db.session.add(supplier)

            product = Product.query.filter_by(sku="TST-001").first()
            if product is None:
                product = Product(sku="TST-001", name="Тестовый товар", retail_price=1000.0)
                db.session.add(product)

            db.session.commit()
            self.user = user
            self.customer_id = customer.id
            self.supplier_id = supplier.id
            self.product_id = product.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self):
        return self.client.post(
            "/auth/login",
            data={"username": "finance", "password": "finance123"},
            follow_redirects=True,
        )

    def test_calculate_cogs_fifo(self):
        with self.app.app_context():
            now = datetime.now()
            # партия товара 10 шт по 100 + 50 транспорт
            batch = InventoryBatch(
                product_id=self.product_id,
                received_date=now - timedelta(days=2),
                quantity=10,
                unit_cost=100.0,
                transport_cost=50.0,
            )
            db.session.add(batch)
            order = SalesOrder(
                order_number="SO-001",
                customer_id=self.customer_id,
                order_date=now,
                status="completed",
                total_amount=0.0,
            )
            db.session.add(order)
            db.session.commit()

            item = SalesOrderItem(
                sales_order_id=order.id,
                product_id=self.product_id,
                quantity=2,
                unit_price=150.0,
                cost_price=0.0,
            )
            db.session.add(item)
            db.session.commit()

            cogs = calculate_cogs_fifo(now.replace(hour=0, minute=0, second=0, microsecond=0), now + timedelta(days=1))
            self.assertAlmostEqual(cogs, 210.0, places=2)

    def test_bdds_forecast_and_plan_fact(self):
        self.login()

        with self.app.app_context():
            # платежный календарь добавление
            resp = self.client.post(
                "/finance/cash-calendar",
                data={
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "amount": "1000",
                    "direction": "incoming",
                    "cash_type": "operational",
                    "probability": "1.0",
                },
                follow_redirects=True,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Элемент календаря сохранён", resp.get_data(as_text=True))

            # прогноз
            resp = self.client.get("/finance/bdds/forecast")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Прогноз движения денежных средств", resp.get_data(as_text=True))

            # план-факт добавление причины
            resp = self.client.post(
                "/finance/plan-fact-analysis?period=" + datetime.now().strftime("%Y-%m"),
                data={
                    "item_name": "Закупки",
                    "planned": "10000",
                    "actual": "13000",
                    "deviation": "3000",
                    "deviation_pct": "30",
                    "reason": "Рост стоимости сырья",
                },
                follow_redirects=True,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Причина отклонения сохранена", resp.get_data(as_text=True))

            deviation = PlanFactDeviation.query.filter_by(period=datetime.now().strftime("%Y-%m")).first()
            self.assertIsNotNone(deviation)
            self.assertEqual(deviation.reason, "Рост стоимости сырья")

    def test_data_mdm_roles(self):
        # finance user имеет только просмотр MDM по умолчанию
        resp = self.login()
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get("/mdm", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Модуль управления данными", resp.get_data(as_text=True))

        resp = self.client.get("/mdm/products/create", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Изменение данных MDM разрешено", resp.get_data(as_text=True))

        with self.app.app_context():
            finance_user = User.query.filter_by(username="finance").first()
            finance_user.is_data_editor = True
            db.session.commit()

        # повторный вход необходим, чтобы обновились права в сессии
        self.client.get("/auth/logout", follow_redirects=True)
        self.login()

        resp = self.client.get("/mdm/products/create")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Новая карточка товара", resp.get_data(as_text=True))

        resp = self.client.post(
            "/mdm/products/create",
            data={"sku": "ROLE-001", "name": "Тестовая роль", "unit": "шт", "retail_price": "1000", "is_active": "on"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Новая карточка номенклатуры создана", resp.get_data(as_text=True))

    def test_bdr_report_and_dashboard(self):
        self.login()

        with self.app.app_context():
            now = datetime.now()
            sosf = SalesOrder(
                order_number="SO-002",
                customer_id=self.customer_id,
                order_date=now,
                status="completed",
                total_amount=2000.0,
            )
            db.session.add(sosf)
            db.session.commit()
            item = SalesOrderItem(
                sales_order_id=sosf.id,
                product_id=self.product_id,
                quantity=1,
                unit_price=2000.0,
                cost_price=1200.0,
                product_group="Корпусная",
            )
            db.session.add(item)
            db.session.commit()

            resp = self.client.get("/finance/bdr")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Бюджет доходов и расходов", resp.get_data(as_text=True))

            resp = self.client.get("/finance/dashboard")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("Executive Summary", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
