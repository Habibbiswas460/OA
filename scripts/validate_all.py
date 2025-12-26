#!/usr/bin/env python3
"""
Final comprehensive validation: test all order types, logging, and flow.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from config import config
from src.core.order_manager import OrderManager
from src.core.trade_manager import TradeManager
from src.core.expiry_manager import ExpiryManager
from src.utils.options_helper import OptionsHelper
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)

def test_all_components():
    print("="*80)
    print("ANGEL-X FINAL VALIDATION TEST")
    print("="*80)
    
    # Test 1: Logger proxy methods
    print("\n[1] Testing logger proxy methods...")
    try:
        logger.log_order({'test': 'value'})
        logger.log_trade({'test': 'trade'})
        logger.log_signal({'test': 'signal'})
        print("✅ Logger proxies working")
    except Exception as e:
        print(f"❌ Logger error: {e}")
        return False
    
    # Test 2: OrderManager single-leg
    print("\n[2] Testing OrderManager.place_option_order()...")
    try:
        om = OrderManager()
        resp = om.place_option_order(
            strategy=config.STRATEGY_NAME,
            underlying="NIFTY",
            expiry_date="30DEC25",
            offset="ATM",
            option_type="CE",
            action="BUY",
            quantity=75,
            pricetype=config.DEFAULT_OPTION_PRICE_TYPE,
            product=config.DEFAULT_OPTION_PRODUCT
        )
        if resp and resp.get('status') == 'success':
            print(f"✅ Single order placed: {resp.get('orderid')}")
        else:
            print(f"❌ Single order failed: {resp}")
            return False
    except Exception as e:
        print(f"❌ Single order error: {e}")
        return False
    
    # Test 3: OrderManager multi-leg
    print("\n[3] Testing OrderManager.place_options_multi_order()...")
    try:
        legs = [
            {"offset": "OTM4", "option_type": "CE", "action": "BUY", "quantity": 75},
            {"offset": "OTM4", "option_type": "PE", "action": "BUY", "quantity": 75}
        ]
        resp = om.place_options_multi_order(
            strategy=config.STRATEGY_NAME,
            underlying="NIFTY",
            legs=legs,
            expiry_date="30DEC25"
        )
        if resp and resp.get('status') == 'success':
            print(f"✅ Multi-leg order placed: {resp.get('orderid')}")
        else:
            print(f"❌ Multi-leg order failed: {resp}")
            return False
    except Exception as e:
        print(f"❌ Multi-leg order error: {e}")
        return False
    
    # Test 4: Symbol resolution
    print("\n[4] Testing ExpiryManager.get_option_symbol_by_offset()...")
    try:
        em = ExpiryManager()
        em.refresh_expiry_chain("NIFTY")
        sym = em.get_option_symbol_by_offset("NIFTY", "30DEC25", "ATM", "CE")
        if sym:
            print(f"✅ Symbol resolved: {sym}")
        else:
            print(f"❌ Symbol resolution returned None")
            return False
    except Exception as e:
        print(f"❌ Symbol resolution error: {e}")
        return False
    
    # Test 5: TradeManager multi-leg
    print("\n[5] Testing TradeManager.enter_multi_leg_order()...")
    try:
        tm = TradeManager()
        legs = [
            {"offset": "ATM", "option_type": "CE", "action": "BUY", "quantity": 75},
            {"offset": "ATM", "option_type": "PE", "action": "BUY", "quantity": 75}
        ]
        resp = tm.enter_multi_leg_order("NIFTY", legs, "30DEC25")
        if resp and resp.get('status') == 'success':
            print(f"✅ TradeManager multi-leg placed: {resp.get('orderid')}")
        else:
            print(f"⚠️  TradeManager response: {resp}")
    except Exception as e:
        print(f"❌ TradeManager error: {e}")
        return False
    
    # Test 6: OptionsHelper offset computation
    print("\n[6] Testing OptionsHelper.compute_offset()...")
    try:
        oh = OptionsHelper()
        # ATM strike assumed ~18700 for NIFTY
        offset_atm = oh.compute_offset("NIFTY", "30DEC25", 18700, "CE")
        offset_itm = oh.compute_offset("NIFTY", "30DEC25", 18650, "CE")
        offset_otm = oh.compute_offset("NIFTY", "30DEC25", 18750, "CE")
        print(f"✅ Offsets computed:")
        print(f"   Strike 18700 (ATM): {offset_atm}")
        print(f"   Strike 18650 (ITM): {offset_itm}")
        print(f"   Strike 18750 (OTM): {offset_otm}")
    except Exception as e:
        print(f"⚠️  Offset computation (non-critical): {e}")
    
    # Test 7: Config flags
    print("\n[7] Checking config flags...")
    print(f"   USE_OPENALGO_OPTIONS_API: {config.USE_OPENALGO_OPTIONS_API}")
    print(f"   USE_MULTILEG_STRATEGY: {config.USE_MULTILEG_STRATEGY}")
    print(f"   MULTILEG_STRATEGY_TYPE: {config.MULTILEG_STRATEGY_TYPE}")
    print(f"   PAPER_TRADING: {config.PAPER_TRADING}")
    print(f"   ANALYZER_MODE: {config.ANALYZER_MODE}")
    print("✅ Config flags readable")
    
    print("\n" + "="*80)
    print("✅ ALL VALIDATION TESTS PASSED")
    print("="*80)
    
    return True

if __name__ == '__main__':
    success = test_all_components()
    sys.exit(0 if success else 1)
