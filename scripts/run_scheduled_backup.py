#!/usr/bin/env python3
"""
Scheduled backup runner for Mebelgrad KIS ERP system.
This script should be run periodically (e.g., hourly) by a scheduler like cron or Windows Task Scheduler.
"""

import os
import sys
import subprocess
import logging
from datetime import datetime

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_backup_check():
    """Check if backup is needed and run it if so."""
    try:
        # Get the path to the backup script
        script_dir = os.path.dirname(__file__)
        backup_script = os.path.join(script_dir, 'backup_database.py')
        
        # Check if backup is needed
        logger.info("Checking if backup is needed...")
        result = subprocess.run([
            sys.executable, backup_script, '--check'
        ], capture_output=True, text=True, cwd=script_dir)
        
        if result.returncode == 0:
            logger.info("Backup is needed, creating backup...")
            
            # Create backup
            result = subprocess.run([
                sys.executable, backup_script, '--create'
            ], capture_output=True, text=True, cwd=script_dir)
            
            if result.returncode == 0:
                logger.info("Backup completed successfully")
                logger.debug(f"Backup output: {result.stdout}")
            else:
                logger.error(f"Backup failed: {result.stderr}")
                
        else:
            logger.info("Backup not needed at this time")
            
    except Exception as e:
        logger.error(f"Scheduled backup check failed: {str(e)}")


def main():
    """Main function."""
    logger.info("Starting scheduled backup check")
    run_backup_check()
    logger.info("Scheduled backup check completed")


if __name__ == '__main__':
    main()