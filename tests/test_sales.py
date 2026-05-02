import io
import unittest

from app import create_app, db
from app.models import Customer, Product, SalesOrder, SalesOrderAttachment, Stock, User


class SalesModuleTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app("testing")
        self.client = self.app.test_client()
        with self.app.app_context():
            user = User.query.filter_by(username="admin").first()
            if user is None:
                user = User(username="admin", email="admin@mebelgrad.local", is_admin=True)
                user.set_password("admin123")
                db.session.add(user)
            if Customer.query.first() is None:
                db.session.add(Customer(name="Test User", phone="+79990000000", email="test@example.com"))
            if Product.query.first() is None:
                db.session.add(Product(sku="TEST-SALE-1", name="Тестовый товар", retail_price=1000))
            db.session.commit()
            product = Product.query.first()
            if product and not product.stock:
                db.session.add(Stock(product_id=product.id, qty_on_hand=10, qty_reserved=0))
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self):
        return self.client.post(
            "/auth/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=True,
        )

    def test_sales_pages_open(self):
        self.login()
        for path in ["/sales/", "/sales/crm", "/sales/orders"]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_create_and_progress_order(self):
        self.login()
        with self.app.app_context():
            customer = Customer.query.first()
            product = Product.query.first()

        payload = {
            "customer_id": customer.id,
            "delivery_address": "г. Москва, ул. Тестовая, д. 1",
            "items": [{"product_id": product.id, "quantity": 2, "unit_price": 1000}],
        }
        create_resp = self.client.post("/sales/api/orders", json=payload)
        self.assertEqual(create_resp.status_code, 200)
        order_id = create_resp.get_json()["order_id"]

        paid_resp = self.client.post(f"/sales/api/orders/{order_id}/confirm-payment")
        self.assertEqual(paid_resp.status_code, 200)
        self.assertEqual(paid_resp.get_json()["status"], "picking")

        assembled_resp = self.client.post(f"/sales/orders/{order_id}/mark-assembled", follow_redirects=True)
        self.assertEqual(assembled_resp.status_code, 200)
        transit_resp = self.client.post(f"/sales/orders/{order_id}/mark-in-transit", follow_redirects=True)
        self.assertEqual(transit_resp.status_code, 200)
        completed_resp = self.client.post(f"/sales/orders/{order_id}/confirm-delivery", follow_redirects=True)
        self.assertEqual(completed_resp.status_code, 200)

    def test_create_order_with_assembly_and_stock(self):
        self.login()
        with self.app.app_context():
            customer = Customer.query.first()
            product = Product.query.first()

        payload = {
            "customer_id": customer.id,
            "delivery_address": "г. Москва, ул. Тестовая, д. 1",
            "needs_assembly": True,
            "items": [{"product_id": product.id, "quantity": 2, "unit_price": 1000}],
        }
        create_resp = self.client.post("/sales/api/orders", json=payload)
        self.assertEqual(create_resp.status_code, 200)
        data = create_resp.get_json()
        self.assertTrue(data["success"])
        order = SalesOrder.query.get(data["order_id"])
        self.assertTrue(order.needs_assembly)
        self.assertEqual(order.total_amount, 3000)

    def test_cancel_order_with_reason(self):
        self.login()
        with self.app.app_context():
            customer = Customer.query.first()
            product = Product.query.first()

        create_resp = self.client.post(
            "/sales/api/orders",
            json={
                "customer_id": customer.id,
                "delivery_address": "г. Москва, ул. Тестовая, д. 1",
                "items": [{"product_id": product.id, "quantity": 1, "unit_price": 1000}],
            },
        )
        order_id = create_resp.get_json()["order_id"]
        cancel_resp = self.client.post(
            f"/sales/orders/{order_id}/cancel",
            data={"cancel_reason": "Клиент отказался"},
            follow_redirects=True,
        )
        self.assertEqual(cancel_resp.status_code, 200)
        with self.app.app_context():
            order = SalesOrder.query.get(order_id)
            self.assertEqual(order.status, "cancelled")
            self.assertEqual(order.cancel_reason, "Клиент отказался")

    def test_confirm_delivery_requires_attachment(self):
        self.login()
        with self.app.app_context():
            customer = Customer.query.first()
            product = Product.query.first()

        create_resp = self.client.post(
            "/sales/api/orders",
            json={
                "customer_id": customer.id,
                "delivery_address": "г. Москва, ул. Тестовая, д. 1",
                "items": [{"product_id": product.id, "quantity": 1, "unit_price": 1000}],
            },
        )
        order_id = create_resp.get_json()["order_id"]
        self.client.post(f"/sales/api/orders/{order_id}/confirm-payment")
        self.client.post(f"/sales/orders/{order_id}/mark-assembled", follow_redirects=True)
        self.client.post(f"/sales/orders/{order_id}/mark-in-transit", follow_redirects=True)

        delivery_resp = self.client.post(f"/sales/orders/{order_id}/confirm-delivery", follow_redirects=True)
        self.assertEqual(delivery_resp.status_code, 200)
        with self.app.app_context():
            order = SalesOrder.query.get(order_id)
            self.assertEqual(order.status, "in_transit")

