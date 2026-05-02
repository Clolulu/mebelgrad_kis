"""
Seeder script to populate test sales orders with delivery addresses in Vladivostok
"""
import sys
from datetime import datetime, timedelta

from app import create_app, db
from app.models import Customer, Product, SalesOrder, SalesOrderItem, SalesOrderAttachment

app = create_app()

with app.app_context():
    # Get or create test customer
    customer = Customer.query.filter_by(name="Тестовый клиент").first()
    if not customer:
        customer = Customer(
            name="Тестовый клиент",
            phone="+79991234567",
            email="test@example.com",
            type="individual",
            is_active=True,
        )
        db.session.add(customer)
        db.session.flush()
    
    # Get first active product
    product = Product.query.filter_by(is_active=True).first()
    if not product:
        print("No active products found. Skipping seeder.")
        sys.exit(1)
    
    # Base address in Vladivostok
    base_address = "г. Владивосток, ул. Светланская, д. {}"
    
    # Define order statuses and their count (2 per status)
    statuses_with_dates = [
        ("unpaid", 0),
        ("picking", 1),
        ("assembled", 2),
        ("in_transit", 3),
        ("completed", 4),
    ]
    
    # Delete existing test orders (optional)
    for order in SalesOrder.query.filter(SalesOrder.order_number.like("SO-SEED%")).all():
        db.session.delete(order)
    db.session.commit()
    
    # Create 2 orders for each status
    for status, day_offset in statuses_with_dates:
        for i in range(2):
            order_number = f"SO-SEED-{status}-{i+1:02d}"
            created_at = datetime.utcnow() - timedelta(days=day_offset)
            
            order = SalesOrder(
                order_number=order_number,
                customer_id=customer.id,
                status=status,
                delivery_address=base_address.format(10 + i),
                needs_assembly=(i == 0),  # First order with assembly
                created_at=created_at,
                total_amount=2000.0 if i == 0 else 1000.0,
            )
            
            db.session.add(order)
            db.session.flush()
            
            # Add order item
            order_item = SalesOrderItem(
                sales_order_id=order.id,
                product_id=product.id,
                quantity=2 if i == 0 else 1,
                unit_price=product.retail_price or 500.0,
                cost_price=0.0,
                product_group="general",
            )
            db.session.add(order_item)
            
            # Add attachment for in_transit and completed orders
            if status in ["in_transit", "completed"]:
                attachment = SalesOrderAttachment(
                    sales_order_id=order.id,
                    kind="delivery_doc",
                    stored_path="uploads/sales_orders/test/test_doc.pdf",
                    original_filename="акт_доставки.pdf",
                )
                db.session.add(attachment)
            
            # Set delivery_confirmed_at for completed orders
            if status == "completed":
                order.delivery_confirmed_at = created_at + timedelta(days=1)
            
            # Set cancel_reason for any future cancelled orders
            if status == "cancelled":
                order.cancel_reason = "Клиент отказался"
    
    db.session.commit()
    print("✓ Seeder completed: 10 test orders created in Vladivostok")
