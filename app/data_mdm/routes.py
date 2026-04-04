from functools import wraps

from datetime import datetime

import json
import re

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_, func, or_

from app.data_mdm import mdm_bp
from app.models import (
    CompanyProfile,
    Customer,
    DuplicateAttempt,
    Employee,
    Product,
    Supplier,
    db,
)


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


def _format_audit_value(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return value


def _normalize_phone(phone):
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if not digits:
        return None
    return "+" + digits


def _normalize_email(email):
    if not email:
        return None
    normalized = email.strip().lower()
    return normalized if normalized else None


def _normalize_inn(inn):
    if not inn:
        return None
    normalized = re.sub(r"\D", "", inn)
    return normalized if normalized else None


def _validate_email(email):
    if not email:
        return True
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def _validate_phone(phone):
    if not phone:
        return True
    digits = re.sub(r"\D", "", phone)
    return 10 <= len(digits) <= 15


def _validate_inn(inn):
    if not inn:
        return False
    normalized = _normalize_inn(inn)
    return len(normalized) in (10, 12)


def _validate_sku(sku):
    if not sku:
        return False
    return bool(re.match(r"^[A-Za-z0-9\-_.]+$", sku))


def _log_duplicate_attempt(entity, attempted_record, attempted_data, duplicate_fields, reason, source="web"):
    log = DuplicateAttempt(
        entity=entity,
        attempted_record=attempted_record,
        attempted_data=json.dumps(attempted_data, ensure_ascii=False),
        duplicate_fields=", ".join(duplicate_fields),
        source=source,
        reason=reason,
    )
    db.session.add(log)
    db.session.commit()


def _find_potential_duplicates(model, partial_values, exact_values):
    filters = []
    for field, value in partial_values.items():
        if value:
            filters.append(getattr(model, field).ilike(f"%{value}%"))
    for field, value in exact_values.items():
        if value:
            filters.append(getattr(model, field) == value)
    if not filters:
        return []
    return model.query.filter(or_(*filters)).all()


def _entity_duplicate_exists(model, values, exclude_id=None):
    filters = []
    for field, value in values.items():
        if value:
            filters.append(getattr(model, field) == value)
    if not filters:
        return False
    query = model.query.filter(or_(*filters))
    if exclude_id:
        query = query.filter(model.id != exclude_id)
    return query.first() is not None


def _build_mdm_audit_entries():
    entries = []

    entity_specs = [
        (
            "Номенклатура",
            Product.query.all(),
            lambda item: item.name,
            lambda item: item.sku,
            "Создание карточки товара",
            "products",
        ),
        (
            "Клиенты",
            Customer.query.all(),
            lambda item: item.name,
            lambda item: item.type,
            "Создание карточки клиента",
            "customers",
        ),
        (
            "Поставщики",
            Supplier.query.all(),
            lambda item: item.name,
            lambda item: item.inn,
            "Создание карточки поставщика",
            "suppliers",
        ),
        (
            "Сотрудники",
            Employee.query.all(),
            lambda item: item.name,
            lambda item: item.position,
            "Создание карточки сотрудника",
            "employees",
        ),
    ]

    for entity_name, rows, title_getter, meta_getter, action, entity_key in entity_specs:
        for row in rows:
            entries.append(
                {
                    "entity": entity_name,
                    "entity_key": entity_key,
                    "action": action,
                    "record_name": title_getter(row),
                    "record_meta": _format_audit_value(meta_getter(row)),
                    "timestamp": row.created_at,
                    "timestamp_label": row.created_at.strftime("%d.%m.%Y %H:%M")
                    if row.created_at
                    else "н/д",
                    "details": "Запись присутствует в мастер-данных.",
                    "status": "success",
                }
            )

    profile = CompanyProfile.query.first()
    if profile:
        entries.append(
            {
                "entity": "Профиль компании",
                "entity_key": "company_profile",
                "action": "Актуализация профиля организации",
                "record_name": profile.short_name or profile.company_name,
                "record_meta": profile.legal_form,
                "timestamp": profile.updated_at or profile.created_at,
                "timestamp_label": (
                    (profile.updated_at or profile.created_at).strftime("%d.%m.%Y %H:%M")
                    if (profile.updated_at or profile.created_at)
                    else "н/д"
                ),
                "details": "Обновлены реквизиты, контакты или печатные атрибуты.",
                "status": "warning",
            }
        )

    for attempt in DuplicateAttempt.query.order_by(DuplicateAttempt.created_at.desc()).limit(50).all():
        entries.append(
            {
                "entity": "Контроль качества данных",
                "entity_key": "duplicate_attempts",
                "action": "Попытка создания дубликата",
                "record_name": attempt.attempted_record,
                "record_meta": attempt.duplicate_fields,
                "timestamp": attempt.created_at,
                "timestamp_label": attempt.created_at.strftime("%d.%m.%Y %H:%M") if attempt.created_at else "н/д",
                "details": attempt.reason,
                "status": "danger",
            }
        )

    for product in Product.query.all():
        if product.stock and product.stock.last_updated:
            entries.append(
                {
                    "entity": "Остатки",
                    "entity_key": "stock",
                    "action": "Обновление складского остатка",
                    "record_name": product.name,
                    "record_meta": product.sku,
                    "timestamp": product.stock.last_updated,
                    "timestamp_label": product.stock.last_updated.strftime("%d.%m.%Y %H:%M"),
                    "details": (
                        f"На складе: {product.qty_on_hand} ед., "
                        f"в резерве: {product.qty_reserved} ед."
                    ),
                    "status": "info",
                }
            )

    entries.sort(key=lambda item: item["timestamp"] or datetime.min, reverse=True)
    return entries


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


@mdm_bp.route("/audit-log")
@login_required
@mdm_readonly_required
def audit_log():
    entity = request.args.get("entity", "").strip()
    q = request.args.get("q", "").strip().lower()

    entries = _build_mdm_audit_entries()
    if entity:
        entries = [entry for entry in entries if entry["entity_key"] == entity]
    if q:
        entries = [
            entry
            for entry in entries
            if q in (entry["record_name"] or "").lower()
            or q in (entry["record_meta"] or "").lower()
            or q in (entry["action"] or "").lower()
            or q in (entry["details"] or "").lower()
        ]

    entity_options = [
        ("products", "Номенклатура"),
        ("customers", "Клиенты"),
        ("suppliers", "Поставщики"),
        ("employees", "Сотрудники"),
        ("company_profile", "Профиль компании"),
        ("stock", "Остатки"),
        ("duplicate_attempts", "Дубли / конфликтные записи"),
    ]

    return render_template(
        "data_mdm/audit_log.html",
        entries=entries[:150],
        entity=entity,
        q=request.args.get("q", "").strip(),
        entity_options=entity_options,
        total_entries=len(entries),
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

        if not _validate_sku(sku):
            flash("Артикул товара должен состоять из букв, цифр, дефисов или точек.", "danger")
            return redirect(url_for("mdm.create_product"))

        if Product.query.filter(func.lower(Product.sku) == sku.lower()).first():
            _log_duplicate_attempt(
                "Product",
                sku,
                {"sku": sku, "name": name},
                ["sku"],
                "Попытка создания товара с существующим артикулом.",
            )
            flash("Товар с таким артикулом уже существует.", "danger")
            return redirect(url_for("mdm.create_product"))

        try:
            price = float(retail_price or 0)
            if price < 0:
                raise ValueError
        except ValueError:
            flash("Цена должна быть числом больше или равна нулю.", "danger")
            return redirect(url_for("mdm.create_product"))

        product = Product(
            sku=sku,
            name=name,
            unit=unit,
            retail_price=price,
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
        try:
            product.retail_price = float(request.form.get("retail_price", product.retail_price) or 0)
            if product.retail_price < 0:
                raise ValueError
        except ValueError:
            flash("Цена должна быть числом больше или равна нулю.", "danger")
            return redirect(url_for("mdm.edit_product", product_id=product_id))
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
        phone = _normalize_phone(request.form.get("phone", "").strip())
        email = _normalize_email(request.form.get("email", "").strip())
        customer_type = request.form.get("type", "individual")

        if not name:
            flash("ФИО или наименование клиента обязательно.", "danger")
            return redirect(url_for("mdm.create_customer"))
        if not phone and not email:
            flash("Укажите телефон или email клиента для уменьшения риска дубликатов.", "danger")
            return redirect(url_for("mdm.create_customer"))
        if not _validate_phone(phone) or not _validate_email(email):
            flash("Проверьте корректность формата телефона и/или email.", "danger")
            return redirect(url_for("mdm.create_customer"))

        duplicate = Customer.query.filter(
            or_(Customer.phone == phone, Customer.email == email)
        ).first()
        if duplicate:
            _log_duplicate_attempt(
                "Customer",
                name,
                {"name": name, "phone": phone, "email": email},
                ["phone", "email"],
                "Попытка создания клиента, совпадающего по телефону или email.",
            )
            flash("Клиент с таким телефоном или email уже существует.", "danger")
            return redirect(url_for("mdm.create_customer"))

        candidates = _find_potential_duplicates(
            Customer,
            {"name": name},
            {"phone": phone, "email": email},
        )
        if candidates:
            _log_duplicate_attempt(
                "Customer",
                name,
                {"name": name, "phone": phone, "email": email},
                ["name", "phone", "email"],
                "Найдены потенциальные дубли клиента по имени и контакту.",
            )
            flash(
                "Найдены похожие записи клиента. Проверьте данные, чтобы избежать дубликатов.",
                "warning",
            )
            return redirect(url_for("mdm.create_customer"))

        customer = Customer(
            name=name,
            phone=phone,
            email=email,
            type=customer_type,
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
        name = request.form.get("name", customer.name).strip()
        phone = _normalize_phone(request.form.get("phone", customer.phone).strip())
        email = _normalize_email(request.form.get("email", customer.email).strip())

        if not name:
            flash("ФИО или наименование клиента обязательно.", "danger")
            return redirect(url_for("mdm.edit_customer", customer_id=customer_id))
        if not phone and not email:
            flash("Укажите телефон или email клиента для уменьшения риска дубликатов.", "danger")
            return redirect(url_for("mdm.edit_customer", customer_id=customer_id))
        if not _validate_phone(phone) or not _validate_email(email):
            flash("Проверьте корректность формата телефона и/или email.", "danger")
            return redirect(url_for("mdm.edit_customer", customer_id=customer_id))

        duplicate = Customer.query.filter(
            or_(Customer.phone == phone, Customer.email == email)
        ).filter(Customer.id != customer.id).first()
        if duplicate:
            _log_duplicate_attempt(
                "Customer",
                name,
                {"name": name, "phone": phone, "email": email},
                ["phone", "email"],
                "Попытка изменения клиента на существующую запись.",
            )
            flash("Другой клиент уже использует этот телефон или email.", "danger")
            return redirect(url_for("mdm.edit_customer", customer_id=customer_id))

        candidates = _find_potential_duplicates(
            Customer,
            {"name": name},
            {"phone": phone, "email": email},
        )
        if any(candidate.id != customer.id for candidate in candidates):
            _log_duplicate_attempt(
                "Customer",
                name,
                {"name": name, "phone": phone, "email": email},
                ["name", "phone", "email"],
                "Найдены потенциальные дубли клиента при редактировании.",
            )
            flash(
                "Найдены похожие записи клиента. Проверьте данные, чтобы избежать дубликатов.",
                "warning",
            )
            return redirect(url_for("mdm.edit_customer", customer_id=customer_id))

        customer.name = name
        customer.phone = phone
        customer.email = email
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
        phone = _normalize_phone(request.form.get("phone", "").strip())
        email = _normalize_email(request.form.get("email", "").strip())
        inn = _normalize_inn(request.form.get("inn", "").strip())

        if not name:
            flash("Наименование поставщика обязательно.", "danger")
            return redirect(url_for("mdm.create_supplier"))
        if not inn or not _validate_inn(inn):
            flash("ИНН поставщика обязателен и должен содержать 10 или 12 цифр.", "danger")
            return redirect(url_for("mdm.create_supplier"))
        if not phone and not email:
            flash("Укажите телефон или email поставщика для уменьшения риска дубликатов.", "danger")
            return redirect(url_for("mdm.create_supplier"))
        if not _validate_phone(phone) or not _validate_email(email):
            flash("Проверьте корректность формата телефона и/или email.", "danger")
            return redirect(url_for("mdm.create_supplier"))

        duplicate = Supplier.query.filter(
            or_(Supplier.inn == inn, Supplier.phone == phone, Supplier.email == email)
        ).first()
        if duplicate:
            _log_duplicate_attempt(
                "Supplier",
                name,
                {"name": name, "phone": phone, "email": email, "inn": inn},
                ["inn", "phone", "email"],
                "Попытка создания поставщика с существующими ключевыми реквизитами.",
            )
            flash("Поставщик с такими реквизитами уже существует.", "danger")
            return redirect(url_for("mdm.create_supplier"))

        candidates = _find_potential_duplicates(
            Supplier,
            {"name": name},
            {"phone": phone, "email": email, "inn": inn},
        )
        if candidates:
            _log_duplicate_attempt(
                "Supplier",
                name,
                {"name": name, "phone": phone, "email": email, "inn": inn},
                ["name", "phone", "email", "inn"],
                "Найдены потенциальные дубли поставщика по наименованию и контактам.",
            )
            flash(
                "Найдены похожие записи поставщика. Проверьте данные, чтобы избежать дубликатов.",
                "warning",
            )
            return redirect(url_for("mdm.create_supplier"))

        supplier = Supplier(
            name=name,
            phone=phone,
            email=email,
            inn=inn,
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
        name = request.form.get("name", supplier.name).strip()
        phone = _normalize_phone(request.form.get("phone", supplier.phone).strip())
        email = _normalize_email(request.form.get("email", supplier.email).strip())
        inn = _normalize_inn(request.form.get("inn", supplier.inn).strip())

        if not name:
            flash("Наименование поставщика обязательно.", "danger")
            return redirect(url_for("mdm.edit_supplier", supplier_id=supplier_id))
        if not inn or not _validate_inn(inn):
            flash("ИНН поставщика обязателен и должен содержать 10 или 12 цифр.", "danger")
            return redirect(url_for("mdm.edit_supplier", supplier_id=supplier_id))
        if not phone and not email:
            flash("Укажите телефон или email поставщика для уменьшения риска дубликатов.", "danger")
            return redirect(url_for("mdm.edit_supplier", supplier_id=supplier_id))
        if not _validate_phone(phone) or not _validate_email(email):
            flash("Проверьте корректность формата телефона и/или email.", "danger")
            return redirect(url_for("mdm.edit_supplier", supplier_id=supplier_id))

        duplicate = Supplier.query.filter(
            or_(Supplier.inn == inn, Supplier.phone == phone, Supplier.email == email)
        ).filter(Supplier.id != supplier.id).first()
        if duplicate:
            _log_duplicate_attempt(
                "Supplier",
                name,
                {"name": name, "phone": phone, "email": email, "inn": inn},
                ["inn", "phone", "email"],
                "Попытка изменения поставщика на существующую запись.",
            )
            flash("Другой поставщик уже использует такой ИНН, телефон или email.", "danger")
            return redirect(url_for("mdm.edit_supplier", supplier_id=supplier_id))

        candidates = _find_potential_duplicates(
            Supplier,
            {"name": name},
            {"phone": phone, "email": email, "inn": inn},
        )
        if any(candidate.id != supplier.id for candidate in candidates):
            _log_duplicate_attempt(
                "Supplier",
                name,
                {"name": name, "phone": phone, "email": email, "inn": inn},
                ["name", "phone", "email", "inn"],
                "Найдены потенциальные дубли поставщика при редактировании.",
            )
            flash(
                "Найдены похожие записи поставщика. Проверьте данные, чтобы избежать дубликатов.",
                "warning",
            )
            return redirect(url_for("mdm.edit_supplier", supplier_id=supplier_id))

        supplier.name = name
        supplier.phone = phone
        supplier.email = email
        supplier.inn = inn
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
        phone = _normalize_phone(request.form.get("phone", "").strip())
        email = _normalize_email(request.form.get("email", "").strip())
        position = request.form.get("role", request.form.get("position", "")).strip()

        if not name:
            flash("ФИО сотрудника обязательно.", "danger")
            return redirect(url_for("mdm.create_employee"))
        if not phone and not email:
            flash("Укажите телефон или email сотрудника для уменьшения риска дубликатов.", "danger")
            return redirect(url_for("mdm.create_employee"))
        if not _validate_phone(phone) or not _validate_email(email):
            flash("Проверьте корректность формата телефона и/или email.", "danger")
            return redirect(url_for("mdm.create_employee"))

        duplicate = Employee.query.filter(or_(Employee.phone == phone, Employee.email == email)).first()
        if duplicate:
            _log_duplicate_attempt(
                "Employee",
                name,
                {"name": name, "phone": phone, "email": email},
                ["phone", "email"],
                "Попытка создания сотрудника с существующим телефоном или email.",
            )
            flash("Сотрудник с таким телефоном или email уже существует.", "danger")
            return redirect(url_for("mdm.create_employee"))

        candidates = _find_potential_duplicates(
            Employee,
            {"name": name},
            {"phone": phone, "email": email},
        )
        if candidates:
            _log_duplicate_attempt(
                "Employee",
                name,
                {"name": name, "phone": phone, "email": email},
                ["name", "phone", "email"],
                "Найдены потенциальные дубли сотрудника по имени и контакту.",
            )
            flash(
                "Найдены похожие записи сотрудника. Проверьте данные, чтобы избежать дубликатов.",
                "warning",
            )
            return redirect(url_for("mdm.create_employee"))

        employee = Employee(
            name=name,
            position=position,
            phone=phone,
            email=email,
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
        name = request.form.get("name", employee.name).strip()
        position = request.form.get(
            "role", request.form.get("position", employee.position)
        ).strip()
        phone = _normalize_phone(request.form.get("phone", employee.phone).strip())
        email = _normalize_email(request.form.get("email", employee.email).strip())

        if not name:
            flash("ФИО сотрудника обязательно.", "danger")
            return redirect(url_for("mdm.edit_employee", employee_id=employee_id))
        if not phone and not email:
            flash("Укажите телефон или email сотрудника для уменьшения риска дубликатов.", "danger")
            return redirect(url_for("mdm.edit_employee", employee_id=employee_id))
        if not _validate_phone(phone) or not _validate_email(email):
            flash("Проверьте корректность формата телефона и/или email.", "danger")
            return redirect(url_for("mdm.edit_employee", employee_id=employee_id))

        duplicate = Employee.query.filter(or_(Employee.phone == phone, Employee.email == email)).filter(Employee.id != employee.id).first()
        if duplicate:
            _log_duplicate_attempt(
                "Employee",
                name,
                {"name": name, "phone": phone, "email": email},
                ["phone", "email"],
                "Попытка изменения сотрудника на существующую запись.",
            )
            flash("Другой сотрудник уже использует этот телефон или email.", "danger")
            return redirect(url_for("mdm.edit_employee", employee_id=employee_id))

        candidates = _find_potential_duplicates(
            Employee,
            {"name": name},
            {"phone": phone, "email": email},
        )
        if any(candidate.id != employee.id for candidate in candidates):
            _log_duplicate_attempt(
                "Employee",
                name,
                {"name": name, "phone": phone, "email": email},
                ["name", "phone", "email"],
                "Найдены потенциальные дубли сотрудника при редактировании.",
            )
            flash(
                "Найдены похожие записи сотрудника. Проверьте данные, чтобы избежать дубликатов.",
                "warning",
            )
            return redirect(url_for("mdm.edit_employee", employee_id=employee_id))

        employee.name = name
        employee.position = position
        employee.phone = phone
        employee.email = email
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

