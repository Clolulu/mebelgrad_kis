import os
from app import create_app

db_path = os.path.join('instance', 'mebelgrad_kis.db')
if os.path.exists(db_path):
    os.remove(db_path)

app = create_app('development')
print('Application created successfully:', app)
