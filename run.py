#!/usr/bin/env python
import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app

if __name__ == '__main__':
    config_name = os.environ.get('FLASK_ENV', 'development')
    app = create_app(config_name)
    
    # Run development server
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=(config_name == 'development'),
        use_reloader=False
    )
