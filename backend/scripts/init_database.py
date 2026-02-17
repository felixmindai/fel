"""
Database Initialization Script
===============================

Creates all required database tables and default configuration.

Usage:
    python scripts/init_database.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Initialize the database."""
    logger.info("="*60)
    logger.info("DATABASE INITIALIZATION")
    logger.info("="*60)
    
    try:
        db = Database()
        db.create_tables()
        
        logger.info("")
        logger.info("✅ Database initialized successfully!")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Add tickers: python scripts/bootstrap_data.py --add-tickers")
        logger.info("2. Fetch data: python scripts/bootstrap_data.py")
        logger.info("3. Start API: python main.py")
        logger.info("")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.error("")
        logger.error("Please check:")
        logger.error("- PostgreSQL is running")
        logger.error("- Database credentials in .env are correct")
        logger.error("- Database 'minervini_bot' exists")
        logger.error("")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
