#!/usr/bin/env python3
"""
OpenAlgo health check: analyzer mode, quotes, expiry discovery, ATM symbol, greeks, and
analyze-mode options order (paper/analyze only). Uses config values for host/key.
"""
import json
import sys

from config import config

try:
    from openalgo import api
except ImportError:
    print("OpenAlgo library not installed. Run: pip install openalgo")
    sys.exit(1)


def log_section(name: str, data):
    print(f"\n{name}:")
    try:
        print(json.dumps(data, indent=2, ensure_ascii=True))
    except Exception:
        print(data)


def main():
    # Require API key and host
    if not getattr(config, "OPENALGO_API_KEY", None):
        print("OPENALGO_API_KEY not set in config/config.py")
        sys.exit(1)
    if not getattr(config, "OPENALGO_HOST", None):
        print("OPENALGO_HOST not set in config/config.py")
        sys.exit(1)

    client = api(
        api_key=config.OPENALGO_API_KEY,
        host=config.OPENALGO_HOST,
        ws_url=getattr(config, "OPENALGO_WS_URL", None),
    )

    # Analyzer status and toggle to analyze mode
    status = client.analyzerstatus()
    log_section("analyzerstatus", status)
    analyze_mode = bool(status and status.get("data", {}).get("analyze_mode"))
    if not analyze_mode:
        toggle = client.analyzertoggle(mode=True)
        log_section("analyzertoggle", toggle)

    # Quotes for the underlying
    quotes = client.quotes(
        symbol=config.PRIMARY_UNDERLYING,
        exchange=config.UNDERLYING_EXCHANGE,
    )
    log_section("quotes", quotes)

    # Nearest expiry discovery
    expiry_resp = client.expiry(
        symbol=config.PRIMARY_UNDERLYING,
        exchange="NFO",
        instrumenttype="options",
    )
    log_section("expiry", expiry_resp)
    expiry_dates = expiry_resp.get("data") if isinstance(expiry_resp, dict) else None
    if not expiry_dates:
        print("No expiry data returned; stopping before options checks.")
        return
    expiry_date = expiry_dates[0]

    # Resolve ATM option symbol
    option_symbol_resp = client.optionsymbol(
        underlying=config.PRIMARY_UNDERLYING,
        exchange=config.DEFAULT_UNDERLYING_EXCHANGE,
        expiry_date=expiry_date,
        offset="ATM",
        option_type="CE",
    )
    log_section("optionsymbol", option_symbol_resp)
    symbol = None
    if option_symbol_resp and option_symbol_resp.get("status") == "success":
        symbol = option_symbol_resp.get("symbol")
    if not symbol:
        print("Could not resolve option symbol; stopping before greeks/orders.")
        return

    # Greeks for the resolved symbol
    greeks_resp = client.optiongreeks(
        symbol=symbol,
        exchange="NFO",
        interest_rate=0.0,
        underlying_symbol=config.PRIMARY_UNDERLYING,
        underlying_exchange=config.UNDERLYING_EXCHANGE,
    )
    log_section("optiongreeks", greeks_resp)

    # Analyzer-mode options order (paper/analyze)
    order_resp = client.optionsorder(
        strategy="HealthCheck",
        underlying=config.PRIMARY_UNDERLYING,
        exchange=config.DEFAULT_UNDERLYING_EXCHANGE,
        expiry_date=expiry_date,
        offset="ATM",
        option_type="CE",
        action="BUY",
        quantity=config.MINIMUM_LOT_SIZE,
        pricetype=config.DEFAULT_OPTION_PRICE_TYPE,
        product=config.DEFAULT_OPTION_PRODUCT,
        splitsize=0,
    )
    log_section("optionsorder", order_resp)


if __name__ == "__main__":
    main()
