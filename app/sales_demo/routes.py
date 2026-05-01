import os
from datetime import datetime

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
from app.models import CompanyProfile, Customer, Product, SalesOrder, SalesOrderAttachment, SalesOrderItem, db

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
    total_orders = SalesOrder.query.count()
    unpaid_orders = SalesOrder.query.filter(SalesOrder.status.in_(["pending", "unpaid"])).count()
    in_progress_orders = SalesOrder.query.filter(SalesOrder.status.in_(["picking", "assembled", "in_transit"])).count()
    completed_orders = SalesOrder.query.filter_by(status="completed").count()
    active_customers = Customer.query.filter_by(is_active=True).count()
    active_products = Product.query.filter_by(is_active=True).count()
    recent_orders = SalesOrder.query.order_by(SalesOrder.created_at.desc()).limit(6).all()
    return render_template(
        "sales/index.html",
        total_orders=total_orders,
        unpaid_orders=unpaid_orders,
        in_progress_orders=in_progress_orders,
        completed_orders=completed_orders,
        active_customers=active_customers,
        active_products=active_products,
        recent_orders=recent_orders,
        status_labels=STATUS_LABELS,
    )


@sales_bp.route("/crm")
@sales_bp.route("/crm/")
@login_required
def crm():
    return render_template("sales/crm.html")


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
    q = request.args.get("q", "").strip()
    customers = Customer.query.filter(Customer.name.ilike(f"%{q}%")).order_by(Customer.name.asc()).limit(20).all()
    return jsonify(
        [
            {
                "id": customer.id,
                "name": customer.name,
                "phone": customer.phone or "",
                "email": customer.email or "",
            }
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
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    phone = (payload.get("phone") or "").strip() or None
    email = (payload.get("email") or "").strip() or None
    if not name:
        return jsonify({"error": "ФИО клиента обязательно"}), 400
    customer = Customer(
        name=name,
        phone=phone,
        email=email,
        birth_date=_parse_date(payload.get("birth_date")),
        registration_address=(payload.get("registration_address") or "").strip() or None,
        passport_series_number=(payload.get("passport_series_number") or "").strip() or None,
        passport_issued_by=(payload.get("passport_issued_by") or "").strip() or None,
        passport_issue_date=_parse_date(payload.get("passport_issue_date")),
        snils=(payload.get("snils") or "").strip() or None,
        customer_inn=(payload.get("customer_inn") or "").strip() or None,
        notes=(payload.get("notes") or "").strip() or None,
        type="individual",
        is_active=True,
    )
    db.session.add(customer)
    db.session.commit()
    return jsonify({"id": customer.id, "name": customer.name, "phone": customer.phone or "", "email": customer.email or ""})


@sales_bp.route("/api/orders", methods=["POST"])
@login_required
def create_order():
    payload = request.get_json(silent=True) or {}
    customer_id = payload.get("customer_id")
    items_payload = payload.get("items") or []
    delivery_address = (payload.get("delivery_address") or "").strip()

    if not customer_id:
        return jsonify({"error": "Выберите клиента"}), 400
    if not delivery_address:
        return jsonify({"error": "Укажите адрес доставки"}), 400
    if not items_payload:
        return jsonify({"error": "Добавьте товары"}), 400

    customer = Customer.query.get(customer_id)
    if not customer:
        return jsonify({"error": "Клиент не найден"}), 404

    order = SalesOrder(
        order_number=_next_order_number(),
        customer_id=customer.id,
        status="unpaid",
        delivery_address=delivery_address,
        created_at=datetime.utcnow(),
    )
    db.session.add(order)
    db.session.flush()

    total_amount = 0.0
    for row in items_payload:
        product = Product.query.get(row.get("product_id"))
        qty = int(row.get("quantity", 0))
        if not product or qty <= 0:
            continue
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
    order.total_amount = round(total_amount, 2)
    db.session.commit()
    return jsonify({"order_id": order.id, "order_number": order.order_number, "status": order.status})


@sales_bp.route("/api/orders/<int:order_id>/confirm-payment", methods=["POST"])
@login_required
def confirm_payment(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    order.status = "picking"
    db.session.commit()
    return jsonify({"ok": True, "status": order.status, "status_label": STATUS_LABELS[order.status]})


@sales_bp.route("/orders/<int:order_id>/mark-assembled", methods=["POST"])
@login_required
def mark_assembled(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    order.status = "assembled"
    db.session.commit()
    flash(f"Заказ {order.order_number} отмечен как 'Собран'.", "success")
    return redirect(url_for("sales_demo.orders"))


@sales_bp.route("/orders/<int:order_id>/mark-in-transit", methods=["POST"])
@login_required
def mark_in_transit(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    order.status = "in_transit"
    db.session.commit()
    flash(f"Заказ {order.order_number} переведен в статус 'В пути'.", "success")
    return redirect(url_for("sales_demo.orders"))


@sales_bp.route("/orders/<int:order_id>/confirm-delivery", methods=["POST"])
@login_required
def confirm_delivery(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    order.status = "completed"
    order.delivery_confirmed_at = datetime.utcnow()
    db.session.commit()
    flash(f"Заказ {order.order_number} отмечен как выполненный.", "success")
    return redirect(url_for("sales_demo.orders"))


@sales_bp.route("/orders/<int:order_id>/upload-delivery-doc", methods=["POST"])
@login_required
def upload_delivery_doc(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    file = request.files.get("document")
    if not file or not file.filename:
        flash("Файл не выбран.", "warning")
        return redirect(url_for("sales_demo.orders"))
    if not _allowed_file(file.filename):
        flash("Неподдерживаемый формат файла.", "danger")
        return redirect(url_for("sales_demo.orders"))

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
    return redirect(url_for("sales_demo.orders"))


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
    customer, items, delivery_address = _payload_for_preview(request.get_json(silent=True) or {})
    company = CompanyProfile.query.first()
    doc = create_sales_doc("Договор купли-продажи", company, customer=customer, items=items, notes=f"Адрес доставки: {delivery_address}")
    return save_doc(doc, f"contract_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx")


@sales_bp.route("/documents/invoice-preview", methods=["POST"])
@login_required
def invoice_preview():
    customer, items, delivery_address = _payload_for_preview(request.get_json(silent=True) or {})
    company = CompanyProfile.query.first()
    doc = create_sales_doc("Счет на оплату", company, customer=customer, items=items, notes=f"Адрес доставки: {delivery_address}")
    return save_doc(doc, f"invoice_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx")


@sales_bp.route("/orders/<int:order_id>/documents/contract-print")
@login_required
def print_contract(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    company = CompanyProfile.query.first()
    items = _order_items_dict(order)
    doc = duplicate_contract_doc(company, order.customer, items, order.delivery_address)
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
    return customer, items, (payload.get("delivery_address") or "").strip()


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
