import unittest
from datetime import datetime, timedelta

from app import create_app, db
from app.finance import services as finance_services
from app.finance.routes import calculate_cogs_fifo
from app.models import (
    CashAccount,
    CashTransaction,
    CompanyProfile,
    Customer,
    FinanceArticle,
    InventoryBatch,
    Payment,
    PaymentRequest,
    Product,
    SalesOrder,
    SalesOrderItem,
    Supplier,
    User,
)


class FinanceModuleTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()

        with self.app.app_context():
            user = User.query.filter_by(username="finance").first()
            if user is None:
                user = User(username="finance", email="finance@mebelgrad.local", is_finance=True)
                user.set_password("finance123")
                db.session.add(user)

            customer = Customer.query.filter_by(name="Test Customer").first()
            if customer is None:
                customer = Customer(name="Test Customer", type="legal_entity")
                db.session.add(customer)

            supplier = Supplier.query.filter_by(name="Test Supplier").first()
            if supplier is None:
                supplier = Supplier(name="Test Supplier", inn="1234567890")
                db.session.add(supplier)

            product = Product.query.filter_by(sku="TST-001").first()
            if product is None:
                product = Product(sku="TST-001", name="Test Product", retail_price=1000.0)
                db.session.add(product)

            article = FinanceArticle.query.filter_by(name="Test Article").first()
            if article is None:
                article = FinanceArticle(
                    name="Test Article",
                    report_type="both",
                    cash_flow_group="operational",
                    pnl_group="other",
                )
                db.session.add(article)

            db.session.commit()
            self.user_id = user.id
            self.customer_id = customer.id
            self.supplier_id = supplier.id
            self.product_id = product.id
            self.article_id = article.id

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

    def test_finance_pages_open_for_finance_user(self):
        self.login()
        urls = [
            "/finance/",
            "/finance/cash-flow",
            "/finance/profitability-report",
            "/finance/management-balance",
            "/finance/budget",
            "/finance/plan-fact-analysis",
            "/finance/bdds/forecast",
            "/finance/settlements",
            "/finance/bdr",
            "/finance/integrations",
            "/finance/payment-requests",
            "/finance/dashboard",
            "/finance/help",
        ]
        for url in urls:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)

        finance_index = self.client.get("/finance/").get_data(as_text=True)
        self.assertIn("Рабочее место финансиста", finance_index)
        for href in [
            "/finance/bdds/forecast",
            "/finance/settlements",
            "/finance/bdr",
            "/finance/dashboard",
            "/finance/help",
        ]:
            self.assertIn(f'href="{href}"', finance_index)
        self.assertIn("Финансовый дашборд", self.client.get("/finance/dashboard").get_data(as_text=True))

    def test_seeded_company_assets_use_external_urls(self):
        with self.app.app_context():
            company = CompanyProfile.query.first()
            self.assertEqual(
                company.seal_url,
                "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQAM2ekfbi4aBiiUKUq6NJLKjJAorMhwJiTqQ&s",
            )
            self.assertEqual(
                company.signature_url,
                "https://upload.wikimedia.org/wikipedia/commons/2/2c/GalkinAI-signature.png",
            )
            self.assertEqual(
                company.logo_url,
                "https://alaci.kz/wp-content/uploads/2022/03/logo-mebelgrad-e1646908558844.png",
            )

    def test_calculate_cogs_fifo(self):
        with self.app.app_context():
            now = datetime(2026, 6, 10)
            batch = InventoryBatch(
                product_id=self.product_id,
                received_date=now - timedelta(days=2),
                quantity=10,
                unit_cost=100.0,
                transport_cost=50.0,
            )
            db.session.add(batch)
            order = SalesOrder(
                order_number="SO-FIFO-001",
                customer_id=self.customer_id,
                order_date=now,
                status="completed",
                total_amount=300.0,
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

            cogs = calculate_cogs_fifo(datetime(2026, 6, 1), datetime(2026, 7, 1))
            self.assertAlmostEqual(cogs, 210.0, places=2)

    def test_cash_flow_uses_opening_balance_and_cash_transactions(self):
        with self.app.app_context():
            before = finance_services.build_cash_flow_report("2026-06")["closing_balance"]
            account = CashAccount(
                name="Test Cash Flow Account",
                account_type="demo",
                currency="RUB",
                opening_balance=1000.0,
                opening_date=datetime(2026, 6, 1),
                is_active=True,
            )
            db.session.add(account)
            db.session.flush()
            db.session.add(
                CashTransaction(
                    account_id=account.id,
                    date=datetime(2026, 6, 5),
                    amount=500.0,
                    direction="incoming",
                    article_id=self.article_id,
                    status="executed",
                    source="manual",
                    external_ref="test-cf-in",
                )
            )
            db.session.add(
                CashTransaction(
                    account_id=account.id,
                    date=datetime(2026, 6, 7),
                    amount=200.0,
                    direction="outgoing",
                    article_id=self.article_id,
                    status="executed",
                    source="manual",
                    external_ref="test-cf-out",
                )
            )
            db.session.commit()

            report = finance_services.build_cash_flow_report("2026-06")
            self.assertAlmostEqual(report["closing_balance"], before + 1300.0, places=2)

    def test_pnl_revenue_uses_sales_orders_not_payments(self):
        with self.app.app_context():
            june_order = SalesOrder(
                order_number="SO-PNL-JUNE",
                customer_id=self.customer_id,
                order_date=datetime(2026, 6, 10),
                status="completed",
                total_amount=5000.0,
            )
            db.session.add(june_order)
            db.session.flush()
            db.session.add(
                SalesOrderItem(
                    sales_order_id=june_order.id,
                    product_id=self.product_id,
                    quantity=1,
                    unit_price=5000.0,
                    cost_price=3000.0,
                )
            )

            may_order = SalesOrder(
                order_number="SO-PNL-MAY",
                customer_id=self.customer_id,
                order_date=datetime(2026, 5, 25),
                status="completed",
                total_amount=7000.0,
            )
            db.session.add(may_order)
            db.session.flush()
            db.session.add(
                Payment(
                    sales_order_id=may_order.id,
                    amount=7000.0,
                    payment_date=datetime(2026, 6, 12),
                    status="completed",
                )
            )
            db.session.commit()

            pnl = finance_services.calculate_pnl("2026-06")
            self.assertAlmostEqual(pnl["revenue"], 5000.0, places=2)

    def test_demo_bank_import_skips_duplicates(self):
        self.login()
        first = self.client.post(
            "/finance/integrations/import-bank-demo",
            data={},
            follow_redirects=True,
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            "/finance/integrations/import-bank-demo",
            data={},
            follow_redirects=True,
        )
        self.assertEqual(second.status_code, 200)
        self.assertIn("пропущено дублей 3", second.get_data(as_text=True))

        with self.app.app_context():
            count = CashTransaction.query.filter(
                CashTransaction.external_ref.like("bank-demo-2026-04-%")
            ).count()
            self.assertEqual(count, 3)

    def test_payment_request_approval_and_paid_creates_transaction(self):
        self.login()
        with self.app.app_context():
            request_item = PaymentRequest(
                date=datetime(2026, 6, 1),
                due_date=datetime(2026, 6, 5),
                amount=1234.0,
                direction="outgoing",
                article_id=self.article_id,
                supplier_id=self.supplier_id,
                status="pending",
                priority="normal",
                comment="Test payment request",
                created_by=self.user_id,
            )
            db.session.add(request_item)
            db.session.commit()
            request_id = request_item.id

        approve = self.client.post(
            f"/finance/payment-requests/{request_id}/approve",
            follow_redirects=True,
        )
        self.assertEqual(approve.status_code, 200)

        paid = self.client.post(
            f"/finance/payment-requests/{request_id}/mark-paid",
            follow_redirects=True,
        )
        self.assertEqual(paid.status_code, 200)

        with self.app.app_context():
            request_item = db.session.get(PaymentRequest, request_id)
            tx = CashTransaction.query.filter_by(external_ref=f"payment_request:{request_id}").first()
            self.assertEqual(request_item.status, "paid")
            self.assertIsNotNone(tx)
            self.assertAlmostEqual(tx.amount, 1234.0, places=2)


if __name__ == "__main__":
    unittest.main()
