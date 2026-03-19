import os
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, render_template
from flask_jwt_extended import JWTManager
from flask_login import LoginManager, current_user

from app.models import (
    BudgetItem,
    Customer,
    Employee,
    Payment,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    SalesOrder,
    SalesOrderItem,
    Stock,
    Supplier,
    User,
    db,
)
from config import config


load_dotenv()

login_manager = LoginManager()
jwt = JWTManager()


def create_app(config_name="development"):
    app = Flask(
        __name__,
        template_folder=os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates"
        ),
    )
    app.config.from_object(config.get(config_name, config["default"]))

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    jwt.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Пожалуйста, выполните вход в систему."
    login_manager.login_message_category = "warning"

    register_blueprints(app)
    register_routes(app)

    with app.app_context():
        db.create_all()
        seed_database()

    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def register_blueprints(app):
    from app.auth import auth_bp
    from app.data_mdm import mdm_bp
    from app.finance import finance_bp
    from app.sales_demo import sales_bp
    from app.warehouse_demo import warehouse_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(mdm_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(warehouse_bp)


def register_routes(app):
    @app.context_processor
    def inject_layout_context():
        return {"current_year": datetime.now().year}

    @app.route("/")
    def index():
        products = Product.query.all()
        customers = Customer.query.all()
        employees = Employee.query.all()
        return render_template(
            "index.html",
            current_user=current_user,
            products_count=len(products),
            active_products_count=sum(1 for product in products if product.is_active),
            low_stock_count=sum(1 for product in products if product.qty_on_hand <= 5),
            total_on_hand=sum(product.qty_on_hand for product in products),
            customers_count=len(customers),
            legal_customers_count=sum(
                1 for customer in customers if customer.type == "legal_entity"
            ),
            suppliers_count=Supplier.query.count(),
            employees_count=len(employees),
            active_employees_count=sum(1 for employee in employees if employee.is_active),
            payments_count=Payment.query.count(),
            purchase_orders_count=PurchaseOrder.query.count(),
            unpaid_purchase_orders=PurchaseOrder.query.filter_by(is_paid=False).count(),
            sales_orders_count=SalesOrder.query.count(),
            budget_items_count=BudgetItem.query.count(),
        )

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404


def seed_database():
    def ensure_user(username, email, password, is_admin=False, is_finance=False):
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(
                username=username,
                email=email,
                is_admin=is_admin,
                is_finance=is_finance,
            )
            user.set_password(password)
            db.session.add(user)
        return user

    ensure_user("admin", "admin@mebelgrad.local", "admin123", is_admin=True, is_finance=True)
    ensure_user("finance", "finance@mebelgrad.local", "finance123", is_finance=True)

    customers_data = [
        {"name": "ООО СтройКорп", "phone": "+7 (800) 123-45-67", "email": "info@stroycorp.ru", "type": "legal_entity"},
        {"name": "ООО Северный Офис", "phone": "+7 (812) 555-11-20", "email": "office@sever-office.ru", "type": "legal_entity"},
        {"name": "Гостиница Нева", "phone": "+7 (812) 555-22-10", "email": "purchases@hotel-neva.ru", "type": "legal_entity"},
        {"name": "Кафе Лофт", "phone": "+7 (812) 555-30-14", "email": "loft@cafe.ru", "type": "legal_entity"},
        {"name": "ИП Дизайн Студия Интерьер", "phone": "+7 (921) 555-88-10", "email": "projects@interior-pro.ru", "type": "legal_entity"},
        {"name": "ООО Бизнес-Парк Центр", "phone": "+7 (812) 555-77-45", "email": "tender@business-park.ru", "type": "legal_entity"},
        {"name": "Иван Петров", "phone": "+7 (900) 111-22-33", "email": "ivan.petrov@mail.ru", "type": "individual"},
        {"name": "Ольга Смирнова", "phone": "+7 (911) 222-41-55", "email": "smirnova@mail.ru", "type": "individual"},
        {"name": "Сергей Николаев", "phone": "+7 (931) 111-54-88", "email": "nikolaev@mail.ru", "type": "individual"},
        {"name": "Марина Орлова", "phone": "+7 (921) 876-13-44", "email": "orlovamarina@mail.ru", "type": "individual"},
        {"name": "ООО Атриум Офис", "phone": "+7 (812) 555-81-61", "email": "buy@atrium-office.ru", "type": "legal_entity"},
        {"name": "ООО Гранд Холл", "phone": "+7 (812) 555-19-24", "email": "procurement@grandhall.ru", "type": "legal_entity"},
        {"name": "Гостевой дом Маяк", "phone": "+7 (401) 255-17-20", "email": "info@mayak-house.ru", "type": "legal_entity"},
        {"name": "ИП Кафе Терраса", "phone": "+7 (921) 730-18-22", "email": "terrace@cafe.ru", "type": "legal_entity"},
        {"name": "Наталья Лебедева", "phone": "+7 (952) 332-90-11", "email": "lebedeva@mail.ru", "type": "individual"},
        {"name": "Алексей Волков", "phone": "+7 (911) 485-63-90", "email": "avolkov@mail.ru", "type": "individual"},
        {"name": "Виктория Демидова", "phone": "+7 (981) 500-70-40", "email": "demidova.v@mail.ru", "type": "individual"},
        {"name": "ООО Северный Берег", "phone": "+7 (812) 555-41-12", "email": "project@northshore.ru", "type": "legal_entity"},
    ]
    suppliers_data = [
        {"name": "ООО МебельИмпорт", "phone": "+7 (495) 123-45-67", "email": "info@mebel-import.ru", "inn": "7701234567"},
        {"name": "АО ДеревоПродукт", "phone": "+7 (495) 987-65-43", "email": "sales@derevo-product.ru", "inn": "7702987654"},
        {"name": "ООО СеверФурнитура", "phone": "+7 (383) 555-14-10", "email": "trade@sever-furnitura.ru", "inn": "5401122334"},
        {"name": "ООО ТекстильСнаб", "phone": "+7 (343) 555-41-22", "email": "supply@textil-snab.ru", "inn": "6604455667"},
        {"name": "ООО Кухни Регион", "phone": "+7 (846) 555-78-19", "email": "orders@kitchen-region.ru", "inn": "6319988776"},
        {"name": "ООО Логистика Волга", "phone": "+7 (845) 555-70-33", "email": "service@volga-log.ru", "inn": "6456677881"},
        {"name": "ООО Фурнитура Профи", "phone": "+7 (812) 440-11-22", "email": "sale@furnitura-profi.ru", "inn": "7812345678"},
        {"name": "ООО МеталлКаркас", "phone": "+7 (831) 455-32-10", "email": "b2b@metal-carcass.ru", "inn": "5258123476"},
        {"name": "ООО ЭкоПанель", "phone": "+7 (351) 488-60-77", "email": "trade@ecopanel.ru", "inn": "7456123980"},
        {"name": "ООО ТрансСервис Север", "phone": "+7 (815) 245-63-11", "email": "dispatch@transnorth.ru", "inn": "5198765432"},
    ]
    employees_data = [
        {"name": "Андрей Кузьмин", "position": "Руководитель", "phone": "+7 (900) 111-00-01", "email": "owner@mebelgrad.local"},
        {"name": "Наталья Власова", "position": "Коммерческий управляющий", "phone": "+7 (900) 111-00-02", "email": "commercial@mebelgrad.local"},
        {"name": "Мария Кузнецова", "position": "Главный бухгалтер", "phone": "+7 (900) 111-00-03", "email": "chief.accountant@mebelgrad.local"},
        {"name": "Ирина Соколова", "position": "Бухгалтер", "phone": "+7 (900) 111-00-04", "email": "finance@mebelgrad.local"},
        {"name": "Олег Воронов", "position": "Заведующий складом", "phone": "+7 (900) 111-00-05", "email": "warehouse@mebelgrad.local"},
        {"name": "Павел Сергеев", "position": "Специалист по закупкам", "phone": "+7 (900) 111-00-06", "email": "procurement@mebelgrad.local"},
        {"name": "Анна Миронова", "position": "Менеджер по продажам", "phone": "+7 (900) 111-00-07", "email": "sales1@mebelgrad.local"},
        {"name": "Дмитрий Захаров", "position": "Менеджер по корпоративным продажам", "phone": "+7 (900) 111-00-08", "email": "b2b@mebelgrad.local"},
        {"name": "Екатерина Павлова", "position": "Администратор данных", "phone": "+7 (900) 111-00-09", "email": "mdm@mebelgrad.local"},
        {"name": "Светлана Орехова", "position": "Аналитик", "phone": "+7 (900) 111-00-10", "email": "analytics@mebelgrad.local"},
        {"name": "Елена Крылова", "position": "Администратор офиса", "phone": "+7 (900) 111-00-11", "email": "office@mebelgrad.local"},
        {"name": "Татьяна Белова", "position": "Специалист по кадрам", "phone": "+7 (900) 111-00-12", "email": "hr@mebelgrad.local"},
        {"name": "Максим Ершов", "position": "Юрисконсульт", "phone": "+7 (900) 111-00-13", "email": "legal@mebelgrad.local"},
        {"name": "Денис Громов", "position": "Менеджер по тендерам", "phone": "+7 (900) 111-00-14", "email": "tender@mebelgrad.local"},
        {"name": "Алина Федорова", "position": "Дизайнер-консультант", "phone": "+7 (900) 111-00-15", "email": "design@mebelgrad.local"},
        {"name": "Виктор Чернов", "position": "Старший продавец-консультант", "phone": "+7 (900) 111-00-16", "email": "sales2@mebelgrad.local"},
        {"name": "Юлия Корнеева", "position": "Продавец-консультант", "phone": "+7 (900) 111-00-17", "email": "sales3@mebelgrad.local"},
        {"name": "Роман Егоров", "position": "Продавец-консультант", "phone": "+7 (900) 111-00-18", "email": "sales4@mebelgrad.local"},
        {"name": "Лилия Самойлова", "position": "Менеджер клиентских заказов", "phone": "+7 (900) 111-00-19", "email": "orders1@mebelgrad.local"},
        {"name": "Кирилл Осипов", "position": "Менеджер клиентских заказов", "phone": "+7 (900) 111-00-20", "email": "orders2@mebelgrad.local"},
        {"name": "Артем Доронин", "position": "Кладовщик", "phone": "+7 (900) 111-00-21", "email": "store1@mebelgrad.local"},
        {"name": "Игорь Мещеряков", "position": "Кладовщик", "phone": "+7 (900) 111-00-22", "email": "store2@mebelgrad.local"},
        {"name": "Андрей Демин", "position": "Комплектовщик", "phone": "+7 (900) 111-00-23", "email": "picker1@mebelgrad.local"},
        {"name": "Руслан Никитин", "position": "Комплектовщик", "phone": "+7 (900) 111-00-24", "email": "picker2@mebelgrad.local"},
        {"name": "Николай Дроздов", "position": "Водитель-экспедитор", "phone": "+7 (900) 111-00-25", "email": "driver1@mebelgrad.local"},
        {"name": "Евгений Герасимов", "position": "Водитель-экспедитор", "phone": "+7 (900) 111-00-26", "email": "driver2@mebelgrad.local"},
        {"name": "Алексей Мартынов", "position": "Специалист по логистике", "phone": "+7 (900) 111-00-27", "email": "logistics@mebelgrad.local"},
        {"name": "Полина Романова", "position": "Маркетолог", "phone": "+7 (900) 111-00-28", "email": "marketing@mebelgrad.local"},
        {"name": "Валерия Киселева", "position": "Контент-менеджер", "phone": "+7 (900) 111-00-29", "email": "content@mebelgrad.local"},
        {"name": "Оксана Гаврилова", "position": "Бухгалтер по расчетам", "phone": "+7 (900) 111-00-30", "email": "accounting2@mebelgrad.local"},
        {"name": "Галина Морозова", "position": "Кассир-операционист", "phone": "+7 (900) 111-00-31", "email": "cashdesk@mebelgrad.local"},
        {"name": "Сергей Лапшин", "position": "Сборщик мебели", "phone": "+7 (900) 111-00-32", "email": "assembly1@mebelgrad.local"},
        {"name": "Илья Шевцов", "position": "Сборщик мебели", "phone": "+7 (900) 111-00-33", "email": "assembly2@mebelgrad.local"},
        {"name": "Антон Рубцов", "position": "Сервисный инженер", "phone": "+7 (900) 111-00-34", "email": "service@mebelgrad.local"},
    ]
    products_data = [
        {"sku": "STOL-001", "name": "Стол письменный прямоугольный", "unit": "шт", "retail_price": 5600.00},
        {"sku": "STUL-002", "name": "Стул мягкий универсальный", "unit": "шт", "retail_price": 2250.00},
        {"sku": "SHKAF-003", "name": "Шкаф книжный высокий", "unit": "шт", "retail_price": 19900.00},
        {"sku": "DIVAN-004", "name": "Диван двухместный тканевый", "unit": "шт", "retail_price": 49900.00},
        {"sku": "KROVAT-005", "name": "Кровать двуспальная с основанием", "unit": "шт", "retail_price": 28500.00},
        {"sku": "KUHNYA-006", "name": "Кухонный гарнитур базовый", "unit": "компл", "retail_price": 124000.00},
        {"sku": "TUMBA-007", "name": "Тумба прикроватная", "unit": "шт", "retail_price": 6500.00},
        {"sku": "KRESLO-008", "name": "Кресло офисное эргономичное", "unit": "шт", "retail_price": 9300.00},
        {"sku": "STELL-009", "name": "Стеллаж металлический", "unit": "шт", "retail_price": 14800.00},
        {"sku": "KOMOD-010", "name": "Комод четырехсекционный", "unit": "шт", "retail_price": 16900.00},
        {"sku": "PEREG-011", "name": "Перегородка офисная", "unit": "шт", "retail_price": 12800.00},
        {"sku": "POLKA-012", "name": "Полка настенная", "unit": "шт", "retail_price": 2850.00},
        {"sku": "VITRINA-013", "name": "Витрина для гостиной", "unit": "шт", "retail_price": 21900.00},
        {"sku": "BANKET-014", "name": "Банкетка для прихожей", "unit": "шт", "retail_price": 7600.00},
        {"sku": "STOIKA-015", "name": "Стойка ресепшн", "unit": "шт", "retail_price": 36400.00},
        {"sku": "MATRAS-016", "name": "Матрас ортопедический", "unit": "шт", "retail_price": 18500.00},
        {"sku": "STOLKOF-017", "name": "Стол кофейный", "unit": "шт", "retail_price": 9800.00},
        {"sku": "PUF-018", "name": "Пуф мягкий", "unit": "шт", "retail_price": 5400.00},
        {"sku": "KONSOL-019", "name": "Консоль декоративная", "unit": "шт", "retail_price": 14200.00},
        {"sku": "PANEL-020", "name": "Панель акустическая настенная", "unit": "шт", "retail_price": 6900.00},
    ]

    customer_map = {}
    for item in customers_data:
        customer = Customer.query.filter_by(name=item["name"]).first()
        if customer is None:
            customer = Customer(**item, is_active=True)
            db.session.add(customer)
        else:
            customer.phone = item["phone"]
            customer.email = item["email"]
            customer.type = item["type"]
            customer.is_active = True
        customer_map[item["name"]] = customer

    supplier_map = {}
    for item in suppliers_data:
        supplier = Supplier.query.filter_by(inn=item["inn"]).first()
        if supplier is None:
            supplier = Supplier(**item, is_active=True)
            db.session.add(supplier)
        else:
            supplier.name = item["name"]
            supplier.phone = item["phone"]
            supplier.email = item["email"]
            supplier.is_active = True
        supplier_map[item["name"]] = supplier

    for item in employees_data:
        employee = Employee.query.filter_by(name=item["name"]).first()
        if employee is None:
            db.session.add(Employee(**item, is_active=True))
        else:
            employee.position = item["position"]
            employee.phone = item["phone"]
            employee.email = item["email"]
            employee.is_active = True

    product_map = {}
    for item in products_data:
        product = Product.query.filter_by(sku=item["sku"]).first()
        if product is None:
            product = Product(**item, is_active=True)
            db.session.add(product)
        else:
            product.name = item["name"]
            product.unit = item["unit"]
            product.retail_price = item["retail_price"]
            product.is_active = True
        product_map[item["sku"]] = product

    db.session.flush()

    stock_levels = {
        "STOL-001": (42, 6),
        "STUL-002": (118, 14),
        "SHKAF-003": (17, 2),
        "DIVAN-004": (9, 2),
        "KROVAT-005": (11, 1),
        "KUHNYA-006": (6, 1),
        "TUMBA-007": (37, 4),
        "KRESLO-008": (55, 8),
        "STELL-009": (19, 3),
        "KOMOD-010": (16, 2),
        "PEREG-011": (28, 5),
        "POLKA-012": (73, 9),
        "VITRINA-013": (8, 1),
        "BANKET-014": (22, 4),
        "STOIKA-015": (5, 1),
        "MATRAS-016": (14, 2),
        "STOLKOF-017": (18, 3),
        "PUF-018": (26, 5),
        "KONSOL-019": (9, 1),
        "PANEL-020": (44, 6),
    }
    for sku, values in stock_levels.items():
        product = product_map[sku]
        stock = Stock.query.filter_by(product_id=product.id).first()
        if stock is None:
            stock = Stock(product_id=product.id)
            db.session.add(stock)
        stock.qty_on_hand = values[0]
        stock.qty_reserved = values[1]

    purchase_orders_data = [
        {"order_number": "PO-2601-001", "supplier": "АО ДеревоПродукт", "order_date": datetime(2026, 1, 5, 10, 15), "status": "completed", "is_paid": True, "items": [("STOL-001", 20, 3300.00), ("STUL-002", 60, 1500.00), ("SHKAF-003", 8, 12900.00)]},
        {"order_number": "PO-2601-002", "supplier": "ООО СеверФурнитура", "order_date": datetime(2026, 1, 18, 12, 40), "status": "completed", "is_paid": True, "items": [("TUMBA-007", 20, 4100.00), ("KRESLO-008", 25, 6200.00)]},
        {"order_number": "PO-2601-003", "supplier": "ООО Кухни Регион", "order_date": datetime(2026, 1, 29, 9, 20), "status": "completed", "is_paid": True, "items": [("KUHNYA-006", 3, 88000.00), ("KOMOD-010", 12, 10900.00)]},
        {"order_number": "PO-2602-001", "supplier": "ООО МебельИмпорт", "order_date": datetime(2026, 2, 7, 11, 5), "status": "received", "is_paid": False, "items": [("DIVAN-004", 6, 32500.00), ("KROVAT-005", 7, 19000.00)]},
        {"order_number": "PO-2602-002", "supplier": "ООО ТекстильСнаб", "order_date": datetime(2026, 2, 19, 15, 30), "status": "completed", "is_paid": True, "items": [("KRESLO-008", 18, 6100.00), ("DIVAN-004", 4, 31800.00)]},
        {"order_number": "PO-2602-003", "supplier": "ООО Логистика Волга", "order_date": datetime(2026, 2, 24, 16, 10), "status": "completed", "is_paid": True, "items": [("PEREG-011", 10, 8600.00), ("POLKA-012", 30, 1700.00)]},
        {"order_number": "PO-2603-001", "supplier": "АО ДеревоПродукт", "order_date": datetime(2026, 3, 3, 10, 0), "status": "pending", "is_paid": False, "items": [("STELL-009", 10, 9800.00), ("PEREG-011", 12, 8500.00)]},
        {"order_number": "PO-2603-002", "supplier": "ООО СеверФурнитура", "order_date": datetime(2026, 3, 12, 14, 30), "status": "pending", "is_paid": False, "items": [("STUL-002", 40, 1490.00), ("POLKA-012", 25, 1650.00)]},
        {"order_number": "PO-2603-003", "supplier": "ООО Кухни Регион", "order_date": datetime(2026, 3, 17, 9, 45), "status": "received", "is_paid": False, "items": [("KUHNYA-006", 2, 87500.00), ("KOMOD-010", 8, 10800.00)]},
        {"order_number": "PO-2602-004", "supplier": "ООО Фурнитура Профи", "order_date": datetime(2026, 2, 26, 11, 25), "status": "completed", "is_paid": True, "items": [("VITRINA-013", 5, 14900.00), ("BANKET-014", 14, 4300.00)]},
        {"order_number": "PO-2603-004", "supplier": "ООО ЭкоПанель", "order_date": datetime(2026, 3, 10, 13, 15), "status": "received", "is_paid": False, "items": [("PANEL-020", 40, 3700.00), ("STOIKA-015", 3, 22800.00)]},
        {"order_number": "PO-2603-005", "supplier": "ООО МеталлКаркас", "order_date": datetime(2026, 3, 18, 11, 40), "status": "pending", "is_paid": False, "items": [("KONSOL-019", 6, 9100.00), ("STELL-009", 8, 9700.00)]},
    ]

    for item in purchase_orders_data:
        if PurchaseOrder.query.filter_by(order_number=item["order_number"]).first():
            continue
        purchase_order = PurchaseOrder(
            order_number=item["order_number"],
            supplier_id=supplier_map[item["supplier"]].id,
            order_date=item["order_date"],
            status=item["status"],
            is_paid=item["is_paid"],
        )
        db.session.add(purchase_order)
        db.session.flush()
        total_amount = 0
        for sku, quantity, unit_cost in item["items"]:
            total_amount += quantity * unit_cost
            db.session.add(
                PurchaseOrderItem(
                    purchase_order_id=purchase_order.id,
                    product_id=product_map[sku].id,
                    quantity=quantity,
                    unit_cost=unit_cost,
                )
            )
        purchase_order.total_amount = total_amount

    sales_orders_data = [
        {"order_number": "SO-2601-001", "customer": "ООО Северный Офис", "order_date": datetime(2026, 1, 9, 13, 10), "status": "completed", "payment": (datetime(2026, 1, 11, 15, 30), "FN-2026-0101"), "items": [("KRESLO-008", 6, 9500.00, 6200.00), ("STELL-009", 3, 14800.00, 9800.00), ("PEREG-011", 2, 12900.00, 8600.00)]},
        {"order_number": "SO-2601-002", "customer": "Иван Петров", "order_date": datetime(2026, 1, 14, 11, 25), "status": "completed", "payment": (datetime(2026, 1, 14, 17, 40), "FN-2026-0102"), "items": [("STOL-001", 1, 5600.00, 3300.00), ("STUL-002", 4, 2300.00, 1500.00)]},
        {"order_number": "SO-2601-003", "customer": "Гостиница Нева", "order_date": datetime(2026, 1, 22, 9, 55), "status": "completed", "payment": (datetime(2026, 1, 25, 12, 10), "FN-2026-0103"), "items": [("KROVAT-005", 3, 28500.00, 19000.00), ("TUMBA-007", 6, 6400.00, 4100.00)]},
        {"order_number": "SO-2602-001", "customer": "Кафе Лофт", "order_date": datetime(2026, 2, 3, 16, 5), "status": "completed", "payment": (datetime(2026, 2, 4, 10, 45), "FN-2026-0201"), "items": [("STOL-001", 4, 5900.00, 3300.00), ("STUL-002", 16, 2200.00, 1500.00)]},
        {"order_number": "SO-2602-002", "customer": "Марина Орлова", "order_date": datetime(2026, 2, 10, 14, 15), "status": "completed", "payment": (datetime(2026, 2, 10, 18, 5), "FN-2026-0202"), "items": [("DIVAN-004", 1, 48900.00, 32500.00), ("KOMOD-010", 1, 16400.00, 10900.00)]},
        {"order_number": "SO-2602-003", "customer": "ООО СтройКорп", "order_date": datetime(2026, 2, 16, 10, 30), "status": "completed", "payment": (datetime(2026, 2, 18, 11, 15), "FN-2026-0203"), "items": [("KUHNYA-006", 1, 124000.00, 88000.00), ("POLKA-012", 4, 2800.00, 1700.00)]},
        {"order_number": "SO-2602-004", "customer": "ООО Бизнес-Парк Центр", "order_date": datetime(2026, 2, 27, 15, 0), "status": "completed", "payment": (datetime(2026, 3, 2, 10, 0), "FN-2026-0204"), "items": [("KRESLO-008", 12, 9300.00, 6200.00), ("PEREG-011", 5, 12800.00, 8600.00)]},
        {"order_number": "SO-2603-001", "customer": "Сергей Николаев", "order_date": datetime(2026, 3, 5, 12, 20), "status": "completed", "payment": (datetime(2026, 3, 5, 16, 55), "FN-2026-0301"), "items": [("SHKAF-003", 1, 19900.00, 12900.00), ("POLKA-012", 2, 2800.00, 1700.00)]},
        {"order_number": "SO-2603-002", "customer": "ИП Дизайн Студия Интерьер", "order_date": datetime(2026, 3, 8, 13, 0), "status": "completed", "payment": (datetime(2026, 3, 9, 9, 30), "FN-2026-0302"), "items": [("KOMOD-010", 3, 16900.00, 10900.00), ("TUMBA-007", 4, 6500.00, 4100.00)]},
        {"order_number": "SO-2603-003", "customer": "ООО Северный Офис", "order_date": datetime(2026, 3, 12, 17, 10), "status": "pending", "payment": None, "items": [("KRESLO-008", 8, 9300.00, 6200.00), ("STELL-009", 2, 14800.00, 9800.00)]},
        {"order_number": "SO-2603-004", "customer": "Ольга Смирнова", "order_date": datetime(2026, 3, 15, 11, 45), "status": "completed", "payment": (datetime(2026, 3, 16, 15, 10), "FN-2026-0304"), "items": [("DIVAN-004", 1, 49900.00, 32500.00), ("STOL-001", 1, 5700.00, 3300.00)]},
        {"order_number": "SO-2603-005", "customer": "Кафе Лофт", "order_date": datetime(2026, 3, 19, 10, 5), "status": "completed", "payment": (datetime(2026, 3, 19, 18, 40), "FN-2026-0305"), "items": [("STUL-002", 10, 2250.00, 1500.00), ("POLKA-012", 6, 2850.00, 1700.00)]},
        {"order_number": "SO-2601-004", "customer": "ООО Атриум Офис", "order_date": datetime(2026, 1, 27, 14, 40), "status": "completed", "payment": (datetime(2026, 1, 29, 16, 20), "FN-2026-0104"), "items": [("STOIKA-015", 1, 36400.00, 22800.00), ("KRESLO-008", 4, 9300.00, 6200.00)]},
        {"order_number": "SO-2601-005", "customer": "Наталья Лебедева", "order_date": datetime(2026, 1, 30, 18, 5), "status": "completed", "payment": (datetime(2026, 1, 30, 18, 40), "FN-2026-0105"), "items": [("BANKET-014", 1, 7600.00, 4300.00), ("PUF-018", 2, 5400.00, 2900.00)]},
        {"order_number": "SO-2602-005", "customer": "Гостевой дом Маяк", "order_date": datetime(2026, 2, 21, 12, 15), "status": "completed", "payment": (datetime(2026, 2, 22, 11, 50), "FN-2026-0205"), "items": [("KROVAT-005", 4, 28600.00, 19000.00), ("MATRAS-016", 4, 18500.00, 11200.00)]},
        {"order_number": "SO-2602-006", "customer": "Алексей Волков", "order_date": datetime(2026, 2, 28, 13, 25), "status": "completed", "payment": (datetime(2026, 2, 28, 17, 35), "FN-2026-0206"), "items": [("STOLKOF-017", 1, 9800.00, 5400.00), ("VITRINA-013", 1, 21900.00, 14900.00)]},
        {"order_number": "SO-2603-006", "customer": "ООО Гранд Холл", "order_date": datetime(2026, 3, 11, 10, 10), "status": "completed", "payment": (datetime(2026, 3, 13, 12, 0), "FN-2026-0306"), "items": [("VITRINA-013", 3, 22300.00, 14900.00), ("KONSOL-019", 2, 14200.00, 9100.00)]},
        {"order_number": "SO-2603-007", "customer": "Виктория Демидова", "order_date": datetime(2026, 3, 17, 14, 35), "status": "completed", "payment": (datetime(2026, 3, 17, 19, 15), "FN-2026-0307"), "items": [("PUF-018", 2, 5400.00, 2900.00), ("BANKET-014", 1, 7600.00, 4300.00)]},
        {"order_number": "SO-2603-008", "customer": "ООО Северный Берег", "order_date": datetime(2026, 3, 19, 12, 55), "status": "pending", "payment": None, "items": [("PANEL-020", 18, 6900.00, 3700.00), ("PEREG-011", 6, 12800.00, 8600.00)]},
    ]

    for item in sales_orders_data:
        if SalesOrder.query.filter_by(order_number=item["order_number"]).first():
            continue
        sales_order = SalesOrder(
            order_number=item["order_number"],
            customer_id=customer_map[item["customer"]].id,
            order_date=item["order_date"],
            status=item["status"],
        )
        db.session.add(sales_order)
        db.session.flush()
        total_amount = 0
        for sku, quantity, unit_price, cost_price in item["items"]:
            total_amount += quantity * unit_price
            db.session.add(
                SalesOrderItem(
                    sales_order_id=sales_order.id,
                    product_id=product_map[sku].id,
                    quantity=quantity,
                    unit_price=unit_price,
                    cost_price=cost_price,
                )
            )
        sales_order.total_amount = total_amount
        if item["payment"] is not None:
            payment_date, receipt = item["payment"]
            db.session.add(
                Payment(
                    sales_order_id=sales_order.id,
                    amount=total_amount,
                    payment_date=payment_date,
                    fiscal_receipt_number=receipt,
                    status="completed",
                )
            )

    budget_items = [
        ("2026-01", "income", "Продажи", 640000.00),
        ("2026-01", "income", "Корпоративные проекты", 220000.00),
        ("2026-01", "income", "Сборка и доставка", 55000.00),
        ("2026-01", "expense", "Закупки", 470000.00),
        ("2026-01", "expense", "Логистика", 48000.00),
        ("2026-01", "expense", "Фонд оплаты труда", 215000.00),
        ("2026-01", "expense", "Маркетинг", 28000.00),
        ("2026-01", "expense", "Аренда", 82000.00),
        ("2026-02", "income", "Продажи", 790000.00),
        ("2026-02", "income", "Корпоративные проекты", 320000.00),
        ("2026-02", "income", "Сборка и доставка", 68000.00),
        ("2026-02", "expense", "Закупки", 560000.00),
        ("2026-02", "expense", "Логистика", 52000.00),
        ("2026-02", "expense", "Фонд оплаты труда", 215000.00),
        ("2026-02", "expense", "Маркетинг", 35000.00),
        ("2026-02", "expense", "Аренда", 82000.00),
        ("2026-03", "income", "Продажи", 720000.00),
        ("2026-03", "income", "Корпоративные проекты", 295000.00),
        ("2026-03", "income", "Сборка и доставка", 61000.00),
        ("2026-03", "expense", "Закупки", 530000.00),
        ("2026-03", "expense", "Логистика", 49000.00),
        ("2026-03", "expense", "Фонд оплаты труда", 215000.00),
        ("2026-03", "expense", "Маркетинг", 26000.00),
        ("2026-03", "expense", "Аренда", 82000.00),
        ("2026-01", "expense", "IT и связь", 22000.00),
        ("2026-01", "expense", "Налоги и комиссии", 37000.00),
        ("2026-02", "expense", "IT и связь", 23000.00),
        ("2026-02", "expense", "Налоги и комиссии", 46000.00),
        ("2026-03", "expense", "IT и связь", 24000.00),
        ("2026-03", "expense", "Налоги и комиссии", 41000.00),
    ]

    for period, item_type, category, planned_amount in budget_items:
        exists = BudgetItem.query.filter_by(
            period=period,
            item_type=item_type,
            category=category,
        ).first()
        if exists is None:
            db.session.add(
                BudgetItem(
                    period=period,
                    item_type=item_type,
                    category=category,
                    planned_amount=planned_amount,
                )
            )

    db.session.commit()
