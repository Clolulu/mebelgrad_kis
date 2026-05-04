from flask import render_template
from flask_login import login_required

from app.warehouse_demo import warehouse_bp


@warehouse_bp.route("/")
@login_required
def index():
    pr_active = PurchaseRequest.query.filter(
        PurchaseRequest.status.in_(['draft', 'submitted', 'approved'])
    ).count()
    pr_total = PurchaseRequest.query.count()
    receipts_today = GoodsReceipt.query.filter(
        GoodsReceipt.receipt_date >= datetime.utcnow().replace(hour=0, minute=0, second=0)
    ).count()
    receipts_total = GoodsReceipt.query.count()
    assembly_orders = SalesOrder.query.filter_by(status='picking').count()
    in_transit = SalesOrder.query.filter_by(status='in_transit').count()
    inventory_counts = InventoryCount.query.count()
    low_stock = Product.query.join(Stock).filter(Stock.qty_on_hand <= 5).count()

    recent_requests = PurchaseRequest.query.order_by(PurchaseRequest.created_at.desc()).limit(5).all()
    recent_receipts = GoodsReceipt.query.order_by(GoodsReceipt.created_at.desc()).limit(5).all()

    return render_template(
        'warehouse/index.html',
        pr_active=pr_active,
        pr_total=pr_total,
        receipts_today=receipts_today,
        receipts_total=receipts_total,
        assembly_orders=assembly_orders,
        in_transit=in_transit,
        inventory_counts=inventory_counts,
        low_stock=low_stock,
        recent_requests=recent_requests,
        recent_receipts=recent_receipts,
        pr_status_labels=PR_STATUS_LABELS,
        receipt_status_labels=RECEIPT_STATUS_LABELS,
    )


# ── Purchase Requests ─────────────────────────────────────────────────────────

@warehouse_bp.route('/purchase-requests')
@login_required
def purchase_requests():
    status = request.args.get('status', '').strip()
    supplier_q = request.args.get('supplier', '').strip()
    priority = request.args.get('priority', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    q = PurchaseRequest.query
    if status:
        q = q.filter(PurchaseRequest.status == status)
    if supplier_q:
        q = q.join(Supplier, isouter=True).filter(Supplier.name.ilike(f'%{supplier_q}%'))
    if priority:
        q = q.filter(PurchaseRequest.priority == priority)
    if date_from:
        q = q.filter(PurchaseRequest.request_date >= datetime.strptime(date_from, '%Y-%m-%d'))
    if date_to:
        dt = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        q = q.filter(PurchaseRequest.request_date <= dt)

    requests_list = q.order_by(PurchaseRequest.created_at.desc()).all()
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()

    return render_template(
        'warehouse/purchase_requests.html',
        requests=requests_list,
        suppliers=suppliers,
        status_labels=PR_STATUS_LABELS,
        priority_labels=PR_PRIORITY_LABELS,
    )


@warehouse_bp.route('/purchase-requests/new', methods=['GET', 'POST'])
@login_required
def purchase_request_new():
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    if request.method == 'POST':
        supplier_id = request.form.get('supplier_id') or None
        needed_by = request.form.get('needed_by_date', '').strip()
        priority = request.form.get('priority', 'normal')
        comment = request.form.get('comment', '').strip() or None

        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        estimated_costs = request.form.getlist('estimated_cost[]')
        comments_per_item = request.form.getlist('item_comment[]')

        if not product_ids:
            flash('Добавьте хотя бы одну позицию в заявку.', 'warning')
            return render_template('warehouse/purchase_request_form.html',
                                   suppliers=suppliers, products=products,
                                   priority_labels=PR_PRIORITY_LABELS, edit=False)

        pr = PurchaseRequest(
            request_number=_next_pr_number(),
            supplier_id=int(supplier_id) if supplier_id else None,
            needed_by_date=datetime.strptime(needed_by, '%Y-%m-%d') if needed_by else None,
            priority=priority,
            comment=comment,
            status='draft',
            created_by=current_user.id,
        )
        db.session.add(pr)
        db.session.flush()

        for i, pid in enumerate(product_ids):
            if not pid:
                continue
            qty = int(quantities[i]) if quantities[i] else 1
            cost = float(estimated_costs[i]) if estimated_costs[i] else 0.0
            item_comment = comments_per_item[i] if i < len(comments_per_item) else ''
            db.session.add(PurchaseRequestItem(
                request_id=pr.id,
                product_id=int(pid),
                quantity=max(qty, 1),
                estimated_cost=cost,
                comment=item_comment or None,
            ))

        db.session.commit()
        flash(f'Заявка {pr.request_number} создана.', 'success')
        return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr.id))

    return render_template('warehouse/purchase_request_form.html',
                           suppliers=suppliers, products=products,
                           priority_labels=PR_PRIORITY_LABELS, edit=False)


@warehouse_bp.route('/purchase-requests/<int:pr_id>')
@login_required
def purchase_request_detail(pr_id):
    pr = PurchaseRequest.query.get_or_404(pr_id)
    return render_template('warehouse/purchase_request_detail.html',
                           pr=pr, status_labels=PR_STATUS_LABELS,
                           priority_labels=PR_PRIORITY_LABELS)


@warehouse_bp.route('/purchase-requests/<int:pr_id>/export-docx')
@login_required
def purchase_request_export_docx(pr_id):
    pr = PurchaseRequest.query.get_or_404(pr_id)
    company = CompanyProfile.query.first()
    buf = generate_purchase_request_docx(pr, company)
    filename = f'Заявка_{pr.request_number}.docx'
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )


@warehouse_bp.route('/purchase-requests/<int:pr_id>/edit', methods=['GET', 'POST'])
@login_required
def purchase_request_edit(pr_id):
    pr = PurchaseRequest.query.get_or_404(pr_id)
    if pr.status not in ('draft', 'rejected'):
        flash('Редактировать можно только черновики и отклонённые заявки.', 'warning')
        return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))

    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    if request.method == 'POST':
        pr.supplier_id = request.form.get('supplier_id') or None
        if pr.supplier_id:
            pr.supplier_id = int(pr.supplier_id)
        needed_by = request.form.get('needed_by_date', '').strip()
        pr.needed_by_date = datetime.strptime(needed_by, '%Y-%m-%d') if needed_by else None
        pr.priority = request.form.get('priority', 'normal')
        pr.comment = request.form.get('comment', '').strip() or None
        pr.status = 'draft'

        for item in pr.items:
            db.session.delete(item)
        db.session.flush()

        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        estimated_costs = request.form.getlist('estimated_cost[]')
        comments_per_item = request.form.getlist('item_comment[]')

        if not product_ids:
            flash('Добавьте хотя бы одну позицию.', 'warning')
            return render_template('warehouse/purchase_request_form.html',
                                   suppliers=suppliers, products=products,
                                   priority_labels=PR_PRIORITY_LABELS, edit=True, pr=pr)

        for i, pid in enumerate(product_ids):
            if not pid:
                continue
            qty = int(quantities[i]) if quantities[i] else 1
            cost = float(estimated_costs[i]) if estimated_costs[i] else 0.0
            item_comment = comments_per_item[i] if i < len(comments_per_item) else ''
            db.session.add(PurchaseRequestItem(
                request_id=pr.id,
                product_id=int(pid),
                quantity=max(qty, 1),
                estimated_cost=cost,
                comment=item_comment or None,
            ))

        db.session.commit()
        flash(f'Заявка {pr.request_number} обновлена.', 'success')
        return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr.id))

    return render_template('warehouse/purchase_request_form.html',
                           suppliers=suppliers, products=products,
                           priority_labels=PR_PRIORITY_LABELS, edit=True, pr=pr)


@warehouse_bp.route('/purchase-requests/<int:pr_id>/submit', methods=['POST'])
@login_required
def purchase_request_submit(pr_id):
    pr = PurchaseRequest.query.get_or_404(pr_id)
    if pr.status != 'draft':
        flash('Подать на согласование можно только черновик.', 'warning')
        return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))
    if not pr.items:
        flash('Заявка должна содержать хотя бы одну позицию.', 'warning')
        return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))
    pr.status = 'submitted'
    db.session.commit()
    flash(f'Заявка {pr.request_number} отправлена на согласование.', 'success')
    return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))


@warehouse_bp.route('/purchase-requests/<int:pr_id>/approve', methods=['POST'])
@login_required
def purchase_request_approve(pr_id):
    pr = PurchaseRequest.query.get_or_404(pr_id)
    if pr.status != 'submitted':
        flash('Согласовать можно только заявку со статусом «На согласовании».', 'warning')
        return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))
    pr.status = 'approved'
    pr.approved_by = current_user.id
    pr.approved_at = datetime.utcnow()
    db.session.commit()
    flash(f'Заявка {pr.request_number} одобрена.', 'success')
    return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))


@warehouse_bp.route('/purchase-requests/<int:pr_id>/reject', methods=['POST'])
@login_required
def purchase_request_reject(pr_id):
    pr = PurchaseRequest.query.get_or_404(pr_id)
    reason = request.form.get('reject_reason', '').strip()
    if pr.status != 'submitted':
        flash('Отклонить можно только заявку со статусом «На согласовании».', 'warning')
        return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))
    pr.status = 'rejected'
    if reason:
        pr.comment = (pr.comment or '') + f'\nОтклонено: {reason}'
    db.session.commit()
    flash(f'Заявка {pr.request_number} отклонена.', 'danger')
    return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))


@warehouse_bp.route('/purchase-requests/<int:pr_id>/convert', methods=['POST'])
@login_required
def purchase_request_convert(pr_id):
    pr = PurchaseRequest.query.get_or_404(pr_id)
    if pr.status != 'approved':
        flash('Оформить заказ можно только по одобренной заявке.', 'warning')
        return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))
    if not pr.supplier_id:
        flash('Укажите поставщика перед оформлением заказа.', 'warning')
        return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))

    total = sum((i.estimated_cost or 0) * i.quantity for i in pr.items)
    po = PurchaseOrder(
        order_number=_next_po_number(),
        supplier_id=pr.supplier_id,
        order_date=datetime.utcnow(),
        status='pending',
        total_amount=total,
        is_paid=False,
    )
    db.session.add(po)
    db.session.flush()

    for item in pr.items:
        db.session.add(PurchaseOrderItem(
            purchase_order_id=po.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_cost=item.estimated_cost or 0.0,
        ))

    pr.status = 'ordered'
    pr.purchase_order_id = po.id
    db.session.commit()
    flash(f'Создан заказ поставщику {po.order_number}.', 'success')
    return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))


@warehouse_bp.route('/purchase-requests/<int:pr_id>/delete', methods=['POST'])
@login_required
def purchase_request_delete(pr_id):
    pr = PurchaseRequest.query.get_or_404(pr_id)
    if pr.status not in ('draft', 'rejected'):
        flash('Удалить можно только черновики и отклонённые заявки.', 'warning')
        return redirect(url_for('warehouse_demo.purchase_request_detail', pr_id=pr_id))
    num = pr.request_number
    db.session.delete(pr)
    db.session.commit()
    flash(f'Заявка {num} удалена.', 'info')
    return redirect(url_for('warehouse_demo.purchase_requests'))


# ── Stock Management ──────────────────────────────────────────────────────────

@warehouse_bp.route('/stock')
@login_required
def stock():
    name_q = request.args.get('name', '').strip()
    sku_q = request.args.get('sku', '').strip()
    stock_filter = request.args.get('stock_filter', '').strip()

    q = Product.query.outerjoin(Stock)
    if name_q:
        q = q.filter(Product.name.ilike(f'%{name_q}%'))
    if sku_q:
        q = q.filter(Product.sku.ilike(f'%{sku_q}%'))
    if stock_filter == 'low':
        q = q.filter(Stock.qty_on_hand <= 5)
    elif stock_filter == 'zero':
        q = q.filter((Stock.qty_on_hand == 0) | (Stock.qty_on_hand.is_(None)))
    elif stock_filter == 'ok':
        q = q.filter(Stock.qty_on_hand > 5)

    products = q.filter(Product.is_active.is_(True)).order_by(Product.name).all()
    total_value = sum((p.qty_on_hand * p.retail_price) for p in products)

@warehouse_bp.route("/", methods=["GET"])
@login_required
def stock_adjust(product_id):
    product = Product.query.get_or_404(product_id)
    delta = request.form.get('delta', '').strip()
    reason = request.form.get('reason', '').strip()
    try:
        delta = int(delta)
    except (ValueError, TypeError):
        flash('Некорректное значение корректировки.', 'danger')
        return redirect(url_for('warehouse_demo.stock'))

    stock = product.stock
    if not stock:
        stock = Stock(product_id=product_id, qty_on_hand=0, qty_reserved=0)
        db.session.add(stock)
        db.session.flush()

    new_qty = stock.qty_on_hand + delta
    if new_qty < 0:
        flash(f'Недостаточно товара на складе. Текущий остаток: {stock.qty_on_hand}.', 'danger')
        return redirect(url_for('warehouse_demo.stock'))

    stock.qty_on_hand = new_qty
    stock.last_updated = datetime.utcnow()
    db.session.commit()
    sign = '+' if delta >= 0 else ''
    flash(f'{product.name}: остаток {sign}{delta} → {new_qty} шт.{(" (" + reason + ")") if reason else ""}', 'success')
    return redirect(url_for('warehouse_demo.stock'))


# ── Goods Receipts ────────────────────────────────────────────────────────────

@warehouse_bp.route('/receipts')
@login_required
def receipts():
    status = request.args.get('status', '').strip()
    supplier_q = request.args.get('supplier', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    q = GoodsReceipt.query
    if status:
        q = q.filter(GoodsReceipt.status == status)
    if supplier_q:
        q = q.join(Supplier).filter(Supplier.name.ilike(f'%{supplier_q}%'))
    if date_from:
        q = q.filter(GoodsReceipt.receipt_date >= datetime.strptime(date_from, '%Y-%m-%d'))
    if date_to:
        dt = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        q = q.filter(GoodsReceipt.receipt_date <= dt)

    receipts_list = q.order_by(GoodsReceipt.created_at.desc()).all()
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()

    return render_template('warehouse/receipts.html',
                           receipts=receipts_list, suppliers=suppliers,
                           status_labels=RECEIPT_STATUS_LABELS)


@warehouse_bp.route('/receipts/new', methods=['GET', 'POST'])
@login_required
def receipt_new():
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    today_str = datetime.utcnow().strftime('%Y-%m-%d')

    if request.method == 'POST':
        # supplier_id comes from hidden field set by JS (or fallback select via JS)
        supplier_id = request.form.get('supplier_id', '').strip()
        po_id = request.form.get('purchase_order_id', '').strip() or None
        doc_number = request.form.get('doc_number', '').strip() or None
        receipt_date_raw = request.form.get('receipt_date', '').strip()
        comment = request.form.get('comment', '').strip() or None

        if not supplier_id:
            flash('Укажите поставщика.', 'warning')
            return render_template('warehouse/receipt_form.html',
                                   suppliers=suppliers, products=products, today=today_str)

        product_ids = request.form.getlist('product_id[]')
        qty_expected_list = request.form.getlist('qty_expected[]')
        qty_received_list = request.form.getlist('qty_received[]')
        unit_cost_list = request.form.getlist('unit_cost[]')

        if not product_ids:
            flash('Добавьте хотя бы одну позицию.', 'warning')
            return render_template('warehouse/receipt_form.html',
                                   suppliers=suppliers, products=products, today=today_str)

        receipt_date = datetime.strptime(receipt_date_raw, '%Y-%m-%d') if receipt_date_raw else datetime.utcnow()

        receipt = GoodsReceipt(
            receipt_number=_next_receipt_number(),
            supplier_id=int(supplier_id),
            purchase_order_id=int(po_id) if po_id else None,
            receipt_date=receipt_date,
            doc_number=doc_number,
            status='draft',
            comment=comment,
            created_by=current_user.id,
        )
        db.session.add(receipt)
        db.session.flush()

        for i, pid in enumerate(product_ids):
            if not pid:
                continue
            try:
                qty_exp = int(qty_expected_list[i]) if i < len(qty_expected_list) and qty_expected_list[i] else 0
                qty_rec = int(qty_received_list[i]) if i < len(qty_received_list) and qty_received_list[i] else 0
                cost = float(unit_cost_list[i]) if i < len(unit_cost_list) and unit_cost_list[i] else 0.0
            except (ValueError, TypeError):
                qty_exp, qty_rec, cost = 0, 0, 0.0
            db.session.add(GoodsReceiptItem(
                receipt_id=receipt.id,
                product_id=int(pid),
                quantity_expected=qty_exp,
                quantity_received=qty_rec,
                unit_cost=cost,
            ))

        db.session.commit()
        flash(f'Приёмка {receipt.receipt_number} создана.', 'success')
        return redirect(url_for('warehouse_demo.receipt_detail', receipt_id=receipt.id))

    return render_template('warehouse/receipt_form.html',
                           suppliers=suppliers, products=products, today=today_str)


@warehouse_bp.route('/receipts/<int:receipt_id>')
@login_required
def receipt_detail(receipt_id):
    receipt = GoodsReceipt.query.get_or_404(receipt_id)
    return render_template('warehouse/receipt_detail.html',
                           receipt=receipt, status_labels=RECEIPT_STATUS_LABELS)


@warehouse_bp.route('/receipts/<int:receipt_id>/verify', methods=['POST'])
@login_required
def receipt_verify(receipt_id):
    receipt = GoodsReceipt.query.get_or_404(receipt_id)
    if receipt.status != 'draft':
        flash('Сверить можно только приёмку в статусе "Черновик".', 'warning')
        return redirect(url_for('warehouse_demo.receipt_detail', receipt_id=receipt_id))
    receipt.status = 'verified'
    db.session.commit()
    flash(f'Приёмка {receipt.receipt_number} подтверждена и сверена.', 'success')
    return redirect(url_for('warehouse_demo.receipt_detail', receipt_id=receipt_id))


@warehouse_bp.route('/receipts/<int:receipt_id>/post', methods=['POST'])
@login_required
def receipt_post(receipt_id):
    receipt = GoodsReceipt.query.get_or_404(receipt_id)
    if receipt.status != 'verified':
        flash('Оприходовать можно только сверенную приёмку.', 'warning')
        return redirect(url_for('warehouse_demo.receipt_detail', receipt_id=receipt_id))

    for item in receipt.items:
        stock = item.product.stock
        if not stock:
            stock = Stock(product_id=item.product_id, qty_on_hand=0, qty_reserved=0)
            db.session.add(stock)
            db.session.flush()
        stock.qty_on_hand += item.quantity_received
        stock.last_updated = datetime.utcnow()

    if receipt.purchase_order_id:
        po = PurchaseOrder.query.get(receipt.purchase_order_id)
        if po:
            po.status = 'received'

    receipt.status = 'posted'
    receipt.posted_at = datetime.utcnow()
    db.session.commit()
    flash(f'Приёмка {receipt.receipt_number} оприходована. Остатки обновлены.', 'success')
    return redirect(url_for('warehouse_demo.receipt_detail', receipt_id=receipt_id))


# ── Picking Orders ────────────────────────────────────────────────────────────

@warehouse_bp.route('/picking')
@login_required
def picking_list():
    status = request.args.get('status', '').strip()
    q = PickingOrder.query
    if status:
        q = q.filter(PickingOrder.status == status)
    picking_orders = q.order_by(PickingOrder.created_at.desc()).all()
    pickers = User.query.filter_by(is_active=True).order_by(User.username).all()
    return render_template('warehouse/picking_list.html',
                           picking_orders=picking_orders,
                           status_labels=PICKING_STATUS_LABELS,
                           status_badge=PICKING_STATUS_BADGE,
                           current_status=status,
                           pickers=pickers)


@warehouse_bp.route('/picking/create/<int:order_id>', methods=['POST'])
@login_required
def picking_create(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    existing = PickingOrder.query.filter_by(sales_order_id=order.id).filter(
        PickingOrder.status.in_(['new', 'in_progress', 'assembled'])
    ).first()
    if existing:
        flash(f'Для заказа {order.order_number} уже существует задание {existing.picking_number}.', 'warning')
        return redirect(url_for('warehouse_demo.picking_detail', pk_id=existing.id))

    pk = PickingOrder(
        picking_number=_next_picking_number(),
        sales_order_id=order.id,
        status='new',
        created_by=current_user.id,
    )
    db.session.add(pk)
    db.session.commit()
    flash(f'Задание на комплектовку {pk.picking_number} создано.', 'success')
    return redirect(url_for('warehouse_demo.picking_detail', pk_id=pk.id))


@warehouse_bp.route('/picking/<int:pk_id>')
@login_required
def picking_detail(pk_id):
    pk = PickingOrder.query.get_or_404(pk_id)
    pickers = User.query.filter_by(is_active=True).order_by(User.username).all()
    return render_template('warehouse/picking_detail.html',
                           pk=pk,
                           status_labels=PICKING_STATUS_LABELS,
                           status_badge=PICKING_STATUS_BADGE,
                           pickers=pickers)


@warehouse_bp.route('/picking/<int:pk_id>/start', methods=['POST'])
@login_required
def picking_start(pk_id):
    pk = PickingOrder.query.get_or_404(pk_id)
    if pk.status != 'new':
        flash('Начать можно только новое задание.', 'warning')
        return redirect(url_for('warehouse_demo.picking_detail', pk_id=pk_id))
    picker_id = request.form.get('picker_id', '').strip()
    pk.picker_id = int(picker_id) if picker_id else current_user.id
    pk.status = 'in_progress'
    pk.started_at = datetime.utcnow()
    pk.sales_order.status = 'picking'
    db.session.commit()
    flash(f'Комплектовка {pk.picking_number} начата.', 'success')
    return redirect(url_for('warehouse_demo.picking_detail', pk_id=pk_id))


@warehouse_bp.route('/picking/<int:pk_id>/assemble', methods=['POST'])
@login_required
def picking_assemble(pk_id):
    pk = PickingOrder.query.get_or_404(pk_id)
    if pk.status != 'in_progress':
        flash('Завершить сборку можно только для задания «В работе».', 'warning')
        return redirect(url_for('warehouse_demo.picking_detail', pk_id=pk_id))

    order = pk.sales_order
    for item in order.items:
        stock = item.product.stock if item.product else None
        if stock:
            if stock.qty_on_hand < item.quantity:
                flash(f'Недостаточно «{item.product.name}»: на складе {stock.qty_on_hand} шт., нужно {item.quantity}.', 'danger')
                return redirect(url_for('warehouse_demo.picking_detail', pk_id=pk_id))
            stock.qty_on_hand -= item.quantity
            stock.qty_reserved = max(0, (stock.qty_reserved or 0) - item.quantity)
            stock.last_updated = datetime.utcnow()

    pk.status = 'assembled'
    pk.assembled_at = datetime.utcnow()
    order.status = 'assembled'
    db.session.commit()
    flash(f'Заказ {order.order_number} собран, остатки списаны.', 'success')
    return redirect(url_for('warehouse_demo.picking_detail', pk_id=pk_id))


@warehouse_bp.route('/picking/<int:pk_id>/ship', methods=['POST'])
@login_required
def picking_ship(pk_id):
    pk = PickingOrder.query.get_or_404(pk_id)
    if pk.status != 'assembled':
        flash('Отгрузить можно только собранный заказ.', 'warning')
        return redirect(url_for('warehouse_demo.picking_detail', pk_id=pk_id))
    pk.status = 'shipped'
    pk.shipped_at = datetime.utcnow()
    pk.sales_order.status = 'in_transit'
    db.session.commit()
    flash(f'Заказ {pk.sales_order.order_number} отгружен.', 'success')
    return redirect(url_for('warehouse_demo.picking_detail', pk_id=pk_id))


@warehouse_bp.route('/picking/<int:pk_id>/export-docx')
@login_required
def picking_export_docx(pk_id):
    pk = PickingOrder.query.get_or_404(pk_id)
    company = CompanyProfile.query.first()
    buf = generate_picking_docx(pk, company)
    filename = f'Комплектовка_{pk.picking_number}.docx'
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )


# ── Order Assembly ────────────────────────────────────────────────────────────

@warehouse_bp.route('/assembly')
@login_required
def assembly():
    status = request.args.get('status', 'picking').strip()
    customer_q = request.args.get('customer', '').strip()

    from app.models import Customer
    q = SalesOrder.query
    if status:
        q = q.filter(SalesOrder.status == status)
    else:
        q = q.filter(SalesOrder.status.in_(['picking', 'assembled']))
    if customer_q:
        q = q.join(Customer).filter(Customer.name.ilike(f'%{customer_q}%'))

    orders = q.order_by(SalesOrder.created_at.desc()).all()
    return render_template('warehouse/assembly.html', orders=orders, current_status=status)


@warehouse_bp.route('/assembly/<int:order_id>/mark-assembled', methods=['POST'])
@login_required
def assembly_mark_assembled(order_id):
    order = SalesOrder.query.get_or_404(order_id)
    if order.status != 'picking':
        flash('Пометить как «Собран» можно только заказ в статусе «В комплектации».', 'warning')
        return redirect(url_for('warehouse_demo.assembly'))

    for item in order.items:
        stock = item.product.stock if item.product else None
        if stock:
            if stock.qty_on_hand < item.quantity:
                flash(f'Недостаточно товара «{item.product.name}» на складе ({stock.qty_on_hand} шт., нужно {item.quantity}).', 'danger')
                return redirect(url_for('warehouse_demo.assembly'))
            stock.qty_on_hand -= item.quantity
            stock.qty_reserved = max(0, (stock.qty_reserved or 0) - item.quantity)
            stock.last_updated = datetime.utcnow()

    order.status = 'assembled'
    db.session.commit()
    flash(f'Заказ {order.order_number} собран. Остатки списаны.', 'success')
    return redirect(url_for('warehouse_demo.assembly'))


# ── Inventory Counts ──────────────────────────────────────────────────────────

@warehouse_bp.route('/inventory')
@login_required
def inventory():
    status = request.args.get('status', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    q = InventoryCount.query
    if status:
        q = q.filter(InventoryCount.status == status)
    if date_from:
        q = q.filter(InventoryCount.count_date >= datetime.strptime(date_from, '%Y-%m-%d'))
    if date_to:
        dt = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        q = q.filter(InventoryCount.count_date <= dt)

    counts = q.order_by(InventoryCount.created_at.desc()).all()
    return render_template('warehouse/inventory.html',
                           counts=counts, status_labels=INV_STATUS_LABELS)


@warehouse_bp.route('/inventory/new', methods=['GET', 'POST'])
@login_required
def inventory_new():
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    if request.method == 'POST':
        count_date_raw = request.form.get('count_date', '').strip()
        comment = request.form.get('comment', '').strip() or None
        count_date = datetime.strptime(count_date_raw, '%Y-%m-%d') if count_date_raw else datetime.utcnow()

        ic = InventoryCount(
            count_number=_next_inv_number(),
            count_date=count_date,
            status='in_progress',
            comment=comment,
            created_by=current_user.id,
        )
        db.session.add(ic)
        db.session.flush()

        for p in products:
            db.session.add(InventoryCountItem(
                count_id=ic.id,
                product_id=p.id,
                qty_system=p.qty_on_hand,
                qty_actual=p.qty_on_hand,
            ))

        db.session.commit()
        flash(f'Инвентаризация {ic.count_number} создана. Заполните фактические остатки.', 'success')
        return redirect(url_for('warehouse_demo.inventory_edit', count_id=ic.id))

    return render_template('warehouse/inventory_form.html', products=products)


@warehouse_bp.route('/inventory/<int:count_id>/edit', methods=['GET', 'POST'])
@login_required
def inventory_edit(count_id):
    ic = InventoryCount.query.get_or_404(count_id)
    if ic.status == 'completed':
        flash('Завершённая инвентаризация доступна только для просмотра.', 'info')
        return redirect(url_for('warehouse_demo.inventory_detail', count_id=count_id))

    if request.method == 'POST':
        for item in ic.items:
            val = request.form.get(f'qty_actual_{item.id}', '').strip()
            try:
                item.qty_actual = max(0, int(val))
            except (ValueError, TypeError):
                item.qty_actual = item.qty_system
        db.session.commit()
        flash('Фактические остатки сохранены.', 'success')
        return redirect(url_for('warehouse_demo.inventory_edit', count_id=count_id))

    return render_template('warehouse/inventory_edit.html', ic=ic)


@warehouse_bp.route('/inventory/<int:count_id>')
@login_required
def inventory_detail(count_id):
    ic = InventoryCount.query.get_or_404(count_id)
    return render_template('warehouse/inventory_detail.html',
                           ic=ic, status_labels=INV_STATUS_LABELS)


@warehouse_bp.route('/inventory/<int:count_id>/complete', methods=['POST'])
@login_required
def inventory_complete(count_id):
    ic = InventoryCount.query.get_or_404(count_id)
    if ic.status != 'in_progress':
        flash('Завершить можно только инвентаризацию в работе.', 'warning')
        return redirect(url_for('warehouse_demo.inventory_detail', count_id=count_id))

    apply_adj = request.form.get('apply_adjustments') == 'on'
    if apply_adj:
        for item in ic.items:
            stock = item.product.stock
            if not stock:
                stock = Stock(product_id=item.product_id, qty_on_hand=0, qty_reserved=0)
                db.session.add(stock)
                db.session.flush()
            stock.qty_on_hand = item.qty_actual
            stock.last_updated = datetime.utcnow()

    ic.status = 'completed'
    ic.completed_at = datetime.utcnow()
    db.session.commit()
    if apply_adj:
        flash(f'Инвентаризация {ic.count_number} завершена. Остатки обновлены по факту.', 'success')
    else:
        flash(f'Инвентаризация {ic.count_number} завершена без корректировки остатков.', 'info')
    return redirect(url_for('warehouse_demo.inventory_detail', count_id=count_id))


# ── API helpers ───────────────────────────────────────────────────────────────

@warehouse_bp.route('/api/products')
@login_required
def api_products():
    q = request.args.get('q', '').strip()
    products = Product.query.filter(
        Product.name.ilike(f'%{q}%'), Product.is_active.is_(True)
    ).order_by(Product.name).limit(50).all()
    return jsonify([{
        'id': p.id, 'sku': p.sku, 'name': p.name,
        'unit': p.unit, 'stock': p.qty_on_hand,
        'retail_price': p.retail_price,
    } for p in products])


@warehouse_bp.route('/api/po-items/<int:po_id>')
@login_required
def api_po_items(po_id):
    po = PurchaseOrder.query.get_or_404(po_id)
    return jsonify([{
        'product_id': i.product_id,
        'product_name': i.product.name if i.product else '',
        'sku': i.product.sku if i.product else '',
        'unit': i.product.unit if i.product else '',
        'quantity': i.quantity,
        'unit_cost': i.unit_cost,
        'stock': i.product.qty_on_hand if i.product else 0,
    } for i in po.items])


@warehouse_bp.route('/api/purchase-orders')
@login_required
def api_purchase_orders():
    supplier_id = request.args.get('supplier_id', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    amount_min = request.args.get('amount_min', '').strip()
    amount_max = request.args.get('amount_max', '').strip()
    status = request.args.get('status', '').strip()

    q = PurchaseOrder.query
    if supplier_id:
        try:
            q = q.filter(PurchaseOrder.supplier_id == int(supplier_id))
        except ValueError:
            pass
    if status:
        q = q.filter(PurchaseOrder.status == status)
    else:
        q = q.filter(PurchaseOrder.status.in_(['pending', 'received']))
    if date_from:
        try:
            q = q.filter(PurchaseOrder.order_date >= datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            q = q.filter(PurchaseOrder.order_date <= dt)
        except ValueError:
            pass
    if amount_min:
        try:
            q = q.filter(PurchaseOrder.total_amount >= float(amount_min))
        except ValueError:
            pass
    if amount_max:
        try:
            q = q.filter(PurchaseOrder.total_amount <= float(amount_max))
        except ValueError:
            pass

    pos = q.order_by(PurchaseOrder.order_date.desc()).limit(50).all()
    return jsonify([{
        'id': po.id,
        'order_number': po.order_number,
        'supplier_id': po.supplier_id,
        'supplier_name': po.supplier.name if po.supplier else '—',
        'order_date': po.order_date.strftime('%d.%m.%Y') if po.order_date else '—',
        'status': po.status,
        'total_amount': po.total_amount or 0,
        'is_paid': po.is_paid,
        'items_count': len(po.items),
        'items': [{
            'product_id': i.product_id,
            'product_name': i.product.name if i.product else '',
            'sku': i.product.sku if i.product else '',
            'unit': i.product.unit if i.product else '',
            'quantity': i.quantity,
            'unit_cost': i.unit_cost,
            'stock': i.product.qty_on_hand if i.product else 0,
        } for i in po.items],
    } for po in pos])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _next_pr_number():
    stamp = datetime.now().strftime('%y%m')
    latest = (PurchaseRequest.query
               .filter(PurchaseRequest.request_number.like(f'PR-{stamp}-%'))
               .order_by(PurchaseRequest.id.desc()).first())
    if latest:
        try:
            suffix = int(latest.request_number.split('-')[-1])
            return f'PR-{stamp}-{suffix + 1:03d}'
        except ValueError:
            pass
    return f'PR-{stamp}-001'


def _next_po_number():
    stamp = datetime.now().strftime('%y%m')
    latest = (PurchaseOrder.query
               .filter(PurchaseOrder.order_number.like(f'PO-{stamp}-%'))
               .order_by(PurchaseOrder.id.desc()).first())
    if latest:
        try:
            suffix = int(latest.order_number.split('-')[-1])
            return f'PO-{stamp}-{suffix + 1:03d}'
        except ValueError:
            pass
    return f'PO-{stamp}-001'


def _next_picking_number():
    stamp = datetime.now().strftime('%y%m')
    latest = (PickingOrder.query
               .filter(PickingOrder.picking_number.like(f'PK-{stamp}-%'))
               .order_by(PickingOrder.id.desc()).first())
    if latest:
        try:
            suffix = int(latest.picking_number.split('-')[-1])
            return f'PK-{stamp}-{suffix + 1:03d}'
        except ValueError:
            pass
    return f'PK-{stamp}-001'


def _next_receipt_number():
    stamp = datetime.now().strftime('%y%m')
    latest = (GoodsReceipt.query
               .filter(GoodsReceipt.receipt_number.like(f'GR-{stamp}-%'))
               .order_by(GoodsReceipt.id.desc()).first())
    if latest:
        try:
            suffix = int(latest.receipt_number.split('-')[-1])
            return f'GR-{stamp}-{suffix + 1:03d}'
        except ValueError:
            pass
    return f'GR-{stamp}-001'


def _next_inv_number():
    stamp = datetime.now().strftime('%y%m')
    latest = (InventoryCount.query
               .filter(InventoryCount.count_number.like(f'INV-{stamp}-%'))
               .order_by(InventoryCount.id.desc()).first())
    if latest:
        try:
            suffix = int(latest.count_number.split('-')[-1])
            return f'INV-{stamp}-{suffix + 1:03d}'
        except ValueError:
            pass
    return f'INV-{stamp}-001'
