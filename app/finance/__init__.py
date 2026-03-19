from flask import Blueprint

finance_bp = Blueprint('finance', __name__, url_prefix='/finance', template_folder='../templates/finance')

from app.finance import routes
