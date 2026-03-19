from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_jwt_extended import create_access_token
from flask_login import current_user, login_required, login_user, logout_user

from app.auth import auth_bp
from app.models import User, db


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash("Неверное имя пользователя или пароль.", "danger")
            return redirect(url_for("auth.login"))

        if not user.is_active:
            flash("Учетная запись деактивирована.", "danger")
            return redirect(url_for("auth.login"))

        login_user(user, remember=remember)
        next_page = request.args.get("next")
        if not next_page or not next_page.startswith("/"):
            next_page = url_for("index")

        flash(f"Добро пожаловать, {user.username}.", "success")
        return redirect(next_page)

    return render_template(
        "auth/login.html",
        first_admin_available=User.query.count() == 0,
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if User.query.count() > 0:
        flash(
            "Саморегистрация доступна только для первого администратора системы.",
            "warning",
        )
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        password_repeat = request.form.get("password_repeat", "")

        if not all([username, email, password, password_repeat]):
            flash("Заполните все поля формы.", "danger")
            return redirect(url_for("auth.register"))

        if password != password_repeat:
            flash("Пароли не совпадают.", "danger")
            return redirect(url_for("auth.register"))

        user = User(
            username=username,
            email=email,
            is_admin=True,
            is_finance=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Первый администратор создан. Теперь можно войти в систему.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username", "").strip()
    password = payload.get("password", "")

    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return jsonify({"message": "Invalid credentials"}), 401

    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "username": user.username,
            "is_admin": user.is_admin,
            "is_finance": user.is_finance,
        },
    )
    return jsonify({"access_token": access_token})
