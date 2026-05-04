from flask import render_template
from flask_login import login_required

from app.warehouse_demo import warehouse_bp


@warehouse_bp.route("/")
@login_required
def demo():
    return render_template("demo/warehouse_demo.html")
