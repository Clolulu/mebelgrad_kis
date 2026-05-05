#!/usr/bin/env python3
"""
Database backup utility for Mebelgrad KIS ERP system.
Creates automated backups of the SQLite database.
"""

import os
import sys
import shutil
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app
from app.models import BackupSettings, db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def create_backup():
    """Create a database backup based on current settings."""
    try:
        app = create_app()
        
        with app.app_context():
            # Get backup settings
            settings = BackupSettings.query.first()
            if not settings or not settings.is_enabled:
                logger.info("Backup is disabled in settings")
                return False
            
            # Ensure backup directory exists
            backup_dir = Path(settings.backup_path)
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Get database path from app config
            db_path = app.config['SQLALCHEMY_DATABASE_URI']
            if db_path.startswith('sqlite:///'):
                db_path = db_path[10:]  # Remove 'sqlite:///'
            elif db_path.startswith('sqlite:'):
                db_path = db_path[7:]   # Remove 'sqlite:'
            
            if not os.path.exists(db_path):
                logger.error(f"Database file not found: {db_path}")
                return False
            
            # Create backup filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"mebelgrad_kis_backup_{timestamp}.db"
            backup_path = backup_dir / backup_filename
            
            # Create backup by copying the database file
            logger.info(f"Creating backup: {backup_path}")
            shutil.copy2(db_path, backup_path)
            
            # Update last backup timestamp
            settings.last_backup = datetime.utcnow()
            db.session.commit()
            
            # Clean up old backups
            cleanup_old_backups(backup_dir, settings.retention_days)
            
            logger.info(f"Backup completed successfully: {backup_path}")
            return True
            
    except Exception as e:
        logger.error(f"Backup failed: {str(e)}")
        return False


def cleanup_old_backups(backup_dir, retention_days):
    """Remove backups older than retention period."""
    try:
        cutoff_date = datetime.now().timestamp() - (retention_days * 24 * 60 * 60)
        
        for backup_file in backup_dir.glob("mebelgrad_kis_backup_*.db"):
            if backup_file.stat().st_mtime < cutoff_date:
                logger.info(f"Removing old backup: {backup_file}")
                backup_file.unlink()
                
    except Exception as e:
        logger.error(f"Failed to cleanup old backups: {str(e)}")


def schedule_next_backup():
    """Update the next backup timestamp based on current settings."""
    try:
        app = create_app()
        
        with app.app_context():
            settings = BackupSettings.query.first()
            if not settings or not settings.is_enabled:
                return
            
            from datetime import timedelta
            
            now = datetime.utcnow()
            
            if settings.frequency == "daily":
                # Next backup at the specified time today or tomorrow
                today_backup = now.replace(hour=int(settings.backup_time.split(":")[0]), 
                                         minute=int(settings.backup_time.split(":")[1]), 
                                         second=0, microsecond=0)
                if today_backup <= now:
                    today_backup += timedelta(days=1)
                settings.next_backup = today_backup
                
            elif settings.frequency == "weekly":
                # Next Monday at the specified time
                days_until_monday = (7 - now.weekday()) % 7
                if days_until_monday == 0 and now.time() >= datetime.strptime(settings.backup_time, "%H:%M").time():
                    days_until_monday = 7
                next_monday = (now + timedelta(days=days_until_monday)).replace(hour=int(settings.backup_time.split(":")[0]), 
                                                                               minute=int(settings.backup_time.split(":")[1]), 
                                                                               second=0, microsecond=0)
                settings.next_backup = next_monday
                
            elif settings.frequency == "monthly":
                # First day of next month at the specified time
                if now.month == 12:
                    next_month = now.replace(year=now.year + 1, month=1, day=1)
                else:
                    next_month = now.replace(month=now.month + 1, day=1)
                next_month = next_month.replace(hour=int(settings.backup_time.split(":")[0]), 
                                              minute=int(settings.backup_time.split(":")[1]), 
                                              second=0, microsecond=0)
                settings.next_backup = next_month
            
            db.session.commit()
            logger.info(f"Next backup scheduled for: {settings.next_backup}")
            
    except Exception as e:
        logger.error(f"Failed to schedule next backup: {str(e)}")


def check_backup_needed():
    """Check if a backup is needed based on schedule."""
    try:
        app = create_app()
        
        with app.app_context():
            settings = BackupSettings.query.first()
            if not settings or not settings.is_enabled:
                return False
            
            now = datetime.utcnow()
            return settings.next_backup and now >= settings.next_backup
            
    except Exception as e:
        logger.error(f"Failed to check backup schedule: {str(e)}")
        return False


def main():
    """Main function for command line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Database backup utility for Mebelgrad KIS')
    parser.add_argument('--create', action='store_true', help='Create a backup now')
    parser.add_argument('--schedule', action='store_true', help='Update next backup schedule')
    parser.add_argument('--check', action='store_true', help='Check if backup is needed')
    
    args = parser.parse_args()
    
    if args.create:
        success = create_backup()
        if success:
            schedule_next_backup()
        sys.exit(0 if success else 1)
        
    elif args.schedule:
        schedule_next_backup()
        sys.exit(0)
        
    elif args.check:
        needed = check_backup_needed()
        print("Backup needed" if needed else "Backup not needed")
        sys.exit(0 if needed else 1)
        
    else:
        parser.print_help()


if __name__ == '__main__':
    main()