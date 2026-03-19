from flask import render_template
from flask_login import login_required

from app.sales_demo import sales_bp


@sales_bp.route("/")
@login_required
def demo():
    return render_template("demo/sales_demo.html")
