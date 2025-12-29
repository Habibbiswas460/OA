#!/usr/bin/env python3
"""
OpenAlgo Integration Test
Comprehensive test of all OpenAlgo APIs with real market data
"""

import sys
import logging

sys.path.insert(0, '/home/lora/projects/OA')

from config import config
from src.utils.logger import StrategyLogger
from src.engines.openalgo_executor import get_executor, ExecutionMode

logging.basicConfig(level=logging.INFO)
logger = StrategyLogger.get_logger(__name__)


def test_workflow():
    """Test complete workflow"""
    
    logger.info("=" * 80)
    logger.info("OPENALGO INTEGRATION TEST")
    logger.info("=" * 80)
    
    # Initialize executor
    executor = get_executor(mode=ExecutionMode.ANALYZE)
    
    # Step 1: Fetch option chain
    logger.info("\n📊 STEP 1: Fetch Option Chain")
    logger.info("-" * 80)
    
    chain = executor.fetch_option_chain(
        underlying="NIFTY",
        expiry_date="30DEC25",
        strike_count=5
    )
    
    if not chain:
        logger.error("❌ Failed to fetch option chain")
        return False
    
    atm_strike = chain.get('atm_strike')
    logger.info(f"✅ ATM Strike: {atm_strike}")
    
    # Step 2: Resolve symbols
    logger.info("\n🔗 STEP 2: Resolve Option Symbols")
    logger.info("-" * 80)
    
    ce_symbol_resp = executor.fetch_option_symbol(
        underlying="NIFTY",
        expiry_date="30DEC25",
        offset="ATM",
        option_type="CE"
    )
    
    if not ce_symbol_resp:
        logger.error("❌ Failed to resolve CE symbol")
        return False
    
    ce_symbol = ce_symbol_resp.get('data', {}).get('symbol') or ce_symbol_resp.get('symbol')
    logger.info(f"✅ CE Symbol: {ce_symbol}")
    
    # Step 3: Fetch Greeks
    logger.info("\n📈 STEP 3: Fetch Greeks Data")
    logger.info("-" * 80)
    
    greeks = executor.fetch_greeks(ce_symbol)
    
    if not greeks:
        logger.error("❌ Failed to fetch Greeks")
        return False
    
    logger.info(f"✅ Greeks Data:")
    logger.info(f"   Delta: {greeks.delta:.4f}")
    logger.info(f"   Gamma: {greeks.gamma:.6f}")
    logger.info(f"   Theta: {greeks.theta:.6f}")
    logger.info(f"   Vega: {greeks.vega:.4f}")
    logger.info(f"   IV: {greeks.iv:.2f}%")
    logger.info(f"   LTP: ₹{greeks.ltp:.2f}")
    logger.info(f"   OI: {greeks.oi:,}")
    
    # Step 4: Fetch quotes
    logger.info("\n💱 STEP 4: Fetch Real-time Quotes")
    logger.info("-" * 80)
    
    quote = executor.fetch_quotes("NIFTY", "NSE")
    
    if quote:
        logger.info(f"✅ NIFTY Quote:")
        logger.info(f"   LTP: ₹{quote.get('ltp'):.2f}")
        logger.info(f"   Bid: ₹{quote.get('bid'):.2f}")
        logger.info(f"   Ask: ₹{quote.get('ask'):.2f}")
        logger.info(f"   Volume: {quote.get('volume'):,}")
    
    # Step 5: Execute order (ANALYZE mode - simulated)
    logger.info("\n🎯 STEP 5: Execute Order (ANALYZE MODE)")
    logger.info("-" * 80)
    
    result = executor.execute_option_order(
        underlying="NIFTY",
        expiry_date="30DEC25",
        offset="ATM",
        option_type="CE",
        action="BUY",
        quantity=75,
        pricetype="MARKET",
        product="NRML"
    )
    
    if result.success:
        logger.info(f"✅ Order Executed:")
        logger.info(f"   Order ID: {result.order_id}")
        logger.info(f"   Symbol: {result.symbol}")
    else:
        logger.error(f"❌ Order Failed: {result.message}")
    
    # Step 6: Test multi-leg order
    logger.info("\n🎪 STEP 6: Execute Multi-leg Order")
    logger.info("-" * 80)
    
    legs = [
        {"offset": "ATM", "option_type": "CE", "action": "BUY", "quantity": 75},
        {"offset": "ATM", "option_type": "PE", "action": "BUY", "quantity": 75}
    ]
    
    multileg_result = executor.execute_multileg_order(
        underlying="NIFTY",
        expiry_date="30DEC25",
        legs=legs,
        strategy_name="STRADDLE_TEST"
    )
    
    if multileg_result.success:
        logger.info(f"✅ Multi-leg Order Executed:")
        logger.info(f"   {multileg_result.message}")
    else:
        logger.error(f"❌ Multi-leg Failed: {multileg_result.message}")
    
    # Step 7: Print summary
    logger.info("\n📊 STEP 7: Execution Summary")
    logger.info("-" * 80)
    
    executor.print_summary()
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ INTEGRATION TEST COMPLETED")
    logger.info("=" * 80)
    
    return True


if __name__ == "__main__":
    try:
        success = test_workflow()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
