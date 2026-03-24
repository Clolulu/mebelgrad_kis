from app.models import db
from app import create_app
from sqlalchemy import text

app = create_app('development')
with app.app_context():
    res = db.session.execute(text("PRAGMA table_info('users');")).fetchall()
    print('users schema columns:', [r[1] for r in res])
