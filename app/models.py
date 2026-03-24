from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User model for authentication"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_finance = db.Column(db.Boolean, default=False)
    is_data_admin = db.Column(db.Boolean, default=False)
    is_data_editor = db.Column(db.Boolean, default=False)
    is_data_viewer = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'


class Customer(db.Model):
    """Customer model"""
    __tablename__ = 'customers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    type = db.Column(db.String(50), default='individual')  # 'individual' or 'legal_entity'
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
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    inn = db.Column(db.String(12))
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
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    items = db.relationship('SalesOrderItem', backref='sales_order', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='sales_order', lazy=True, cascade='all, delete-orphan')
    
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
