import unittest

from app import create_app, db
from app.models import Customer, Product, User


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

