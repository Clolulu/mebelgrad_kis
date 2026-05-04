import os
from datetime import datetime, timedelta

from flask import (
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import login_required
from werkzeug.utils import secure_filename

from app.sales_demo import sales_bp
from app.sales_demo.docx_utils import create_sales_doc, duplicate_contract_doc, save_doc
from app.models import CompanyProfile, Customer, Payment, Product, SalesOrder, SalesOrderAttachment, SalesOrderItem, db
from app.schema_utils import get_visible_fields, get_field_by_name

STATUS_LABELS = {
    "pending": "Не оплачен",
    "unpaid": "Не оплачен",
    "picking": "В процессе комплектации",
    "assembled": "Собран",
    "in_transit": "В пути",
    "completed": "Выполнен",
    "cancelled": "Отменен",
}
ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx"}


@sales_bp.route("/")
@login_required
def index():
    from sqlalchemy import func
    
    total_orders = SalesOrder.query.count()
    unpaid_orders = SalesOrder.query.filter(SalesOrder.status.in_(["pending", "unpaid"])).count()
    assembling_orders = SalesOrder.query.filter_by(status="picking").count()
    assembled_orders = SalesOrder.query.filter_by(status="assembled").count()
    in_transit_orders = SalesOrder.query.filter_by(status="in_transit").count()
    completed_orders = SalesOrder.query.filter_by(status="completed").count()
    active_customers = Customer.query.filter_by(is_active=True).count()
    active_products = Product.query.filter_by(is_active=True).count()
    recent_orders = SalesOrder.query.order_by(SalesOrder.created_at.desc()).limit(6).all()
    
    # Statistics: orders for month and week
    now = datetime.utcnow()
    month_ago = now - timedelta(days=30)
    week_ago = now - timedelta(days=7)
    
    orders_this_month = SalesOrder.query.filter(SalesOrder.created_at >= month_ago).count()
    orders_this_week = SalesOrder.query.filter(SalesOrder.created_at >= week_ago).count()
    
    # Top selling and least selling products
    from sqlalchemy import func, desc
    selling_products = db.session.query(
        Product,
        func.sum(SalesOrderItem.quantity).label('total_qty')
    ).join(SalesOrderItem).group_by(Product.id).order_by(desc('total_qty')).limit(5).all()
    
    least_selling_products = db.session.query(
        Product,
        func.sum(SalesOrderItem.quantity).label('total_qty')
    ).join(SalesOrderItem).group_by(Product.id).order_by('total_qty').limit(5).all()
    
    return render_template(
        "sales/index.html",
        total_orders=total_orders,
        unpaid_orders=unpaid_orders,
        assembling_orders=assembling_orders,
        assembled_orders=assembled_orders,
        in_transit_orders=in_transit_orders,
        completed_orders=completed_orders,
        active_customers=active_customers,
        active_products=active_products,
        recent_orders=recent_orders,
        status_labels=STATUS_LABELS,
        orders_this_month=orders_this_month,
        orders_this_week=orders_this_week,
        selling_products=selling_products,
        least_selling_products=least_selling_products,
    )


@sales_bp.route("/crm")
@sales_bp.route("/crm/")
@login_required
def crm():
    customer_fields = [
        {
            "name": field.name,
            "label": field.label,
            "type": field.data_type,
            "required": field.is_required,
            "max_length": field.max_length,
            "help_text": field.help_text,
        }
        for field in get_visible_fields("customers")
    ]
    return render_template("sales/crm.html", customer_fields=customer_fields)


@sales_bp.route("/orders")
@sales_bp.route("/orders/")
@login_required
def orders():
    status = request.args.get("status", "").strip()
    customer_query = request.args.get("customer", "").strip()
    created_from = request.args.get("created_from", "").strip()
    created_to = request.args.get("created_to", "").strip()
    amount_min = request.args.get("amount_min", "").strip()
    amount_max = request.args.get("amount_max", "").strip()

    query = SalesOrder.query.join(Customer)
    if status:
        if status == "unpaid":
            query = query.filter(SalesOrder.status.in_(["unpaid", "pending"]))
        else:
            query = query.filter(SalesOrder.status == status)
    if customer_query:
        query = query.filter(Customer.name.ilike(f"%{customer_query}%"))
    if created_from:
        query = query.filter(SalesOrder.created_at >= datetime.strptime(created_from, "%Y-%m-%d"))
    if created_to:
        to_dt = datetime.strptime(created_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        query = query.filter(SalesOrder.created_at <= to_dt)
    if amount_min:
        query = query.filter(SalesOrder.total_amount >= float(amount_min))
    if amount_max:
        query = query.filter(SalesOrder.total_amount <= float(amount_max))

    orders_list = query.order_by(SalesOrder.created_at.desc()).all()
    return render_template("sales/orders.html", orders=orders_list, status_labels=STATUS_LABELS)


@sales_bp.route("/api/customers")
@login_required
def search_customers():
    """
    Search for customers by name field (searchable field from MDM schema).
    Returns results with all schema-defined visible fields.
    """
    q = request.args.get("q", "").strip()
    customers = Customer.query.filter(Customer.name.ilike(f"%{q}%")).order_by(Customer.name.asc()).limit(20).all()
    
    # Get schema fields for response serialization
    schema_fields = get_visible_fields('customers')
    
    return jsonify(
        [
            {
                field.name: str(getattr(customer, field.name) or "")
                for field in schema_fields
                if hasattr(customer, field.name)
            } | {"id": customer.id}
            for customer in customers
        ]
    )


@sales_bp.route("/api/products")
@login_required
def search_products():
    q = request.args.get("q", "").strip()
    products = Product.query.filter(Product.name.ilike(f"%{q}%"), Product.is_active.is_(True)).order_by(Product.name.asc()).limit(50).all()
    return jsonify(
        [
            {
                "id": product.id,
                "sku": product.sku,
                "name": product.name,
                "unit": product.unit,
                "unit_price": product.retail_price,
                "stock": product.qty_on_hand,
            }
            for product in products
        ]
    )


@sales_bp.route("/api/customers", methods=["POST"])
@login_required
def create_customer():
    """
    Create a customer using fields defined in the MDM schema.
    Dynamically extracts only schema-defined fields from the payload.
    """
    payload = request.get_json(silent=True) or {}
    
    # Get schema fields for customers
    schema_fields = get_visible_fields('customers')
    
    # Extract only schema-defined fields
    customer_data = {}
    for field in schema_fields:
        raw_value = payload.get(field.name, "")
        
        # Basic type conversion based on field definition
        if field.data_type == 'boolean':
            customer_data[field.name] = raw_value in [True, 'true', 'on', '1', 1]
        elif field.data_type == 'date':
            customer_data[field.name] = _parse_date(raw_value) if raw_value else None
        elif field.data_type in ['integer', 'float']:
            try:
                customer_data[field.name] = float(raw_value) if raw_value else None
            except (ValueError, TypeError):
                customer_data[field.name] = None
        else:
            customer_data[field.name] = (raw_value or "").strip() or None
    
    # Validate required fields
    name_field = get_field_by_name('customers', 'name')
    if name_field and name_field.is_required and not customer_data.get('name'):
        return jsonify({"error": f"{name_field.label} обязательно"}), 400
    
    # Create customer with schema-defined fields
    try:
        customer = Customer(
            **customer_data,
            type="individual",
            is_active=True,
        )
        db.session.add(customer)
        db.session.commit()
        
        # Return response with only schema-defined fields
        response = {"id": customer.id}
        for field in schema_fields:
            if hasattr(customer, field.name):
                response[field.name] = str(getattr(customer, field.name) or "")
        return jsonify(response)
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@sales_bp.route("/api/orders", methods=["POST"])
@login_required
def create_order():
    payload = request.get_json(silent=True) or {}
    customer_id = payload.get("customer_id")
    items_payload = payload.get("items") or []
    delivery_address = (payload.get("delivery_address") or "").strip()
    delivery_date_str = (payload.get("delivery_date") or "").strip()
    needs_assembly = bool(payload.get("needs_assembly"))

    if not customer_id:
        return jsonify({"error": "Выберите клиента"}), 400
    if not delivery_address:
        return jsonify({"error": "Укажите адрес доставки"}), 400
    if not items_payload:
        return jsonify({"error": "Добавьте товары"}), 400

    customer = Customer.query.get(customer_id)
    if not customer:
        return jsonify({"error": "Клиент не найден"}), 404

    # Calculate delivery date: if not provided, set to 2 days from now
    if delivery_date_str:
        try:
            delivery_date = datetime.strptime(delivery_date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Неверный формат даты доставки"}), 400
    else:
        delivery_date = datetime.utcnow() + timedelta(days=2)

    order = SalesOrder(
        order_number=_next_order_number(),
        customer_id=customer.id,
        status="unpaid",
        delivery_address=delivery_address,
        delivery_date=delivery_date,
        needs_assembly=needs_assembly,
        created_at=datetime.utcnow(),
    )
    db.session.add(order)
    db.session.flush()

    total_amount = 0.0
    for row in items_payload:
        product = Product.query.get(row.get("product_id"))
        qty = int(row.get("quantity", 0))
        if not product:
            return jsonify({"error": "Товар не найден"}), 400
        if qty <= 0:
            return jsonify({"error": "Количество товара должно быть больше нуля"}), 400
        if qty > product.qty_on_hand:
            return jsonify({"error": f"Для товара '{product.name}' доступно только {product.qty_on_hand} шт."}), 400
        unit_price = float(row.get("unit_price") or product.retail_price or 0.0)
        total_amount += qty * unit_price
        db.session.add(
            SalesOrderItem(
                sales_order_id=order.id,
                product_id=product.id,
                quantity=qty,
                unit_price=unit_price,
                cost_price=0.0,
                product_group="general",
            )
        )

    if needs_assembly:
        total_amount += 1000.0

    order.total_amount = round(total_amount, 2)
    db.session.commit()
    return jsonify({"success": True, "order_id": order.id, "order_number": order.order_number, "status": order.status})


@sales_bp.route("/api/orders/<int:order_id>/confirm-payment", methods=["POST"])
@login_required
def confirm_payment(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    if order.status == "cancelled":
        return jsonify({"ok": False, "error": "Нельзя подтвердить оплату отмененного заказа"}), 400
    if order.status in {"picking", "assembled", "in_transit", "completed"}:
        return jsonify({
            "ok": True,
            "order_id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "status_label": STATUS_LABELS[order.status],
        })
    order.status = "picking"
    payment = Payment(
        sales_order_id=order.id,
        amount=float(order.total_amount or 0.0),
        payment_date=datetime.utcnow(),
        status="completed",
    )
    db.session.add(payment)
    db.session.commit()
    return jsonify({
        "ok": True,
        "order_id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "status_label": STATUS_LABELS[order.status],
    })


@sales_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    reason = (request.form.get("cancel_reason") or "").strip()
    if not reason:
        flash("Укажите причину отмены заказа.", "warning")
        return _redirect_with_filters()
    order.status = "cancelled"
    order.cancel_reason = reason
    db.session.commit()
    flash(f"Заказ {order.order_number} отменен. Причина: {reason}", "success")
    return _redirect_with_filters()


@sales_bp.route("/orders/<int:order_id>/add-assembly", methods=["POST"])
@login_required
def add_assembly(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    if order.status in {"cancelled", "completed"}:
        flash("Нельзя добавить сборку к этому заказу.", "warning")
        return _redirect_with_filters()
    if order.needs_assembly:
        flash("Сборка уже добавлена к заказу.", "info")
        return _redirect_with_filters()
    order.needs_assembly = True
    order.total_amount = round((order.total_amount or 0.0) + 1000.0, 2)
    db.session.commit()
    flash(f"Сборка добавлена к заказу {order.order_number}.", "success")
    return _redirect_with_filters()


@sales_bp.route("/attachments/<int:attachment_id>/rename", methods=["POST"])
@login_required
def rename_attachment(attachment_id):
    attachment = SalesOrderAttachment.query.get_or_404(attachment_id)
    new_name = (request.form.get("new_name") or "").strip()
    if not new_name:
        flash("Укажите новое имя файла.", "warning")
        return _redirect_with_filters()
    attachment.original_filename = new_name
    db.session.commit()
    flash(f"Имя документа обновлено на '{new_name}'.", "success")
    return _redirect_with_filters()


@sales_bp.route("/orders/<int:order_id>/mark-assembled", methods=["POST"])
@login_required
def mark_assembled(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    order.status = "assembled"
    db.session.commit()
    flash(f"Заказ {order.order_number} отмечен как 'Собран'.", "success")
    return _redirect_with_filters()


@sales_bp.route("/orders/<int:order_id>/mark-in-transit", methods=["POST"])
@login_required
def mark_in_transit(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    order.status = "in_transit"
    db.session.commit()
    flash(f"Заказ {order.order_number} переведен в статус 'В пути'.", "success")
    return _redirect_with_filters()


@sales_bp.route("/orders/<int:order_id>/confirm-delivery", methods=["POST"])
@login_required
def confirm_delivery(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    if order.status != "in_transit":
        flash("Подтвердить доставку можно только для заказа в пути.", "warning")
        return _redirect_with_filters()
    if not order.attachments:
        flash("Прикрепите документ перед подтверждением доставки.", "warning")
        return _redirect_with_filters()
    order.status = "completed"
    order.delivery_confirmed_at = datetime.utcnow()
    db.session.commit()
    flash(f"Заказ {order.order_number} отмечен как выполненный.", "success")
    return _redirect_with_filters()


@sales_bp.route("/orders/<int:order_id>/upload-delivery-doc", methods=["POST"])
@login_required
def upload_delivery_doc(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    file = request.files.get("document")
    if not file or not file.filename:
        flash("Файл не выбран.", "warning")
        return _redirect_with_filters()
    if not _allowed_file(file.filename):
        flash("Неподдерживаемый формат файла.", "danger")
        return _redirect_with_filters()

    upload_dir = os.path.join(current_app.instance_path, "uploads", "sales_orders", str(order.id))
    os.makedirs(upload_dir, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    original_name = secure_filename(file.filename)
    stored_name = f"{timestamp}_{original_name}"
    stored_path = os.path.join(upload_dir, stored_name)
    file.save(stored_path)

    rel_path = os.path.relpath(stored_path, current_app.instance_path).replace("\\", "/")
    attachment = SalesOrderAttachment(
        sales_order_id=order.id,
        kind="delivery_doc",
        stored_path=rel_path,
        original_filename=original_name,
    )
    db.session.add(attachment)
    db.session.commit()
    flash(f"Документ '{original_name}' прикреплен к заказу {order.order_number}.", "success")
    return _redirect_with_filters()


@sales_bp.route("/attachments/<int:attachment_id>")
@login_required
def download_attachment(attachment_id):
    attachment = SalesOrderAttachment.query.get_or_404(attachment_id)
    absolute_path = os.path.join(current_app.instance_path, attachment.stored_path)
    directory = os.path.dirname(absolute_path)
    filename = os.path.basename(absolute_path)
    return send_from_directory(directory, filename, as_attachment=False, download_name=attachment.original_filename)


@sales_bp.route("/documents/contract-preview", methods=["POST"])
@login_required
def contract_preview():
    customer, items, delivery_address, needs_assembly = _payload_for_preview(request.get_json(silent=True) or {})
    company = CompanyProfile.query.first()
    doc = create_sales_doc(
        "Договор купли-продажи",
        company,
        customer=customer,
        items=items,
        notes=f"Адрес доставки: {delivery_address}",
        needs_assembly=needs_assembly,
    )
    return save_doc(doc, f"contract_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx")


@sales_bp.route("/documents/invoice-preview", methods=["POST"])
@login_required
def invoice_preview():
    customer, items, delivery_address, needs_assembly = _payload_for_preview(request.get_json(silent=True) or {})
    company = CompanyProfile.query.first()
    doc = create_sales_doc(
        "Счет на оплату",
        company,
        customer=customer,
        items=items,
        notes=f"Адрес доставки: {delivery_address}",
        needs_assembly=needs_assembly,
    )
    return save_doc(doc, f"invoice_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx")


@sales_bp.route("/orders/<int:order_id>/documents/contract-print")
@login_required
def print_contract(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    company = CompanyProfile.query.first()
    items = _order_items_dict(order)
    doc = duplicate_contract_doc(company, order.customer, items, order.delivery_address, needs_assembly=order.needs_assembly)
    return save_doc(doc, f"contract_{order.order_number}_2copies.docx")


@sales_bp.route("/orders/<int:order_id>/documents/<string:doc_type>")
@login_required
def order_document(order_id, doc_type):
    order = SalesOrder.query.get_or_404(order_id)
    company = CompanyProfile.query.first()
    items = _order_items_dict(order)
    doc_title_map = {
        "internal-shipment-note": "Внутренняя накладная на отгрузку",
        "route-sheet": "Маршрутный лист",
        "delivery-act": "Акт доставки",
        "assembly-act": "Акт сборки",
    }
    if doc_type not in doc_title_map:
        return "Unknown document type", 404
    doc = create_sales_doc(doc_title_map[doc_type], company, order=order, customer=order.customer, items=items)
    return save_doc(doc, f"{doc_type}_{order.order_number}.docx")


def _redirect_with_filters():
    """Перенаправить на страницу заказов с сохранением фильтров"""
    filters = {}
    for key in ["status", "customer", "created_from", "created_to", "amount_min", "amount_max"]:
        val = request.args.get(key, "").strip()
        if val:
            filters[key] = val
    return redirect(url_for("sales_demo.orders", **filters))


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_UPLOAD_EXTENSIONS


def _next_order_number():
    stamp = datetime.now().strftime("%y%m")
    latest = (
        SalesOrder.query.filter(SalesOrder.order_number.like(f"SO-{stamp}-%"))
        .order_by(SalesOrder.id.desc())
        .first()
    )
    if latest and latest.order_number.count("-") == 2:
        try:
            suffix = int(latest.order_number.split("-")[-1])
            return f"SO-{stamp}-{suffix + 1:03d}"
        except ValueError:
            pass
    return f"SO-{stamp}-001"


def _parse_date(raw_value):
    if not raw_value:
        return None
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _payload_for_preview(payload):
    customer_id = payload.get("customer_id")
    customer = Customer.query.get(customer_id) if customer_id else None
    items = []
    for item in payload.get("items") or []:
        product = Product.query.get(item.get("product_id"))
        if not product:
            continue
        items.append(
            {
                "name": product.name,
                "quantity": int(item.get("quantity", 0)),
                "unit_price": float(item.get("unit_price") or product.retail_price or 0.0),
                "stock": product.qty_on_hand,
            }
        )
    return (
        customer,
        items,
        (payload.get("delivery_address") or "").strip(),
        bool(payload.get("needs_assembly")),
    )


def _order_items_dict(order):
    data = []
    for row in order.items:
        data.append(
            {
                "name": row.product.name if row.product else f"Товар #{row.product_id}",
                "quantity": row.quantity,
                "unit_price": row.unit_price,
                "stock": row.product.qty_on_hand if row.product else 0,
            }
        )
    return data
