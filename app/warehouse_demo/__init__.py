from flask import Blueprint

warehouse_bp = Blueprint('warehouse_demo', __name__, url_prefix='/warehouse')

from app.warehouse_demo import routes
