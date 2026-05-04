import re
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, current_user
from sqlalchemy import event, inspect
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User model for authentication"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_finance = db.Column(db.Boolean, default=False)
    is_data_admin = db.Column(db.Boolean, default=False)
    is_data_editor = db.Column(db.Boolean, default=False)
    is_data_viewer = db.Column(db.Boolean, default=False)
    # New role system: админ, финансист, кладовщик, Продавец
    role_admin = db.Column(db.Boolean, default=False)  # админ
    role_financier = db.Column(db.Boolean, default=False)  # финансист
    role_warehouse = db.Column(db.Boolean, default=False)  # кладовщик
    role_seller = db.Column(db.Boolean, default=False)  # Продавец
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

    @property
    def role_name(self):
        if self.role_admin:
            return "admin"
        if self.role_financier:
            return "finance"
        if self.role_warehouse:
            return "warehouse"
        if self.role_seller:
            return "seller"
        return None

    @property
    def role_label(self):
        return {
            "admin": "Админ",
            "finance": "Финансист",
            "warehouse": "Кладовщик",
            "seller": "Продавец",
        }.get(self.role_name, "Нет роли")

    @property
    def role_permission(self):
        if not self.role_name:
            return None
        return RolePermission.query.filter_by(role_name=self.role_name).first()

    @property
    def can_view_mdm(self):
        if self.is_admin:
            return True
        permissions = self.role_permission
        return bool(
            (permissions and (permissions.can_view_mdm or permissions.can_edit_mdm))
            or self.is_data_admin
            or self.is_data_editor
            or self.is_data_viewer
        )

    @property
    def can_edit_mdm(self):
        if self.is_admin:
            return True
        permissions = self.role_permission
        return bool(
            (permissions and permissions.can_edit_mdm)
            or self.is_data_admin
            or self.is_data_editor
        )

    @property
    def can_view_finance(self):
        if self.is_admin:
            return True
        permissions = self.role_permission
        return bool(
            (permissions and (permissions.can_view_finance or permissions.can_edit_finance))
            or self.is_finance
        )

    @property
    def can_edit_finance(self):
        if self.is_admin:
            return True
        permissions = self.role_permission
        return bool(
            (permissions and permissions.can_edit_finance)
            or self.is_finance
        )

    @property
    def can_view_warehouse(self):
        if self.is_admin:
            return True
        permissions = self.role_permission
        return bool(
            permissions and (permissions.can_view_warehouse or permissions.can_edit_warehouse)
        )

    @property
    def can_edit_warehouse(self):
        if self.is_admin:
            return True
        permissions = self.role_permission
        return bool(permissions and permissions.can_edit_warehouse)

    @property
    def can_view_sales(self):
        if self.is_admin:
            return True
        permissions = self.role_permission
        return bool(
            permissions and (permissions.can_view_sales or permissions.can_edit_sales)
        )

    @property
    def can_edit_sales(self):
        if self.is_admin:
            return True
        permissions = self.role_permission
        return bool(permissions and permissions.can_edit_sales)


class RolePermission(db.Model):
    __tablename__ = 'role_permissions'

    id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(50), nullable=False, unique=True)
    label = db.Column(db.String(50), nullable=False)
    can_view_mdm = db.Column(db.Boolean, default=False)
    can_edit_mdm = db.Column(db.Boolean, default=False)
    can_view_finance = db.Column(db.Boolean, default=False)
    can_edit_finance = db.Column(db.Boolean, default=False)
    can_view_warehouse = db.Column(db.Boolean, default=False)
    can_edit_warehouse = db.Column(db.Boolean, default=False)
    can_view_sales = db.Column(db.Boolean, default=False)
    can_edit_sales = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<RolePermission {self.role_name}>'


class Customer(db.Model):
    """Customer model"""
    __tablename__ = 'customers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), unique=True)
    email = db.Column(db.String(120), unique=True)
    type = db.Column(db.String(50), default='individual')  # 'individual' or 'legal_entity'
    birth_date = db.Column(db.Date)
    registration_address = db.Column(db.String(255))
    passport_series_number = db.Column(db.String(20))
    passport_issued_by = db.Column(db.String(255))
    passport_issue_date = db.Column(db.Date)
    snils = db.Column(db.String(20))
    customer_inn = db.Column(db.String(12))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    sales_orders = db.relationship('SalesOrder', backref='customer', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Customer {self.name}>'


class Supplier(db.Model):
    """Supplier model"""
    __tablename__ = 'suppliers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), unique=True)
    email = db.Column(db.String(120), unique=True)
    inn = db.Column(db.String(12), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    purchase_orders = db.relationship('PurchaseOrder', backref='supplier', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Supplier {self.name}>'


class Employee(db.Model):
    """Employee model"""
    __tablename__ = 'employees'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    position = db.Column(db.String(100))
    phone = db.Column(db.String(20), unique=True)
    email = db.Column(db.String(120), unique=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Employee {self.name}>'


class Product(db.Model):
    """Product/Nomenclature model"""
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    unit = db.Column(db.String(20), default='pcs')  # 'pcs' (шт) or 'set' (компл)
    retail_price = db.Column(db.Float, nullable=False, default=0.0)
    certificate_link = db.Column(db.String(500), default='https://davitamebel.ru/customers/deklaratsii-sootvetstviya/29112026.pdf?srsltid=AfmBOoroXcby5DgCGNkVqvZ3jBiV1LJ8IGsMgp7AKaqRFvWiDIr6ZXKM')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    stock = db.relationship('Stock', backref='product', uselist=False, cascade='all, delete-orphan')
    sales_order_items = db.relationship('SalesOrderItem', backref='product', lazy=True, cascade='all, delete-orphan')
    purchase_order_items = db.relationship('PurchaseOrderItem', backref='product', lazy=True, cascade='all, delete-orphan')
    
    @property
    def qty_on_hand(self):
        """Get current stock quantity"""
        if self.stock:
            return self.stock.qty_on_hand
        return 0
    
    @property
    def qty_reserved(self):
        """Get reserved stock quantity"""
        if self.stock:
            return self.stock.qty_reserved
        return 0
    
    def __repr__(self):
        return f'<Product {self.sku} - {self.name}>'


class Stock(db.Model):
    """Stock/Warehouse model"""
    __tablename__ = 'stock'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, unique=True)
    qty_on_hand = db.Column(db.Integer, default=0)
    qty_reserved = db.Column(db.Integer, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Stock Product {self.product_id}: {self.qty_on_hand}>'


class SalesOrder(db.Model):
    """Sales Order model"""
    __tablename__ = 'sales_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    segment = db.Column(db.String(50), default='retail')  # retail / b2b / service
    status = db.Column(db.String(50), default='pending')  # 'pending', 'completed', 'cancelled'
    total_amount = db.Column(db.Float, default=0.0)
    needs_assembly = db.Column(db.Boolean, default=False)
    cancel_reason = db.Column(db.Text)
    delivery_address = db.Column(db.String(255))
    delivery_confirmed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    items = db.relationship('SalesOrderItem', backref='sales_order', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='sales_order', lazy=True, cascade='all, delete-orphan')
    attachments = db.relationship('SalesOrderAttachment', backref='sales_order', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<SalesOrder {self.order_number}>'


class SalesOrderItem(db.Model):
    """Sales Order Item model"""
    __tablename__ = 'sales_order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey('sales_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    cost_price = db.Column(db.Float, default=0.0)  # For calculating COGS
    product_group = db.Column(db.String(50), default='general')  # корпусная/мягкая/кухни/офис
    
    def __repr__(self):
        return f'<SalesOrderItem Order {self.sales_order_id} - Product {self.product_id}>'


class SalesOrderAttachment(db.Model):
    """Attachments uploaded in sales order processing workflow."""
    __tablename__ = 'sales_order_attachments'

    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey('sales_orders.id'), nullable=False)
    kind = db.Column(db.String(50), default='delivery_doc')
    stored_path = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploader = db.relationship('User', backref='sales_order_attachments')

    def __repr__(self):
        return f'<SalesOrderAttachment {self.id} for order {self.sales_order_id}>'


class Payment(db.Model):
    """Payment model (incoming payments from customers)"""
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey('sales_orders.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    fiscal_receipt_number = db.Column(db.String(50))
    status = db.Column(db.String(50), default='completed')  # 'completed', 'pending'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Payment {self.id} - Amount {self.amount}>'


class PurchaseOrder(db.Model):
    """Purchase Order model (for suppliers)"""
    __tablename__ = 'purchase_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending')  # 'pending', 'received', 'completed', 'cancelled'
    total_amount = db.Column(db.Float, default=0.0)
    is_paid = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    items = db.relationship('PurchaseOrderItem', backref='purchase_order', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<PurchaseOrder {self.order_number}>'


class PurchaseOrderItem(db.Model):
    """Purchase Order Item model"""
    __tablename__ = 'purchase_order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False)
    
    def __repr__(self):
        return f'<PurchaseOrderItem Order {self.purchase_order_id} - Product {self.product_id}>'


class BudgetItem(db.Model):
    """Budget Item model for financial planning"""
    __tablename__ = 'budget_items'
    
    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(20), nullable=False)  # e.g., '2024-01', '2024-02'
    item_type = db.Column(db.String(50), nullable=False)  # 'income' or 'expense'
    category = db.Column(db.String(100), nullable=False)  # e.g., 'Sales', 'Purchases', 'Logistics'
    planned_amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<BudgetItem {self.period} - {self.category}: {self.planned_amount}>'


class InventoryBatch(db.Model):
    """Инвентарная партия для расчета COGS FIFO/средней"""
    __tablename__ = 'inventory_batches'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    received_date = db.Column(db.DateTime, default=datetime.utcnow)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False)
    transport_cost = db.Column(db.Float, default=0.0)
    quantity_consumed = db.Column(db.Integer, default=0)

    def available_quantity(self):
        return max(self.quantity - self.quantity_consumed, 0)


class IndirectExpense(db.Model):
    """Косвенные операционные расходы"""
    __tablename__ = 'indirect_expenses'

    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<IndirectExpense {self.period} - {self.category}: {self.amount}>'


class CashCalendarItem(db.Model):
    """Позиции платежного календаря"""
    __tablename__ = 'cash_calendar_items'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    direction = db.Column(db.String(20), nullable=False)  # incoming/outgoing
    cash_type = db.Column(db.String(20), nullable=False)  # operational/investment/financial
    counterparty_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    status = db.Column(db.String(20), default='planned')  # planned/confirmed/executed
    probability = db.Column(db.Float, default=1.0)
    comment = db.Column(db.String(255))

    def __repr__(self):
        return f'<CashCalendarItem {self.date.date()} {self.direction} {self.amount}>'


class BalanceSnapshot(db.Model):
    """Управленческий баланс на дату"""
    __tablename__ = 'balance_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    snapshot_date = db.Column(db.DateTime, nullable=False)
    total_assets = db.Column(db.Float, nullable=False)
    total_liabilities = db.Column(db.Float, nullable=False)
    equity = db.Column(db.Float, nullable=False)
    details = db.Column(db.String)

    def __repr__(self):
        return f'<BalanceSnapshot {self.snapshot_date.date()}: A{self.total_assets} L{self.total_liabilities} E{self.equity}>'


class PlanFactDeviation(db.Model):
    """Отклонения план-факт со статусом и причиной"""
    __tablename__ = 'plan_fact_deviations'

    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(20), nullable=False)
    item_name = db.Column(db.String(100), nullable=False)
    planned_value = db.Column(db.Float, default=0.0)
    actual_value = db.Column(db.Float, default=0.0)
    deviation = db.Column(db.Float, default=0.0)
    deviation_pct = db.Column(db.Float, default=0.0)
    reason = db.Column(db.String(255))
    entered_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<PlanFactDeviation {self.period} {self.item_name}: {self.deviation}>'


class CashAccount(db.Model):
    """Cash/bank account used by the finance workplace."""
    __tablename__ = 'cash_accounts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    account_type = db.Column(db.String(20), default='bank')  # bank/cash/demo
    bank_name = db.Column(db.String(255))
    account_number = db.Column(db.String(64))
    currency = db.Column(db.String(3), default='RUB')
    opening_balance = db.Column(db.Float, default=0.0)
    opening_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    transactions = db.relationship(
        'CashTransaction',
        backref='account',
        lazy=True,
        cascade='all, delete-orphan',
    )

    def __repr__(self):
        return f'<CashAccount {self.name}: {self.currency}>'


class FinanceArticle(db.Model):
    """Finance article shared by cash flow, P&L and budgets."""
    __tablename__ = 'finance_articles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    report_type = db.Column(db.String(20), default='both')  # bdds/bdr/both
    cash_flow_group = db.Column(db.String(20), default='operational')
    pnl_group = db.Column(db.String(20), default='other')
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<FinanceArticle {self.name}>'


class CashTransaction(db.Model):
    """Actual or planned cash movement imported from demo sources or entered manually."""
    __tablename__ = 'cash_transactions'

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('cash_accounts.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    amount = db.Column(db.Float, nullable=False)
    direction = db.Column(db.String(20), nullable=False)  # incoming/outgoing
    article_id = db.Column(db.Integer, db.ForeignKey('finance_articles.id'))
    counterparty = db.Column(db.String(255))
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    source = db.Column(db.String(30), default='manual')  # manual/demo_bank/1c/sales/purchase
    status = db.Column(db.String(20), default='executed')  # planned/confirmed/executed/cancelled
    description = db.Column(db.String(255))
    external_ref = db.Column(db.String(120), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    article = db.relationship('FinanceArticle', backref='cash_transactions')
    customer = db.relationship('Customer', backref='cash_transactions')
    supplier = db.relationship('Supplier', backref='cash_transactions')

    def signed_amount(self):
        return self.amount if self.direction == 'incoming' else -self.amount

    def __repr__(self):
        return f'<CashTransaction {self.date.date()} {self.direction} {self.amount}>'


class FixedAsset(db.Model):
    """Simplified management accounting fixed asset."""
    __tablename__ = 'fixed_assets'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    purchase_date = db.Column(db.DateTime, nullable=False)
    initial_cost = db.Column(db.Float, nullable=False, default=0.0)
    accumulated_depreciation = db.Column(db.Float, default=0.0)
    category = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)

    @property
    def carrying_amount(self):
        return max((self.initial_cost or 0) - (self.accumulated_depreciation or 0), 0)

    def __repr__(self):
        return f'<FixedAsset {self.name}: {self.carrying_amount}>'


class Loan(db.Model):
    """Demo loan/liability for management balance."""
    __tablename__ = 'loans'

    id = db.Column(db.Integer, primary_key=True)
    lender = db.Column(db.String(160), nullable=False, unique=True)
    principal = db.Column(db.Float, nullable=False, default=0.0)
    rate = db.Column(db.Float, default=0.0)
    start_date = db.Column(db.DateTime, nullable=False)
    due_date = db.Column(db.DateTime, nullable=False)
    outstanding_amount = db.Column(db.Float, nullable=False, default=0.0)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Loan {self.lender}: {self.outstanding_amount}>'


class BudgetScenario(db.Model):
    """Annual budget scenario with a demo approval status."""
    __tablename__ = 'budget_scenarios'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft/approved/archived
    version = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    lines = db.relationship(
        'BudgetLine',
        backref='scenario',
        lazy=True,
        cascade='all, delete-orphan',
    )

    __table_args__ = (
        db.UniqueConstraint('name', 'year', 'version', name='uq_budget_scenario_version'),
    )

    def __repr__(self):
        return f'<BudgetScenario {self.name} {self.year} v{self.version}>'


class BudgetLine(db.Model):
    """Monthly budget line by finance article."""
    __tablename__ = 'budget_lines'

    id = db.Column(db.Integer, primary_key=True)
    scenario_id = db.Column(db.Integer, db.ForeignKey('budget_scenarios.id'), nullable=False)
    period = db.Column(db.String(20), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('finance_articles.id'))
    category = db.Column(db.String(120))
    amount = db.Column(db.Float, nullable=False, default=0.0)
    department = db.Column(db.String(100))
    owner = db.Column(db.String(100))

    article = db.relationship('FinanceArticle', backref='budget_lines')

    def __repr__(self):
        return f'<BudgetLine {self.period} {self.category}: {self.amount}>'


class PaymentRequest(db.Model):
    """Demo payment request workflow, without real banking operations."""
    __tablename__ = 'payment_requests'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.DateTime, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    direction = db.Column(db.String(20), default='outgoing')
    article_id = db.Column(db.Integer, db.ForeignKey('finance_articles.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    status = db.Column(db.String(20), default='draft')  # draft/pending/approved/rejected/paid
    priority = db.Column(db.String(20), default='normal')
    comment = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved_at = db.Column(db.DateTime)

    article = db.relationship('FinanceArticle', backref='payment_requests')
    supplier = db.relationship('Supplier', backref='payment_requests')
    customer = db.relationship('Customer', backref='payment_requests')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_payment_requests')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_payment_requests')

    def __repr__(self):
        return f'<PaymentRequest {self.id}: {self.status} {self.amount}>'


class CompanyProfile(db.Model):
    """Реквизиты организации для печати отчётов"""
    __tablename__ = 'company_profile'

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(255), nullable=False)
    short_name = db.Column(db.String(50), nullable=False)
    legal_form = db.Column(db.String(20), default='ООО')  # ООО, АО, ИП
    inn = db.Column(db.String(12), nullable=False, unique=True)
    kpp = db.Column(db.String(9))
    ogrn = db.Column(db.String(13))
    okved = db.Column(db.String(20))  # Основной код ОКВЭД
    tax_system = db.Column(db.String(50))  # Система налогообложения
    employees_count = db.Column(db.Integer, default=0)  # Количество сотрудников
    
    # Адреса
    legal_address = db.Column(db.String(255), nullable=False)
    actual_address = db.Column(db.String(255))
    
    # Контакты
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    website = db.Column(db.String(255))
    
    # Банковские реквизиты
    bank_name = db.Column(db.String(255))
    bank_bik = db.Column(db.String(9))
    correspondent_account = db.Column(db.String(20))
    settlement_account = db.Column(db.String(20))
    
    # Руководство
    ceo = db.Column(db.String(255))  # Для ИП - ФИО ИП, для юр.лиц - ФИО руководителя
    ceo_position = db.Column(db.String(100))  # Должность руководителя (для юр.лиц)
    ceo_signature_url = db.Column(db.String(500))  # URL подписи руководителя
    signature_url = db.Column(db.String(500))  # URL подписи ИП
    chief_accountant_name = db.Column(db.String(255))
    chief_accountant_signature_url = db.Column(db.String(500))
    
    # Печать
    seal_url = db.Column(db.String(500))  # URL печати
    
    # Логотип
    logo_url = db.Column(db.String(500))
    
    # Параметры печати
    print_footer = db.Column(db.Text)  # Текст подвала
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<CompanyProfile {self.short_name}>'


class DuplicateAttempt(db.Model):
    """Журнал попыток создания дубликатов в мастер-данных"""
    __tablename__ = 'duplicate_attempts'

    id = db.Column(db.Integer, primary_key=True)
    entity = db.Column(db.String(50), nullable=False)
    attempted_record = db.Column(db.String(255))
    attempted_data = db.Column(db.Text)
    duplicate_fields = db.Column(db.String(255))
    source = db.Column(db.String(100), default='web')
    reason = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<DuplicateAttempt {self.entity} {self.duplicate_fields}>'


class AuditLog(db.Model):
    __tablename__ = 'audit_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    username = db.Column(db.String(120))
    entity = db.Column(db.String(100), nullable=False)
    entity_key = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    record_name = db.Column(db.String(255))
    record_meta = db.Column(db.String(255))
    details = db.Column(db.Text)
    status = db.Column(db.String(50), default='success')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<AuditLog {self.entity} {self.action}>'


class PurchaseRequest(db.Model):
    """Заявка на закупку (до превращения в PurchaseOrder)."""
    __tablename__ = 'purchase_requests'

    id = db.Column(db.Integer, primary_key=True)
    request_number = db.Column(db.String(50), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=True)
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    needed_by_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default='draft')  # draft/submitted/approved/rejected/ordered
    priority = db.Column(db.String(20), default='normal')  # low/normal/high/urgent
    comment = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('PurchaseRequestItem', backref='request', lazy=True, cascade='all, delete-orphan')
    supplier = db.relationship('Supplier', backref='purchase_requests')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_purchase_requests')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_purchase_requests')
    purchase_order = db.relationship('PurchaseOrder', backref='purchase_request', uselist=False)

    @property
    def total_estimated(self):
        return sum((i.estimated_cost or 0) * i.quantity for i in self.items)

    def __repr__(self):
        return f'<PurchaseRequest {self.request_number}: {self.status}>'


class PurchaseRequestItem(db.Model):
    """Позиция заявки на закупку."""
    __tablename__ = 'purchase_request_items'

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('purchase_requests.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    estimated_cost = db.Column(db.Float, default=0.0)
    comment = db.Column(db.String(255))

    product = db.relationship('Product', backref='purchase_request_items')

    def __repr__(self):
        return f'<PurchaseRequestItem req={self.request_id} prod={self.product_id} qty={self.quantity}>'


class GoodsReceipt(db.Model):
    """Приёмка товара от поставщика."""
    __tablename__ = 'goods_receipts'

    id = db.Column(db.Integer, primary_key=True)
    receipt_number = db.Column(db.String(50), unique=True, nullable=False)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    receipt_date = db.Column(db.DateTime, default=datetime.utcnow)
    doc_number = db.Column(db.String(50))
    status = db.Column(db.String(20), default='draft')  # draft/verified/posted
    comment = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    posted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('GoodsReceiptItem', backref='receipt', lazy=True, cascade='all, delete-orphan')
    supplier = db.relationship('Supplier', backref='goods_receipts')
    purchase_order = db.relationship('PurchaseOrder', backref='goods_receipts')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_goods_receipts')

    @property
    def total_amount(self):
        return sum((i.unit_cost or 0) * i.quantity_received for i in self.items)

    def __repr__(self):
        return f'<GoodsReceipt {self.receipt_number}: {self.status}>'


class GoodsReceiptItem(db.Model):
    """Позиция приёмки товара."""
    __tablename__ = 'goods_receipt_items'

    id = db.Column(db.Integer, primary_key=True)
    receipt_id = db.Column(db.Integer, db.ForeignKey('goods_receipts.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity_expected = db.Column(db.Integer, default=0)
    quantity_received = db.Column(db.Integer, nullable=False, default=0)
    unit_cost = db.Column(db.Float, default=0.0)

    product = db.relationship('Product', backref='goods_receipt_items')

    @property
    def discrepancy(self):
        return self.quantity_received - self.quantity_expected

    def __repr__(self):
        return f'<GoodsReceiptItem receipt={self.receipt_id} prod={self.product_id}>'


class InventoryCount(db.Model):
    """Инвентаризация складских запасов."""
    __tablename__ = 'inventory_counts'

    id = db.Column(db.Integer, primary_key=True)
    count_number = db.Column(db.String(50), unique=True, nullable=False)
    count_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='draft')  # draft/in_progress/completed
    comment = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('InventoryCountItem', backref='count', lazy=True, cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_inventory_counts')

    def __repr__(self):
        return f'<InventoryCount {self.count_number}: {self.status}>'


class InventoryCountItem(db.Model):
    """Позиция инвентаризации."""
    __tablename__ = 'inventory_count_items'

    id = db.Column(db.Integer, primary_key=True)
    count_id = db.Column(db.Integer, db.ForeignKey('inventory_counts.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    qty_system = db.Column(db.Integer, default=0)
    qty_actual = db.Column(db.Integer, default=0)

    product = db.relationship('Product', backref='inventory_count_items')

    @property
    def discrepancy(self):
        return self.qty_actual - self.qty_system

    def __repr__(self):
        return f'<InventoryCountItem count={self.count_id} prod={self.product_id}>'


def _normalize_phone_value(value):
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if not digits:
        return None
    return "+" + digits if not digits.startswith("+") else digits


def _normalize_email_value(value):
    if not value:
        return None
    return value.strip().lower() or None


def _normalize_inn_value(value):
    if not value:
        return None
    normalized = re.sub(r"\D", "", value)
    return normalized or None


@event.listens_for(db.session, "before_flush")
def _normalize_mdm_fields(session, flush_context, instances):
    for obj in list(session.new) + list(session.dirty):
        if hasattr(obj, "phone"):
            obj.phone = _normalize_phone_value(obj.phone)
        if hasattr(obj, "email"):
            obj.email = _normalize_email_value(obj.email)
        if hasattr(obj, "inn"):
            obj.inn = _normalize_inn_value(obj.inn)


def _get_audit_entity_data(obj):
    class_name = type(obj).__name__
    entity_map = {
        "Product": ("Номенклатура", "products"),
        "Customer": ("Клиенты", "customers"),
        "Supplier": ("Поставщики", "suppliers"),
        "Employee": ("Сотрудники", "employees"),
        "User": ("Пользователи системы", "users"),
        "CompanyProfile": ("Профиль компании", "company_profile"),
        "RolePermission": ("Роли пользователей", "roles"),
        "DuplicateAttempt": ("Контроль качества данных", "duplicate_attempts"),
    }
    return entity_map.get(class_name, (class_name, class_name.lower()))


def _get_audit_record_data(obj):
    record_name = None
    record_meta = None

    if hasattr(obj, "name"):
        record_name = obj.name
    elif hasattr(obj, "username"):
        record_name = obj.username
    elif hasattr(obj, "short_name"):
        record_name = obj.short_name

    if hasattr(obj, "sku"):
        record_meta = obj.sku
    elif hasattr(obj, "inn"):
        record_meta = obj.inn
    elif hasattr(obj, "position"):
        record_meta = obj.position
    elif hasattr(obj, "type"):
        record_meta = obj.type
    elif hasattr(obj, "email"):
        record_meta = obj.email

    return record_name, record_meta


def _get_changed_fields(obj):
    state = inspect(obj)
    changes = []
    for attr in state.attrs:
        if attr.history.has_changes():
            changes.append(attr.key)
    return changes


@event.listens_for(db.session, "after_flush")
def _record_audit_log(session, flush_context):
    if not hasattr(current_user, "is_authenticated"):
        return

    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if isinstance(obj, AuditLog):
            continue

        entity_label, entity_key = _get_audit_entity_data(obj)
        record_name, record_meta = _get_audit_record_data(obj)
        username = current_user.username if current_user.is_authenticated else "Система"
        user_id = current_user.id if current_user.is_authenticated else None

        if obj in session.new:
            action = "Создание записи"
            details = None
        elif obj in session.deleted:
            action = "Удаление записи"
            details = None
        else:
            changed = _get_changed_fields(obj)
            if not changed:
                continue
            action = "Изменение записи"
            details = f"Изменены поля: {', '.join(changed)}"

        if isinstance(obj, DuplicateAttempt) and obj in session.new:
            action = "Попытка создания дубликата"
            details = obj.reason

        log_entry = AuditLog(
            user_id=user_id,
            username=username,
            entity=entity_label,
            entity_key=entity_key,
            action=action,
            record_name=record_name,
            record_meta=record_meta,
            details=details,
            status="success",
        )
        session.add(log_entry)
