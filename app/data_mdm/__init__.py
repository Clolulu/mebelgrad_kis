from flask import Blueprint

mdm_bp = Blueprint('mdm', __name__, url_prefix='/mdm', template_folder='../templates/data_mdm')

from app.data_mdm import routes
