# Mebelgrad KIS

Flask CRM/ERP application for a furniture business (КИС "МебельГрад"). Supports master data management, sales, warehouse, purchasing, and financial planning.

## Architecture

- **Framework**: Python 3.12 / Flask 2.3.3
- **Database**: SQLite (local development), via SQLAlchemy
- **Auth**: Flask-Login (session-based) + Flask-JWT-Extended (token-based)
- **Templates**: Jinja2 HTML templates in `templates/`
- **Entry point**: `run.py` — creates the Flask app, seeds the database on first run

## Key Files

- `run.py` — Entry point; module-level `app` variable for both direct run and gunicorn
- `config.py` — Configuration classes (Dev uses SQLite explicitly, Prod uses DATABASE_URL)
- `app/__init__.py` — `create_app()` factory: registers blueprints, runs DB migrations, seeds data
- `app/models.py` — SQLAlchemy models (all tables)
- `templates/` — All HTML templates

## Modules / Blueprints

- `app/auth` (`/auth`) — Authentication (login, logout)
- `app/data_mdm` (`/mdm`) — Master Data Management (products, customers, suppliers, employees)
- `app/finance` (`/finance`) — Financial planning (budget, cash calendar, P&L, balance)
- `app/sales_demo` (`/sales`) — Sales order workflow (CRM, orders, delivery, documents)
- `app/warehouse_demo` (`/warehouse`) — Warehouse & procurement module (see below)

## Warehouse Module (`/warehouse`)

Full-featured warehouse and procurement module with 6 sub-sections:

### Sub-sections
| URL | Description |
|-----|-------------|
| `/warehouse/` | Dashboard with KPIs and recent activity |
| `/warehouse/purchase-requests` | Purchase requests (заявки на закупку) — full CRUD, status workflow |
| `/warehouse/stock` | Stock management with manual adjustments |
| `/warehouse/receipts` | Goods receipts (приёмка), post to stock |
| `/warehouse/assembly` | Order assembly (комплектация) — picking & stock deduction |
| `/warehouse/inventory` | Inventory counts (инвентаризация) with optional stock correction |

### Purchase Request Status Workflow
`draft` → `submitted` → `approved` → `ordered` (creates PurchaseOrder)
                     ↘ `rejected` → back to `draft` for editing

### New Models (added to `app/models.py`)
- `PurchaseRequest` / `PurchaseRequestItem` — заявки на закупку с позициями
- `GoodsReceipt` / `GoodsReceiptItem` — приёмка товаров
- `InventoryCount` / `InventoryCountItem` — инвентаризационные ведомости

## Database

- **Development**: SQLite at `instance/mebelgrad_kis.db` (auto-created on first run)
- **Production**: Uses `DATABASE_URL` environment variable
- Schema is auto-migrated on startup via `sync_user_schema()`, `sync_sales_schema()`, and `db.create_all()`
- Database is seeded with demo data on first run automatically

## Demo Users

| Username | Password | Role |
|----------|----------|------|
| admin@mebelgrad.local | admin123 | Full access |
| finance@mebelgrad.local | finance123 | Finance + read MDM |
| seller@mebelgrad.local | seller123 | Sales module |
| warehouse@mebelgrad.local | warehouse123 | Warehouse module |

## Running

```bash
python run.py
```

App runs on `0.0.0.0:5000`.

## Deployment

Configured for autoscale deployment with gunicorn:
```
gunicorn --bind=0.0.0.0:5000 --reuse-port run:app
```

## Notes

- The `DATABASE_URL` secret in Replit points to PostgreSQL (Helium), but development config explicitly uses SQLite to avoid PRAGMA/PostgreSQL incompatibilities in schema sync functions
- Schema sync functions (`_get_existing_columns`) support both SQLite (PRAGMA) and PostgreSQL (information_schema)
- `wkhtmltopdf.exe` is included in the repo for PDF generation on Windows; Linux uses system wkhtmltopdf if available
- All new warehouse tables are created automatically via `db.create_all()` on first startup
