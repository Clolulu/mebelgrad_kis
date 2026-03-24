from functools import wraps

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.data_mdm import mdm_bp
from app.models import Customer, Employee, Product, Supplier, CompanyProfile, db


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Раздел управления данными доступен только администратору.", "danger")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapper


def mdm_readonly_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if (
            not current_user.is_authenticated
            or not (
                current_user.is_admin
                or current_user.is_data_admin
                or current_user.is_data_editor
                or current_user.is_data_viewer
            )
        ):
            flash("Доступ к данным MDM ограничен. Обратитесь к администратору.", "danger")
            return redirect(url_for("index"))
        return view(*args, **kwargs)

    return wrapper


def mdm_editor_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if (
            not current_user.is_authenticated
            or not (
                current_user.is_admin
                or current_user.is_data_admin
                or current_user.is_data_editor
            )
        ):
            flash("Изменение данных MDM разрешено только пользователям с правами редактирования.", "danger")
            return redirect(url_for("mdm.index"))
        return view(*args, **kwargs)

    return wrapper


@mdm_bp.route("/")
@login_required
@mdm_readonly_required
def index():
    products = Product.query.all()
    customers = Customer.query.all()
    suppliers = Supplier.query.all()
    employees = Employee.query.all()
    user_roles = []
    if current_user.is_admin:
        user_roles.append("admin")
    if current_user.is_data_admin:
        user_roles.append("mdm-admin")
    if current_user.is_data_editor:
        user_roles.append("mdm-editor")
    if current_user.is_data_viewer:
        user_roles.append("mdm-viewer")

    return render_template(
        "data_mdm/index.html",
        products_count=len(products),
        active_products_count=sum(1 for product in products if product.is_active),
        low_stock_count=sum(1 for product in products if product.qty_on_hand <= 5),
        customers_count=len(customers),
        legal_customers_count=sum(
            1 for customer in customers if customer.type == "legal_entity"
        ),
        suppliers_count=len(suppliers),
        employees_count=len(employees),
        active_employees_count=sum(1 for employee in employees if employee.is_active),
        incomplete_customer_contacts=sum(
            1 for customer in customers if not customer.phone or not customer.email
        ),
        incomplete_supplier_profiles=sum(
            1
            for supplier in suppliers
            if not supplier.phone or not supplier.email or not supplier.inn
        ),
        incomplete_employee_contacts=sum(
            1 for employee in employees if not employee.phone or not employee.email
        ),
        total_reserved=sum(product.qty_reserved for product in products),
        total_on_hand=sum(product.qty_on_hand for product in products),
        user_roles=user_roles,
    )


@mdm_bp.route("/quality")
@login_required
@mdm_readonly_required
def quality_dashboard():
    products = Product.query.order_by(Product.name.asc()).all()
    customers = Customer.query.order_by(Customer.name.asc()).all()
    suppliers = Supplier.query.order_by(Supplier.name.asc()).all()
    employees = Employee.query.order_by(Employee.name.asc()).all()

    critical_products = [product for product in products if product.qty_on_hand <= 5]
    reserved_products = [product for product in products if product.qty_reserved > 0]
    customers_without_contacts = [
        customer for customer in customers if not customer.phone or not customer.email
    ]
    suppliers_without_profile = [
        supplier
        for supplier in suppliers
        if not supplier.phone or not supplier.email or not supplier.inn
    ]
    employees_without_contacts = [
        employee for employee in employees if not employee.phone or not employee.email
    ]
    inactive_records = {
        "products": sum(1 for product in products if not product.is_active),
        "customers": sum(1 for customer in customers if not customer.is_active),
        "suppliers": sum(1 for supplier in suppliers if not supplier.is_active),
        "employees": sum(1 for employee in employees if not employee.is_active),
    }

    filled_fields = 0
    total_fields = 0
    for customer in customers:
        total_fields += 2
        filled_fields += int(bool(customer.phone)) + int(bool(customer.email))
    for supplier in suppliers:
        total_fields += 3
        filled_fields += (
            int(bool(supplier.phone)) + int(bool(supplier.email)) + int(bool(supplier.inn))
        )
    for employee in employees:
        total_fields += 2
        filled_fields += int(bool(employee.phone)) + int(bool(employee.email))

    completeness_pct = (filled_fields / total_fields * 100) if total_fields else 100
    unit_rows = []
    for unit_name in sorted({product.unit for product in products}):
        unit_products = [product for product in products if product.unit == unit_name]
        unit_rows.append(
            {
                "unit": unit_name,
                "count": len(unit_products),
                "on_hand": sum(product.qty_on_hand for product in unit_products),
                "reserved": sum(product.qty_reserved for product in unit_products),
            }
        )

    return render_template(
        "data_mdm/quality.html",
        completeness_pct=completeness_pct,
        filled_fields=filled_fields,
        total_fields=total_fields,
        inactive_records=inactive_records,
        critical_products=critical_products[:12],
        reserved_products=reserved_products[:12],
        customers_without_contacts=customers_without_contacts[:12],
        suppliers_without_profile=suppliers_without_profile[:12],
        employees_without_contacts=employees_without_contacts[:12],
        unit_rows=unit_rows,
        total_on_hand=sum(product.qty_on_hand for product in products),
        total_reserved=sum(product.qty_reserved for product in products),
        critical_count=len(critical_products),
        reserved_count=len(reserved_products),
    )


@mdm_bp.route("/products")
@login_required
@mdm_readonly_required
def products_list():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    active = request.args.get("active", "")
    unit = request.args.get("unit", "")

    query = Product.query
    if q:
        query = query.filter(or_(Product.sku.ilike(f"%{q}%"), Product.name.ilike(f"%{q}%")))
    if active == "active":
        query = query.filter(Product.is_active.is_(True))
    elif active == "inactive":
        query = query.filter(Product.is_active.is_(False))
    if unit:
        query = query.filter(Product.unit == unit)

    products = query.order_by(Product.name.asc()).paginate(page=page, per_page=20)
    all_products = Product.query.all()
    return render_template(
        "data_mdm/products/list.html",
        products=products,
        q=q,
        active=active,
        unit=unit,
        total_products=len(all_products),
        active_products=sum(1 for item in all_products if item.is_active),
        low_stock_products=sum(1 for item in all_products if item.qty_on_hand <= 5),
    )


@mdm_bp.route("/products/create", methods=["GET", "POST"])
@login_required
@mdm_editor_required
def create_product():
    if request.method == "POST":
        sku = request.form.get("sku", "").strip()
        name = request.form.get("name", "").strip()
        unit = request.form.get("unit", "шт")
        retail_price = request.form.get("retail_price", 0)

        if not sku or not name:
            flash("Артикул и наименование обязательны для заполнения.", "danger")
            return redirect(url_for("mdm.create_product"))

        if Product.query.filter_by(sku=sku).first():
            flash("Товар с таким артикулом уже существует.", "danger")
            return redirect(url_for("mdm.create_product"))

        product = Product(
            sku=sku,
            name=name,
            unit=unit,
            retail_price=float(retail_price or 0),
            is_active=request.form.get("is_active") == "on",
        )
        db.session.add(product)
        db.session.flush()
        from app.models import Stock

        db.session.add(Stock(product_id=product.id, qty_on_hand=0, qty_reserved=0))
        db.session.commit()

        flash("Новая карточка номенклатуры создана.", "success")
        return redirect(url_for("mdm.products_list"))

    return render_template("data_mdm/products/create.html")


@mdm_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
@mdm_editor_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)

    if request.method == "POST":
        product.name = request.form.get("name", product.name).strip()
        product.unit = request.form.get("unit", product.unit)
        product.retail_price = float(request.form.get("retail_price", product.retail_price) or 0)
        product.is_active = request.form.get("is_active") == "on"
        db.session.commit()

        flash("Карточка товара обновлена.", "success")
        return redirect(url_for("mdm.products_list"))

    return render_template("data_mdm/products/edit.html", product=product)


@mdm_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
@mdm_editor_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("Товар удален из мастер-данных.", "info")
    return redirect(url_for("mdm.products_list"))


@mdm_bp.route("/customers")
@login_required
@mdm_readonly_required
def customers_list():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    customer_type = request.args.get("customer_type", "")

    query = Customer.query
    if q:
        query = query.filter(
            or_(
                Customer.name.ilike(f"%{q}%"),
                Customer.phone.ilike(f"%{q}%"),
                Customer.email.ilike(f"%{q}%"),
            )
        )
    if customer_type:
        query = query.filter(Customer.type == customer_type)

    customers = query.order_by(Customer.name.asc()).paginate(page=page, per_page=20)
    return render_template(
        "data_mdm/customers/list.html",
        customers=customers,
        q=q,
        customer_type=customer_type,
        total_customers=Customer.query.count(),
        legal_customers=Customer.query.filter_by(type="legal_entity").count(),
        individual_customers=Customer.query.filter_by(type="individual").count(),
    )


@mdm_bp.route("/customers/create", methods=["GET", "POST"])
@login_required
@mdm_editor_required
def create_customer():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("ФИО или наименование клиента обязательно.", "danger")
            return redirect(url_for("mdm.create_customer"))

        customer = Customer(
            name=name,
            phone=request.form.get("phone", "").strip(),
            email=request.form.get("email", "").strip(),
            type=request.form.get("type", "individual"),
            is_active=request.form.get("is_active") == "on",
        )
        db.session.add(customer)
        db.session.commit()

        flash("Клиентский профиль создан.", "success")
        return redirect(url_for("mdm.customers_list"))

    return render_template("data_mdm/customers/create.html")


@mdm_bp.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
@mdm_editor_required
def edit_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)

    if request.method == "POST":
        customer.name = request.form.get("name", customer.name).strip()
        customer.phone = request.form.get("phone", customer.phone).strip()
        customer.email = request.form.get("email", customer.email).strip()
        customer.type = request.form.get("type", customer.type)
        customer.is_active = request.form.get("is_active") == "on"
        db.session.commit()

        flash("Карточка клиента обновлена.", "success")
        return redirect(url_for("mdm.customers_list"))

    return render_template("data_mdm/customers/edit.html", customer=customer)


@mdm_bp.route("/customers/<int:customer_id>/delete", methods=["POST"])
@login_required
@mdm_editor_required
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    db.session.delete(customer)
    db.session.commit()
    flash("Клиент удален из справочника.", "info")
    return redirect(url_for("mdm.customers_list"))


@mdm_bp.route("/suppliers")
@login_required
@mdm_readonly_required
def suppliers_list():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()

    query = Supplier.query
    if q:
        query = query.filter(
            or_(
                Supplier.name.ilike(f"%{q}%"),
                Supplier.phone.ilike(f"%{q}%"),
                Supplier.email.ilike(f"%{q}%"),
                Supplier.inn.ilike(f"%{q}%"),
            )
        )

    suppliers = query.order_by(Supplier.name.asc()).paginate(page=page, per_page=20)
    return render_template(
        "data_mdm/suppliers/list.html",
        suppliers=suppliers,
        q=q,
        total_suppliers=Supplier.query.count(),
        active_suppliers=Supplier.query.filter_by(is_active=True).count(),
    )


@mdm_bp.route("/suppliers/create", methods=["GET", "POST"])
@login_required
@mdm_editor_required
def create_supplier():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Наименование поставщика обязательно.", "danger")
            return redirect(url_for("mdm.create_supplier"))

        supplier = Supplier(
            name=name,
            phone=request.form.get("phone", "").strip(),
            email=request.form.get("email", "").strip(),
            inn=request.form.get("inn", "").strip(),
            is_active=request.form.get("is_active") == "on",
        )
        db.session.add(supplier)
        db.session.commit()

        flash("Поставщик добавлен в единый справочник.", "success")
        return redirect(url_for("mdm.suppliers_list"))

    return render_template("data_mdm/suppliers/create.html")


@mdm_bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@login_required
@mdm_editor_required
def edit_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)

    if request.method == "POST":
        supplier.name = request.form.get("name", supplier.name).strip()
        supplier.phone = request.form.get("phone", supplier.phone).strip()
        supplier.email = request.form.get("email", supplier.email).strip()
        supplier.inn = request.form.get("inn", supplier.inn).strip()
        supplier.is_active = request.form.get("is_active") == "on"
        db.session.commit()

        flash("Карточка поставщика обновлена.", "success")
        return redirect(url_for("mdm.suppliers_list"))

    return render_template("data_mdm/suppliers/edit.html", supplier=supplier)


@mdm_bp.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
@login_required
@mdm_editor_required
def delete_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    db.session.delete(supplier)
    db.session.commit()
    flash("Поставщик удален из справочника.", "info")
    return redirect(url_for("mdm.suppliers_list"))


@mdm_bp.route("/employees")
@login_required
@mdm_readonly_required
def employees_list():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    role = request.args.get("role", "").strip()

    query = Employee.query
    if q:
        query = query.filter(
            or_(
                Employee.name.ilike(f"%{q}%"),
                Employee.position.ilike(f"%{q}%"),
                Employee.phone.ilike(f"%{q}%"),
                Employee.email.ilike(f"%{q}%"),
            )
        )
    if role:
        query = query.filter(Employee.position.ilike(f"%{role}%"))

    employees = query.order_by(Employee.name.asc()).paginate(page=page, per_page=20)
    return render_template(
        "data_mdm/employees/list.html",
        employees=employees,
        q=q,
        role=role,
        total_employees=Employee.query.count(),
        active_employees=Employee.query.filter_by(is_active=True).count(),
    )


@mdm_bp.route("/employees/create", methods=["GET", "POST"])
@login_required
@mdm_editor_required
def create_employee():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("ФИО сотрудника обязательно.", "danger")
            return redirect(url_for("mdm.create_employee"))

        employee = Employee(
            name=name,
            position=request.form.get("role", request.form.get("position", "")).strip(),
            phone=request.form.get("phone", "").strip(),
            email=request.form.get("email", "").strip(),
            is_active=request.form.get("is_active") == "on",
        )
        db.session.add(employee)
        db.session.commit()

        flash("Сотрудник добавлен в кадровый справочник.", "success")
        return redirect(url_for("mdm.employees_list"))

    return render_template("data_mdm/employees/create.html")


@mdm_bp.route("/employees/<int:employee_id>/edit", methods=["GET", "POST"])
@login_required
@mdm_editor_required
def edit_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)

    if request.method == "POST":
        employee.name = request.form.get("name", employee.name).strip()
        employee.position = request.form.get(
            "role", request.form.get("position", employee.position)
        ).strip()
        employee.phone = request.form.get("phone", employee.phone).strip()
        employee.email = request.form.get("email", employee.email).strip()
        employee.is_active = request.form.get("is_active") == "on"
        db.session.commit()

        flash("Карточка сотрудника обновлена.", "success")
        return redirect(url_for("mdm.employees_list"))

    return render_template("data_mdm/employees/edit.html", employee=employee)


@mdm_bp.route("/employees/<int:employee_id>/delete", methods=["POST"])
@login_required
@mdm_editor_required
def delete_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    db.session.delete(employee)
    db.session.commit()
    flash("Сотрудник удален из кадрового справочника.", "info")
    return redirect(url_for("mdm.employees_list"))


@mdm_bp.route("/stock")
@login_required
@mdm_readonly_required
def stock_list():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    stock_state = request.args.get("stock_state", "")

    query = Product.query
    if q:
        query = query.filter(or_(Product.sku.ilike(f"%{q}%"), Product.name.ilike(f"%{q}%")))

    products = query.order_by(Product.name.asc()).all()
    if stock_state == "critical":
        products = [product for product in products if product.qty_on_hand <= 5]
    elif stock_state == "reserved":
        products = [product for product in products if product.qty_reserved > 0]
    elif stock_state == "available":
        products = [product for product in products if product.qty_on_hand - product.qty_reserved > 0]

    start = (page - 1) * 20
    end = start + 20
    page_items = products[start:end]

    class SimplePagination:
        def __init__(self, items, page, per_page):
            self.items = items
            self.page = page
            self.per_page = per_page
            self.total = len(products)
            self.pages = max(1, (self.total + per_page - 1) // per_page)
            self.has_prev = page > 1
            self.has_next = page < self.pages
            self.prev_num = page - 1
            self.next_num = page + 1

        def iter_pages(self):
            return range(1, self.pages + 1)

    pagination = SimplePagination(page_items, page, 20)
    return render_template(
        "data_mdm/stock/list.html",
        products=pagination,
        q=q,
        stock_state=stock_state,
        critical_count=sum(1 for product in Product.query.all() if product.qty_on_hand <= 5),
        reserved_count=sum(1 for product in Product.query.all() if product.qty_reserved > 0),
        total_on_hand=sum(product.qty_on_hand for product in Product.query.all()),
    )


@mdm_bp.route("/users/roles", methods=["GET", "POST"])
@login_required
@admin_required
def user_roles():
    from app.models import User

    if request.method == "POST":
        for user in User.query.all():
            user.is_data_admin = request.form.get(f"data_admin_{user.id}") == "on"
            user.is_data_editor = request.form.get(f"data_editor_{user.id}") == "on"
            user.is_data_viewer = request.form.get(f"data_viewer_{user.id}") == "on"
        db.session.commit()
        flash("Роли доступа к MDM обновлены", "success")
        return redirect(url_for("mdm.user_roles"))

    users = User.query.order_by(User.username).all()
    return render_template("data_mdm/users/roles.html", users=users)


@mdm_bp.route("/company-profile")
@login_required
@mdm_readonly_required
def company_profile():
    profile = CompanyProfile.query.first()
    if not profile:
        flash("Профиль компании не найден. Обратитесь к администратору.", "danger")
        return redirect(url_for("mdm.index"))
    return render_template("data_mdm/company_profile.html", profile=profile)


@mdm_bp.route("/company-profile/edit", methods=["GET", "POST"])
@login_required
@mdm_editor_required
def edit_company_profile():
    profile = CompanyProfile.query.first()
    if not profile:
        flash("Профиль компании не найден. Обратитесь к администратору.", "danger")
        return redirect(url_for("mdm.index"))

    if request.method == "POST":
        # Вспомогательная функция для безопасной обработки формы
        def get_form_value(key, current_value=None, required=False):
            value = request.form.get(key, "").strip()
            if not value:
                return None if not required else (current_value or "")
            return value
        
        profile.company_name = get_form_value("company_name", profile.company_name, required=True)
        profile.short_name = get_form_value("short_name", profile.short_name)
        profile.legal_form = get_form_value("legal_form", profile.legal_form, required=True)
        profile.inn = get_form_value("inn", profile.inn, required=True)
        profile.kpp = get_form_value("kpp", profile.kpp)
        profile.ogrn = get_form_value("ogrn", profile.ogrn, required=True)
        profile.legal_address = get_form_value("legal_address", profile.legal_address, required=True)
        profile.actual_address = get_form_value("actual_address", profile.actual_address)
        profile.phone = get_form_value("phone", profile.phone)
        profile.email = get_form_value("email", profile.email)
        profile.website = get_form_value("website", profile.website)
        profile.bank_name = get_form_value("bank_name", profile.bank_name)
        profile.bank_bik = get_form_value("bank_bik", profile.bank_bik)
        profile.correspondent_account = get_form_value("correspondent_account", profile.correspondent_account)
        profile.settlement_account = get_form_value("settlement_account", profile.settlement_account)
        profile.ceo = get_form_value("ceo", profile.ceo, required=True)
        profile.ceo_position = get_form_value("ceo_position", profile.ceo_position)
        profile.chief_accountant_name = get_form_value("chief_accountant_name", profile.chief_accountant_name)
        profile.logo_url = get_form_value("logo_url", profile.logo_url)
        profile.seal_url = get_form_value("seal_url", profile.seal_url)
        profile.signature_url = get_form_value("signature_url", profile.signature_url)

        # Для ИП не нужны отдельные поля руководителя и главбуха
        if profile.legal_form == "ИП":
            profile.ceo_position = None
            profile.chief_accountant_name = None
            profile.chief_accountant_signature_url = None

        db.session.commit()
        flash("Профиль компании обновлен.", "success")
        return redirect(url_for("mdm.company_profile"))

    return render_template("data_mdm/company_profile_edit.html", profile=profile)

