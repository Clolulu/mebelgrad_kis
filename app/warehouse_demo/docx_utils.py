"""Word-document generation utilities for the warehouse module."""
from __future__ import annotations

import os
import urllib.request
import tempfile
from io import BytesIO
from datetime import datetime

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ── helpers ────────────────────────────────────────────────────────────────────

def _set_cell_bg(cell, hex_color: str):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def _cell_borders(cell, top=True, bottom=True, left=True, right=True, color='999999', sz='4'):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for side, flag in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        if flag:
            el = OxmlElement(f'w:{side}')
            el.set(qn('w:val'), 'single')
            el.set(qn('w:sz'), sz)
            el.set(qn('w:color'), color)
            tcBorders.append(el)
    tcPr.append(tcBorders)


def _para_font(para, bold=False, size=None, color=None, align=None):
    for run in para.runs:
        if bold is not None:
            run.bold = bold
        if size:
            run.font.size = Pt(size)
        if color:
            run.font.color.rgb = RGBColor(*bytes.fromhex(color))
    if align:
        para.alignment = align


def _add_run(para, text, bold=False, size=10, color=None, italic=False):
    run = para.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.italic = italic
    if color:
        run.font.color.rgb = RGBColor(*bytes.fromhex(color))
    return run


def _download_image(url: str) -> str | None:
    """Download image from URL to a temp file; return path or None."""
    if not url:
        return None
    try:
        if url.startswith('/') or url.startswith('static/'):
            # local file path relative to project root
            base = os.path.join(os.path.dirname(__file__), '..', '..')
            local = os.path.join(base, url.lstrip('/'))
            if os.path.exists(local):
                return local
            return None
        suffix = '.png' if 'png' in url else '.jpg'
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        urllib.request.urlretrieve(url, tmp.name)
        return tmp.name
    except Exception:
        return None


def _sig_block(table, col_idx, title: str, name: str, sig_url: str | None, date_str: str):
    """Fill one column of the 3-column signature table."""
    cell = table.cell(0, col_idx)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM

    # title
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(p, title, bold=True, size=9)

    # signature image or blank line
    p2 = cell.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if sig_url:
        img_path = _download_image(sig_url)
        if img_path:
            try:
                run = p2.add_run()
                run.add_picture(img_path, height=Cm(1.5))
            except Exception:
                _add_run(p2, ' ' * 30, size=10)
        else:
            _add_run(p2, ' ' * 30, size=10)
    else:
        _add_run(p2, ' ' * 30, size=10)

    # underline for name
    p3 = cell.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p3.add_run('_' * 28)
    r.font.size = Pt(9)

    # name
    p4 = cell.add_paragraph()
    p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(p4, name or '________________________', size=9, color='666666', italic=True)

    # date
    p5 = cell.add_paragraph()
    p5.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(p5, date_str, size=8, color='888888')


# ── picking doc generator ─────────────────────────────────────────────────────

def generate_picking_docx(pk, company) -> BytesIO:
    """Задание на комплектовку в формате .docx."""
    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(1.5)
    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(10)

    order = pk.sales_order
    customer = order.customer if order else None

    # ── Центрированная шапка компании ────────────────────────────────────────
    if company:
        name_line = f'{company.legal_form} «{company.company_name}»' if company.legal_form and company.company_name else (company.company_name or '')
        p_name = doc.add_paragraph()
        p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(p_name, name_line, bold=True, size=12)

        addr_parts = []
        if company.legal_address:
            addr_parts.append(company.legal_address)
        if company.phone:
            addr_parts.append(f'тел. {company.phone}')
        if addr_parts:
            p_addr = doc.add_paragraph()
            p_addr.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_run(p_addr, ', '.join(addr_parts), size=9, color='444444')

        inn_parts = []
        if company.inn: inn_parts.append(f'ИНН {company.inn}')
        if company.kpp: inn_parts.append(f'КПП {company.kpp}')
        if company.ogrn: inn_parts.append(f'ОГРН {company.ogrn}')
        if inn_parts:
            p_inn = doc.add_paragraph()
            p_inn.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_run(p_inn, ', '.join(inn_parts), size=9, color='444444')

    # ── Заголовок ─────────────────────────────────────────────────────────────
    doc.add_paragraph()
    created_str = pk.created_at.strftime('%d.%m.%Y') if pk.created_at else datetime.utcnow().strftime('%d.%m.%Y')
    tp = doc.add_paragraph()
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(tp, 'ЗАДАНИЕ НА КОМПЛЕКТОВКУ', bold=True, size=14)
    sp = doc.add_paragraph()
    sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(sp, f'№ {pk.picking_number}  от  {created_str}', size=12)
    doc.add_paragraph()

    # ── Мета-таблица ──────────────────────────────────────────────────────────
    meta_rows = [
        ('Номер заказа', order.order_number if order else '—'),
        ('Дата заказа', order.order_date.strftime('%d.%m.%Y') if order and order.order_date else '—'),
        ('Клиент', customer.name if customer else '—'),
        ('Телефон клиента', customer.phone if customer else '—'),
        ('Адрес доставки', order.delivery_address if order and order.delivery_address else '—'),
        ('Комплектовщик', pk.picker.username if pk.picker else '—'),
        ('Статус', PICKING_DOC_STATUS.get(pk.status, pk.status)),
    ]
    info = doc.add_table(rows=len(meta_rows), cols=2)
    info.style = 'Table Grid'
    info.columns[0].width = Cm(5)
    info.columns[1].width = Cm(11.5)
    for ri, (label, value) in enumerate(meta_rows):
        lc = info.cell(ri, 0)
        _set_cell_bg(lc, 'EBF3FA')
        _add_run(lc.paragraphs[0], label, bold=True, size=9)
        _add_run(info.cell(ri, 1).paragraphs[0], value or '—', size=9)

    doc.add_paragraph()

    # ── Таблица позиций ───────────────────────────────────────────────────────
    p_lbl = doc.add_paragraph()
    _add_run(p_lbl, 'Табличная часть заявки:', bold=True, size=10)

    items = order.items if order else []
    headers2 = ['№', 'Артикул', 'Наименование товара', 'Ед. изм.', 'Кол-во', 'На складе', '✓ Выдано']
    col_w2 = [Cm(0.8), Cm(2.0), Cm(5.7), Cm(1.5), Cm(1.5), Cm(2.0), Cm(3.0)]
    tbl = doc.add_table(rows=1 + len(items) + 1, cols=7)
    tbl.style = 'Table Grid'
    for i, w in enumerate(col_w2):
        for row in tbl.rows:
            row.cells[i].width = w

    for ci, hdr in enumerate(headers2):
        cell = tbl.cell(0, ci)
        _set_cell_bg(cell, TABLE_HEADER_COLOR)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(p, hdr, bold=True, size=9)

    total_qty = 0
    for ri, item in enumerate(items, start=1):
        bg = ALT_ROW_COLOR if ri % 2 == 0 else 'FFFFFF'
        stock_qty = item.product.qty_on_hand if item.product else 0
        qty = item.quantity or 0
        total_qty += qty
        ok = stock_qty >= qty
        vals2 = [
            (str(ri), WD_ALIGN_PARAGRAPH.CENTER),
            (item.product.sku if item.product else '—', WD_ALIGN_PARAGRAPH.CENTER),
            (item.product.name if item.product else '—', WD_ALIGN_PARAGRAPH.LEFT),
            (item.product.unit if item.product else '—', WD_ALIGN_PARAGRAPH.CENTER),
            (str(qty), WD_ALIGN_PARAGRAPH.CENTER),
            (str(stock_qty), WD_ALIGN_PARAGRAPH.CENTER),
            ('', WD_ALIGN_PARAGRAPH.CENTER),
        ]
        for ci, (val, align) in enumerate(vals2):
            c2 = tbl.cell(ri, ci)
            _set_cell_bg(c2, bg)
            p2 = c2.paragraphs[0]
            p2.alignment = align
            run = _add_run(p2, val, size=9)
            if ci == 5:
                run.font.color.rgb = RGBColor(0x19, 0x87, 0x54) if ok else RGBColor(0xDC, 0x35, 0x45)

    total_row_idx = len(items) + 1
    tot_left = tbl.cell(total_row_idx, 0)
    tot_left.merge(tbl.cell(total_row_idx, 4))
    _set_cell_bg(tot_left, TABLE_HEADER_COLOR)
    tp2 = tot_left.paragraphs[0]
    tp2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _add_run(tp2, 'Итого:', bold=True, size=9)
    for ci in range(5, 7):
        _set_cell_bg(tbl.cell(total_row_idx, ci), TABLE_HEADER_COLOR)
    _add_run(tbl.cell(total_row_idx, 4).paragraphs[0], str(total_qty), bold=True, size=9)

    # ── Журнал хронологии ─────────────────────────────────────────────────────
    doc.add_paragraph()
    log_rows = [
        ('Задание создано', pk.created_at.strftime('%d.%m.%Y %H:%M') if pk.created_at else '—'),
        ('Комплектовка начата', pk.started_at.strftime('%d.%m.%Y %H:%M') if pk.started_at else '—'),
        ('Собрано', pk.assembled_at.strftime('%d.%m.%Y %H:%M') if pk.assembled_at else '—'),
        ('Отгружено', pk.shipped_at.strftime('%d.%m.%Y %H:%M') if pk.shipped_at else '—'),
    ]
    comment_tbl = doc.add_table(rows=len(log_rows), cols=2)
    comment_tbl.style = 'Table Grid'
    comment_tbl.columns[0].width = Cm(5)
    comment_tbl.columns[1].width = Cm(11.5)
    for ri, (label, val) in enumerate(log_rows):
        lc = comment_tbl.cell(ri, 0)
        _set_cell_bg(lc, 'EBF3FA')
        _add_run(lc.paragraphs[0], label, bold=True, size=9)
        _add_run(comment_tbl.cell(ri, 1).paragraphs[0], val, size=9)

    doc.add_paragraph()
    doc.add_paragraph()

    # ── Подписи (3 колонки) ───────────────────────────────────────────────────
    picker_name = pk.picker.username if pk.picker else '________________________'
    sig_tbl = doc.add_table(rows=1, cols=3)
    sig_tbl.style = 'Table Grid'
    sig_tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    for col in sig_tbl.columns:
        col.width = Cm(5.5)

    _sig_block(sig_tbl, 0, 'Комплектовал', picker_name, None,
               pk.assembled_at.strftime('%d.%m.%Y') if pk.assembled_at else '«__» ________ 20__ г.')
    _sig_block(sig_tbl, 1, 'Проверил', '________________________', None, '«__» ________ 20__ г.')
    _sig_block(sig_tbl, 2, 'Отгрузил', '________________________',
               company.seal_url if company else None,
               pk.shipped_at.strftime('%d.%m.%Y') if pk.shipped_at else '«__» ________ 20__ г.')

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# ── main generator ─────────────────────────────────────────────────────────────

PRIORITY_LABELS = {
    'low': 'Низкий', 'normal': 'Обычный', 'high': 'Высокий', 'urgent': 'Срочный',
}

STATUS_LABELS = {
    'draft': 'Черновик', 'submitted': 'На согласовании',
    'approved': 'Одобрена', 'rejected': 'Отклонена', 'ordered': 'Передана в заказ',
}

TABLE_HEADER_COLOR = 'D6E4F0'
ALT_ROW_COLOR = 'F7FAFD'

PICKING_DOC_STATUS = {
    'new': 'Новое',
    'in_progress': 'В работе',
    'assembled': 'Собрано',
    'shipped': 'Отгружено',
}


def generate_purchase_request_docx(pr, company) -> BytesIO:
    """
    Generate a .docx for the given PurchaseRequest object.
    `company` may be None (CompanyProfile instance or None).
    Returns a BytesIO buffer ready to be sent as file response.
    """
    doc = Document()

    for section in doc.sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(1.5)

    style = doc.styles['Normal']
    style.font.name = 'Times New Roman'
    style.font.size = Pt(10)

    # ── HEADER: центрированные реквизиты компании ────────────────────────────
    if company:
        name_line = f'{company.legal_form} «{company.company_name}»' if company.legal_form and company.company_name else (company.company_name or '')
        p_name = doc.add_paragraph()
        p_name.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(p_name, name_line, bold=True, size=12)

        reqs = []
        if company.legal_address:
            reqs.append(company.legal_address)
        contacts = []
        if company.phone:
            contacts.append(f'тел. {company.phone}')
        if contacts:
            reqs.extend(contacts)
        if reqs:
            p_addr = doc.add_paragraph()
            p_addr.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_run(p_addr, ', '.join(reqs), size=9, color='444444')

        inn_parts = []
        if company.inn:
            inn_parts.append(f'ИНН {company.inn}')
        if company.kpp:
            inn_parts.append(f'КПП {company.kpp}')
        if company.ogrn:
            inn_parts.append(f'ОГРН {company.ogrn}')
        if inn_parts:
            p_inn = doc.add_paragraph()
            p_inn.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_run(p_inn, ', '.join(inn_parts), size=9, color='444444')

    # ── DOCUMENT TITLE ───────────────────────────────────────────────────────
    doc.add_paragraph()
    date_str = pr.request_date.strftime('%d.%m.%Y') if pr.request_date else datetime.utcnow().strftime('%d.%m.%Y')
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(title_p, 'ЗАЯВКА НА ЗАКУПКУ', bold=True, size=14)
    sub_p = doc.add_paragraph()
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _add_run(sub_p, f'№ {pr.request_number}  от  {date_str}', bold=False, size=12)

    doc.add_paragraph()

    # ── META INFO TABLE ───────────────────────────────────────────────────────
    initiator_name = pr.creator.username if pr.creator else '—'
    notes = pr.comment or '—'

    meta_rows = [
        ('Инициатор', initiator_name),
        ('Поставщик', pr.supplier.name if pr.supplier else '—'),
        ('Основание', notes),
        ('Приоритет', PRIORITY_LABELS.get(pr.priority, pr.priority or '—')),
        ('Требуемая дата поставки', pr.needed_by_date.strftime('%d.%m.%Y') if pr.needed_by_date else '—'),
        ('Статус', STATUS_LABELS.get(pr.status, pr.status or '—')),
    ]

    meta = doc.add_table(rows=len(meta_rows), cols=4)
    meta.style = 'Table Grid'
    meta.alignment = WD_TABLE_ALIGNMENT.LEFT
    meta.columns[0].width = Cm(4.5)
    meta.columns[1].width = Cm(7.5)
    meta.columns[2].width = Cm(0.1)
    meta.columns[3].width = Cm(4.4)

    for ri, (label, value) in enumerate(meta_rows):
        lc = meta.cell(ri, 0)
        _set_cell_bg(lc, 'EBF3FA')
        _add_run(lc.paragraphs[0], label, bold=True, size=9)
        vc = meta.cell(ri, 1)
        _add_run(vc.paragraphs[0], value, size=9)
        meta.cell(ri, 1).merge(meta.cell(ri, 3))

    doc.add_paragraph()

    # ── ITEMS TABLE ──────────────────────────────────────────────────────────
    p_items_lbl = doc.add_paragraph()
    _add_run(p_items_lbl, 'Табличная часть заявки:', bold=True, size=10)

    col_widths = [Cm(0.8), Cm(2.0), Cm(5.5), Cm(1.5), Cm(1.5), Cm(2.7), Cm(2.5)]
    headers = ['№', 'Артикул', 'Наименование', 'Ед. изм.', 'Кол-во', 'Ориентировочная цена', 'Сумма']
    n_items = len(pr.items)
    items_table = doc.add_table(rows=1 + n_items + 1, cols=7)
    items_table.style = 'Table Grid'

    for i, w in enumerate(col_widths):
        for row in items_table.rows:
            row.cells[i].width = w

    for ci, hdr in enumerate(headers):
        cell = items_table.cell(0, ci)
        _set_cell_bg(cell, TABLE_HEADER_COLOR)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(p, hdr, bold=True, size=9)

    total = 0.0
    for ri, item in enumerate(pr.items, start=1):
        qty = item.quantity or 0
        price = item.estimated_cost or 0.0
        subtotal = qty * price
        total += subtotal
        bg = ALT_ROW_COLOR if ri % 2 == 0 else 'FFFFFF'
        vals = [
            (str(ri), WD_ALIGN_PARAGRAPH.CENTER),
            (item.product.sku if item.product else '—', WD_ALIGN_PARAGRAPH.CENTER),
            (item.product.name if item.product else '—', WD_ALIGN_PARAGRAPH.LEFT),
            (item.product.unit if item.product else '—', WD_ALIGN_PARAGRAPH.CENTER),
            (str(qty), WD_ALIGN_PARAGRAPH.CENTER),
            (f'{price:,.2f}'.replace(',', ' '), WD_ALIGN_PARAGRAPH.RIGHT),
            (f'{subtotal:,.2f}'.replace(',', ' '), WD_ALIGN_PARAGRAPH.RIGHT),
        ]
        for ci, (val, align) in enumerate(vals):
            cell = items_table.cell(ri, ci)
            _set_cell_bg(cell, bg)
            p = cell.paragraphs[0]
            p.alignment = align
            _add_run(p, val, size=9)

    total_row_idx = n_items + 1
    total_left = items_table.cell(total_row_idx, 0)
    total_left.merge(items_table.cell(total_row_idx, 5))
    _set_cell_bg(total_left, TABLE_HEADER_COLOR)
    tp = total_left.paragraphs[0]
    tp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _add_run(tp, 'Итого:', bold=True, size=9)
    total_right = items_table.cell(total_row_idx, 6)
    _set_cell_bg(total_right, TABLE_HEADER_COLOR)
    trp = total_right.paragraphs[0]
    trp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _add_run(trp, f'{total:,.2f}'.replace(',', ' '), bold=True, size=9)

    # ── COMMENT BELOW TABLE ──────────────────────────────────────────────────
    doc.add_paragraph()
    comment_tbl = doc.add_table(rows=1, cols=1)
    comment_tbl.style = 'Table Grid'
    comment_tbl.columns[0].width = Cm(16.5)
    cc = comment_tbl.cell(0, 0)
    _add_run(cc.paragraphs[0], f'Комментарий: {pr.comment or "—"}', size=9)

    doc.add_paragraph()
    doc.add_paragraph()

    # ── SIGNATURE BLOCKS (2 колонки: Составил / Согласовал) ──────────────────
    today = datetime.utcnow().strftime('%d.%m.%Y')
    approved_date = pr.approved_at.strftime('%d.%m.%Y') if pr.approved_at else '«__» ________ 20__ г.'
    creator_name = pr.creator.username if pr.creator else '________________________'
    approver_name = pr.approver.username if pr.approver else '________________________'

    sig_table = doc.add_table(rows=1, cols=2)
    sig_table.style = 'Table Grid'
    sig_table.alignment = WD_TABLE_ALIGNMENT.LEFT
    sig_table.columns[0].width = Cm(8)
    sig_table.columns[1].width = Cm(8.5)

    _sig_block(sig_table, 0, 'Составил', creator_name,
               company.ceo_signature_url if (company and pr.creator and getattr(pr.creator, 'is_admin', False)) else None,
               pr.created_at.strftime('%d.%m.%Y') if pr.created_at else today)
    _sig_block(sig_table, 1, 'Согласовал', approver_name,
               company.seal_url if company else None,
               approved_date)

    # ── FOOTER ───────────────────────────────────────────────────────────────
    if company and company.print_footer:
        doc.add_paragraph()
        fp = doc.add_paragraph()
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _add_run(fp, company.print_footer, size=8, color='888888', italic=True)

    # ── serialize to BytesIO ──────────────────────────────────────────────────
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
