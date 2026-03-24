# Mebelgrad KIS

Flask-проект CRM/ERP для мебельного бизнеса: MDM + Finance + Sales/Warehouse demo.

## Быстрый запуск

1. Создать и активировать виртуальное окружение:
   - `python -m venv .venv`
   - `.
\.venv\Scripts\activate`
2. Установить зависимости:
   - `pip install -r requirements.txt`
3. (Опционально) создать `.env` с переменными:
   - `SECRET_KEY`, `JWT_SECRET_KEY`, `DATABASE_URL`, `FLASK_ENV=development`
4. Запустить сервер:
   - `python run.py`
5. Открыть в браузере:
   - http://127.0.0.1:5000

## Демо-пользователи

- `admin` / `admin123` (admin + finance + полный MDM)
- `finance` / `finance123` (finance + mdm-viewer)

## Структура

- `run.py` — точка входа
- `app/__init__.py` — создание приложения, инициализация расширений, создание/синхронизация схемы, сиды
- `app/models.py` — модели SQLAlchemy
- `app/*/routes.py` — Blueprints: auth, data_mdm, finance, sales_demo, warehouse_demo
- `templates/` — HTML-шаблоны

## Проблемы и исправления

Если при старте появляется ошибка:

```
sqlalchemy.exc.OperationalError: no such column: users.is_data_admin
```

1. Удалите файл базы данных: `instance\mebelgrad_kis.db`
2. Перезапустите: `python run.py`

Новый код автоматически добавляет недостающие колонки `is_data_admin`, `is_data_editor`, `is_data_viewer`.

## Тесты

- `tests/test_finance.py` (pytest)

## Настройка на продакшн

- Выставить `FLASK_ENV=production`
- Установить `DATABASE_URL` (PostgreSQL / другой RDBMS)
- Использовать миграции alembic для схемы
