#!/usr/bin/env python3
"""
Quick data feed test - Check if market data is flowing from OpenAlgo
"""
import sys
import time
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, '/home/lora/projects/OA')

from src.utils.data_feed import DataFeed

def test_data_feed():
    """Test if market data is flowing"""
    logger.info("=" * 60)
    logger.info("🔍 DATA FEED TEST - Checking market data flow")
    logger.info("=" * 60)
    
    # Initialize data feed
    data_feed = DataFeed()
    
    try:
        # Connect
        logger.info("🔌 Connecting to OpenAlgo WebSocket...")
        data_feed.connect()
        time.sleep(1)
        
        # Subscribe to NIFTY
        logger.info("📊 Subscribing to NIFTY LTP...")
        instruments = [{'exchange': 'NSE', 'symbol': 'NIFTY'}]
        data_feed.subscribe_ltp(instruments)
        time.sleep(2)
        
        # Monitor for ticks
        logger.info("⏳ Listening for market data (30 seconds)...")
        logger.info("-" * 60)
        
        tick_count = 0
        start_time = time.time()
        prices = {}
        
        while time.time() - start_time < 30:
            # Check if we have any new ticks
            current_price = data_feed.get_ltp('NIFTY')
            
            if current_price:
                if 'NIFTY' not in prices or prices['NIFTY'] != current_price:
                    prices['NIFTY'] = current_price
                    tick_count += 1
                    elapsed = int(time.time() - start_time)
                    logger.info(f"✅ TICK #{tick_count} @ {elapsed}s | NIFTY: ₹{current_price:.2f}")
            
            time.sleep(0.5)
        
        logger.info("-" * 60)
        
        if tick_count > 0:
            logger.info(f"✅ SUCCESS! Received {tick_count} ticks in 30 seconds")
            logger.info(f"📈 Latest NIFTY: ₹{prices.get('NIFTY', 'N/A')}")
        else:
            logger.warning("⚠️  NO DATA! Market may be closed or OpenAlgo not broadcasting")
            logger.warning("   Check: 1) Market hours (9:15-15:30 IST)")
            logger.warning("          2) OpenAlgo server running")
            logger.warning("          3) Network connectivity")
        
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.info("Cleaning up...")
        data_feed.disconnect()

if __name__ == "__main__":
    test_data_feed()
