#!/usr/bin/env python3
"""
Quick tests for OrderManager single and multi-leg flows in PAPER_TRADING mode.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from config import config
from src.core.order_manager import OrderManager


def test_single_option_order():
    om = OrderManager()
    resp = om.place_option_order(
        strategy=config.STRATEGY_NAME,
        underlying=config.PRIMARY_UNDERLYING,
        expiry_date='30DEC25',
        offset='ATM',
        option_type='CE',
        action='BUY',
        quantity=config.MINIMUM_LOT_SIZE,
        pricetype=config.DEFAULT_OPTION_PRICE_TYPE,
        product=config.DEFAULT_OPTION_PRODUCT,
        splitsize=config.DEFAULT_SPLIT_SIZE,
    )
    print('Single optionsorder response:', resp)


def test_multi_leg_order():
    om = OrderManager()
    legs = [
        {"offset": "OTM6", "option_type": "CE", "action": "BUY", "quantity": config.MINIMUM_LOT_SIZE},
        {"offset": "OTM6", "option_type": "PE", "action": "BUY", "quantity": config.MINIMUM_LOT_SIZE},
        {"offset": "OTM4", "option_type": "CE", "action": "SELL", "quantity": config.MINIMUM_LOT_SIZE},
        {"offset": "OTM4", "option_type": "PE", "action": "SELL", "quantity": config.MINIMUM_LOT_SIZE},
    ]
    resp = om.place_options_multi_order(
        strategy=config.STRATEGY_NAME,
        underlying=config.PRIMARY_UNDERLYING,
        legs=legs,
        expiry_date='30DEC25',
    )
    print('Multi-leg optionsmultiorder response:', resp)


if __name__ == '__main__':
    print('PAPER_TRADING:', config.PAPER_TRADING)
    test_single_option_order()
    test_multi_leg_order()
