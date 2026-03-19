from flask import Blueprint

sales_bp = Blueprint('sales_demo', __name__, url_prefix='/sales', template_folder='../templates/demo')

from app.sales_demo import routes
