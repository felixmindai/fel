"""
Bootstrap Script - Initial Historical Data
===========================================

Fetches 1 year of historical daily bars for all active tickers.
Run this ONCE after adding tickers for the first time.

Usage:
    python scripts/bootstrap_data.py
    python scripts/bootstrap_data.py --force  # Re-fetch all data
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from data_fetcher import DataFetcher
import logging
import argparse
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def bootstrap_data(force=False):
    """
    Bootstrap historical data for all tickers.
    
    Args:
        force: If True, re-fetch all data even if it exists
    """
    logger.info("="*60)
    logger.info("BOOTSTRAP: Historical Data Fetch")
    logger.info("="*60)
    
    db = Database()
    fetcher = DataFetcher()
    
    # Connect to IB
    if not fetcher.connect():
        logger.error("❌ Failed to connect to Interactive Brokers")
        logger.error("   Make sure TWS or IB Gateway is running on port 7497")
        return False
    
    # Get active tickers
    tickers = db.get_active_tickers()
    
    if not tickers:
        logger.error("❌ No active tickers found")
        logger.error("   Please add tickers first using the UI or database")
        return False
    
    logger.info(f"Found {len(tickers)} active tickers")
    logger.info("")
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for i, symbol in enumerate(tickers, 1):
        try:
            logger.info(f"[{i}/{len(tickers)}] Processing {symbol}...")
            
            # Check if data already exists (unless force=True)
            if not force:
                latest_date = db.get_latest_bar_date(symbol)
                if latest_date:
                    logger.info(f"  ✓ Data exists (latest: {latest_date}) - skipping")
                    skip_count += 1
                    continue
            
            # Fetch 1 year of data
            logger.info(f"  Fetching 1 year of historical data...")
            bars = fetcher.fetch_historical_bars(symbol, duration='1 Y', bar_size='1 day')
            
            if not bars:
                logger.warning(f"  ⚠️ No data returned for {symbol}")
                error_count += 1
                continue
            
            # Save to database
            saved = db.save_daily_bars(symbol, bars)
            
            if saved > 0:
                logger.info(f"  ✅ Saved {saved} bars for {symbol}")
                success_count += 1
            else:
                logger.warning(f"  ⚠️ Failed to save data for {symbol}")
                error_count += 1
            
            # Rate limiting - don't hammer IB API
            import time
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"  ❌ Error processing {symbol}: {e}")
            error_count += 1
    
    # Disconnect
    fetcher.disconnect()
    
    # Summary
    logger.info("")
    logger.info("="*60)
    logger.info("BOOTSTRAP COMPLETE")
    logger.info("="*60)
    logger.info(f"✅ Success: {success_count} tickers")
    logger.info(f"⏭️  Skipped: {skip_count} tickers (data exists)")
    logger.info(f"❌ Errors:  {error_count} tickers")
    logger.info("")
    
    if success_count > 0:
        logger.info("🎉 You can now run the scanner!")
    
    return True


def add_default_tickers():
    """Add a default set of quality tickers for testing."""
    logger.info("Adding default ticker list...")
    
    db = Database()
    
    # Quality large caps and mid caps (100 total)
    default_tickers = [
        # Tech Giants
        ('AAPL', 'Apple Inc', 'Technology'),
        ('MSFT', 'Microsoft Corporation', 'Technology'),
        ('GOOGL', 'Alphabet Inc', 'Technology'),
        ('AMZN', 'Amazon.com Inc', 'Technology'),
        ('NVDA', 'NVIDIA Corporation', 'Technology'),
        ('META', 'Meta Platforms Inc', 'Technology'),
        ('TSLA', 'Tesla Inc', 'Automotive'),
        ('AVGO', 'Broadcom Inc', 'Technology'),
        ('AMD', 'Advanced Micro Devices', 'Technology'),
        ('CRM', 'Salesforce Inc', 'Technology'),
        ('ORCL', 'Oracle Corporation', 'Technology'),
        ('ADBE', 'Adobe Inc', 'Technology'),
        ('CSCO', 'Cisco Systems Inc', 'Technology'),
        ('INTC', 'Intel Corporation', 'Technology'),
        ('QCOM', 'QUALCOMM Inc', 'Technology'),
        
        # Healthcare
        ('UNH', 'UnitedHealth Group', 'Healthcare'),
        ('JNJ', 'Johnson & Johnson', 'Healthcare'),
        ('LLY', 'Eli Lilly and Company', 'Healthcare'),
        ('ABBV', 'AbbVie Inc', 'Healthcare'),
        ('MRK', 'Merck & Co Inc', 'Healthcare'),
        ('TMO', 'Thermo Fisher Scientific', 'Healthcare'),
        ('ABT', 'Abbott Laboratories', 'Healthcare'),
        ('DHR', 'Danaher Corporation', 'Healthcare'),
        ('PFE', 'Pfizer Inc', 'Healthcare'),
        ('BMY', 'Bristol-Myers Squibb', 'Healthcare'),
        
        # Financials
        ('JPM', 'JPMorgan Chase & Co', 'Financial'),
        ('V', 'Visa Inc', 'Financial'),
        ('MA', 'Mastercard Inc', 'Financial'),
        ('BAC', 'Bank of America Corp', 'Financial'),
        ('WFC', 'Wells Fargo & Company', 'Financial'),
        ('GS', 'Goldman Sachs Group', 'Financial'),
        ('MS', 'Morgan Stanley', 'Financial'),
        ('AXP', 'American Express Company', 'Financial'),
        ('BLK', 'BlackRock Inc', 'Financial'),
        ('SCHW', 'Charles Schwab Corp', 'Financial'),
        
        # Consumer
        ('WMT', 'Walmart Inc', 'Retail'),
        ('HD', 'Home Depot Inc', 'Retail'),
        ('COST', 'Costco Wholesale Corp', 'Retail'),
        ('PG', 'Procter & Gamble Co', 'Consumer'),
        ('KO', 'Coca-Cola Company', 'Consumer'),
        ('PEP', 'PepsiCo Inc', 'Consumer'),
        ('MCD', 'McDonald\'s Corporation', 'Consumer'),
        ('NKE', 'Nike Inc', 'Consumer'),
        ('SBUX', 'Starbucks Corporation', 'Consumer'),
        ('TGT', 'Target Corporation', 'Retail'),
        
        # Industrial
        ('CAT', 'Caterpillar Inc', 'Industrial'),
        ('BA', 'Boeing Company', 'Industrial'),
        ('HON', 'Honeywell International', 'Industrial'),
        ('UNP', 'Union Pacific Corporation', 'Industrial'),
        ('RTX', 'Raytheon Technologies', 'Industrial'),
        ('LMT', 'Lockheed Martin Corp', 'Industrial'),
        ('GE', 'General Electric Company', 'Industrial'),
        ('MMM', '3M Company', 'Industrial'),
        ('DE', 'Deere & Company', 'Industrial'),
        ('UPS', 'United Parcel Service', 'Industrial'),
        
        # Energy
        ('XOM', 'Exxon Mobil Corporation', 'Energy'),
        ('CVX', 'Chevron Corporation', 'Energy'),
        ('COP', 'ConocoPhillips', 'Energy'),
        ('SLB', 'Schlumberger NV', 'Energy'),
        ('EOG', 'EOG Resources Inc', 'Energy'),
        
        # Communication
        ('NFLX', 'Netflix Inc', 'Media'),
        ('DIS', 'Walt Disney Company', 'Media'),
        ('CMCSA', 'Comcast Corporation', 'Media'),
        ('VZ', 'Verizon Communications', 'Telecom'),
        ('T', 'AT&T Inc', 'Telecom'),
        
        # Materials
        ('LIN', 'Linde plc', 'Materials'),
        ('APD', 'Air Products & Chemicals', 'Materials'),
        ('SHW', 'Sherwin-Williams Company', 'Materials'),
        ('FCX', 'Freeport-McMoRan Inc', 'Materials'),
        ('NEM', 'Newmont Corporation', 'Materials'),
        
        # Utilities
        ('NEE', 'NextEra Energy Inc', 'Utilities'),
        ('DUK', 'Duke Energy Corporation', 'Utilities'),
        ('SO', 'Southern Company', 'Utilities'),
        ('D', 'Dominion Energy Inc', 'Utilities'),
        
        # Real Estate
        ('PLD', 'Prologis Inc', 'Real Estate'),
        ('AMT', 'American Tower Corp', 'Real Estate'),
        ('SPG', 'Simon Property Group', 'Real Estate'),
        
        # ETFs for reference
        ('SPY', 'SPDR S&P 500 ETF', 'ETF'),
        ('QQQ', 'Invesco QQQ Trust', 'ETF'),
        ('IWM', 'iShares Russell 2000', 'ETF'),
        
        # Growth Stocks
        ('SNOW', 'Snowflake Inc', 'Technology'),
        ('SHOP', 'Shopify Inc', 'Technology'),
        ('SQ', 'Block Inc', 'Technology'),
        ('COIN', 'Coinbase Global Inc', 'Technology'),
        ('RBLX', 'Roblox Corporation', 'Technology'),
        ('U', 'Unity Software Inc', 'Technology'),
        ('NET', 'Cloudflare Inc', 'Technology'),
        ('DDOG', 'Datadog Inc', 'Technology'),
        ('CRWD', 'CrowdStrike Holdings', 'Technology'),
        ('ZS', 'Zscaler Inc', 'Technology'),
    ]
    
    added = 0
    for symbol, name, sector in default_tickers:
        if db.add_ticker(symbol, name, sector):
            added += 1
    
    logger.info(f"✅ Added {added} default tickers")
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Bootstrap historical data')
    parser.add_argument('--force', action='store_true', help='Re-fetch all data even if exists')
    parser.add_argument('--add-tickers', action='store_true', help='Add default ticker list')
    args = parser.parse_args()
    
    if args.add_tickers:
        add_default_tickers()
        logger.info("")
        logger.info("Now run the script again without --add-tickers to fetch data")
        return
    
    bootstrap_data(force=args.force)


if __name__ == "__main__":
    main()
