"""
ANGEL-X Main Strategy Orchestrator
Coordinates all 9 layers of ANGEL-X system
Optimized for local network with auto-reconnection and monitoring
"""

import signal
import time
import logging
from datetime import datetime, timedelta
from threading import Lock

# Configuration
from config import config

# Utils
from src.utils.logger import StrategyLogger
from src.utils.data_feed import DataFeed
from src.utils.trade_journal import TradeJournal
from src.utils.network_resilience import get_network_monitor
from src.utils.greeks_data_manager import GreeksDataManager
from src.utils.session_logger import get_session_logger, end_current_session

# Engines
from src.engines.bias_engine import BiasEngine, BiasState
from src.engines.strike_selection_engine import StrikeSelectionEngine
from src.engines.entry_engine import EntryEngine, EntrySignal
from src.engines.trap_detection_engine import TrapDetectionEngine

# Core
from src.core.position_sizing import PositionSizing
from src.core.order_manager import OrderManager, OrderAction, OrderType, ProductType
from src.core.trade_manager import TradeManager
from src.core.expiry_manager import ExpiryManager
from src.utils.options_helper import OptionsHelper

logger = StrategyLogger.get_logger(__name__)


class AngelXStrategy:
    """
    ANGEL-X: Professional Options Scalping Strategy
    
    9-Layer Architecture:
    1. Data Ingestion (WebSocket)
    2. Data Normalization & Health Check
    3. Market State Engine (Bias)
    4. Option Selection Engine
    5. Entry Engine (Trigger)
    6. Position Sizing Engine (Risk)
    7. Execution Engine (Orders)
    8. Trade Management Engine (Greek exits)
    9. Daily Risk & Kill-Switch
    """
    
    def __init__(self):
        """Initialize ANGEL-X strategy"""
        mode_label = "DEMO" if config.DEMO_MODE else ("ANALYZE" if config.PAPER_TRADING else "LIVE")
        logger.info("="*80)
        logger.info("ANGEL-X STRATEGY INITIALIZATION")
        logger.info(f"Mode: {mode_label}")
        logger.info("="*80)
        
        # If demo mode, skip expensive init
        if config.DEMO_MODE:
            logger.info("DEMO_MODE enabled - using simulation")
            self.running = False
            self.state_lock = Lock()
            self.session_logger = get_session_logger()
            self.session_logger.set_mode("PAPER")
            logger.info("Demo mode ready - minimal components initialized")
            return
        
        # Initialize session logger
        self.session_logger = get_session_logger()
        exec_mode = "PAPER" if config.PAPER_TRADING else "LIVE"
        self.session_logger.set_mode(exec_mode)
        self.session_logger.log_event('STRATEGY_INIT', {
            'mode': exec_mode,
            'symbol': getattr(config, 'SYMBOL', config.PRIMARY_UNDERLYING),
            'max_daily_loss': getattr(config, 'MAX_DAILY_LOSS', getattr(config, 'MAX_DAILY_LOSS_AMOUNT', None))
        })
        logger.info(f"Session logger initialized: {self.session_logger.session_id} | Mode: {exec_mode}")
        
        # Initialize network monitor for local network resilience
        self.network_monitor = get_network_monitor()
        self.network_monitor.start_monitoring()
        logger.info("Network monitor started - monitoring connectivity and data flow")
        
        # Initialize all components
        self.data_feed = DataFeed()
        self.bias_engine = BiasEngine()
        self.trap_detection = TrapDetectionEngine()
        self.strike_selection = StrikeSelectionEngine()
        self.entry_engine = EntryEngine(self.bias_engine, self.trap_detection)
        self.position_sizing = PositionSizing()
        self.order_manager = OrderManager()
        self.trade_manager = TradeManager()
        self.trade_journal = TradeJournal()
        self.options_helper = OptionsHelper()
        
        # Greeks data manager for real-time Greeks and OI
        self.greeks_manager = GreeksDataManager()
        logger.info("Greeks data manager initialized")
        
        # Expiry manager - auto-detect from OpenAlgo
        try:
            self.expiry_manager = ExpiryManager()
            if not config.DEMO_MODE:
                self.expiry_manager.refresh_expiry_chain(config.PRIMARY_UNDERLYING)
            logger.info("Expiry manager initialized")
        except Exception as e:
            logger.warning(f"Expiry manager init failed (demo mode): {e}")
            self.expiry_manager = ExpiryManager()
        
        # Strategy state
        self.running = False
        self.state_lock = Lock()
        self.last_tick_time = None
        
        # Daily limits
        self.daily_start_time = datetime.now()
        self.daily_pnl = 0.0
        self.daily_trades = 0
        
        # Signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info("All components initialized successfully")
        logger.info("="*80)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("Received shutdown signal")
        self.stop()
    
    def _place_multileg_order(self, entry_context, position, expiry_rules):
        """Place multi-leg options order (straddle/strangle) based on config."""
        try:
            current_exp = self.expiry_manager.get_current_expiry()
            if not current_exp:
                logger.error("No current expiry; cannot place multileg order")
                return None
            
            expiry_date = current_exp.expiry_date
            qty = int(position.quantity * expiry_rules.get('max_position_size_factor', 1.0))
            
            legs = []
            
            if config.MULTILEG_STRATEGY_TYPE == "STRADDLE":
                # ATM CE + ATM PE (long both)
                legs = [
                    {
                        "offset": config.MULTILEG_BUY_LEG_OFFSET,
                        "option_type": "CE",
                        "action": "BUY",
                        "quantity": qty,
                        "pricetype": config.DEFAULT_OPTION_PRICE_TYPE,
                        "product": config.DEFAULT_OPTION_PRODUCT
                    },
                    {
                        "offset": config.MULTILEG_BUY_LEG_OFFSET,
                        "option_type": "PE",
                        "action": "BUY",
                        "quantity": qty,
                        "pricetype": config.DEFAULT_OPTION_PRICE_TYPE,
                        "product": config.DEFAULT_OPTION_PRODUCT
                    }
                ]
                logger.log_order({'type': 'STRADDLE_LEGS', 'legs': legs})
            
            elif config.MULTILEG_STRATEGY_TYPE == "STRANGLE":
                # OTM CE + OTM PE (long both)
                legs = [
                    {
                        "offset": config.MULTILEG_BUY_LEG_OFFSET,
                        "option_type": "CE",
                        "action": "BUY",
                        "quantity": qty,
                        "pricetype": config.DEFAULT_OPTION_PRICE_TYPE,
                        "product": config.DEFAULT_OPTION_PRODUCT
                    },
                    {
                        "offset": config.MULTILEG_BUY_LEG_OFFSET,
                        "option_type": "PE",
                        "action": "BUY",
                        "quantity": qty,
                        "pricetype": config.DEFAULT_OPTION_PRICE_TYPE,
                        "product": config.DEFAULT_OPTION_PRODUCT
                    }
                ]
                logger.log_order({'type': 'STRANGLE_LEGS', 'legs': legs})
            
            if legs:
                order = self.trade_manager.enter_multi_leg_order(
                    underlying=config.PRIMARY_UNDERLYING,
                    legs=legs,
                    expiry_date=expiry_date
                )
                return order
            
            return None
        
        except Exception as e:
            logger.error(f"Error placing multileg order: {e}")
            return None
    
    def start(self):
        """Start the strategy"""
        try:
            logger.info("Starting ANGEL-X strategy...")
            
            # Check demo mode
            if config.DEMO_MODE:
                logger.info("=" * 80)
                logger.info("DEMO MODE ENABLED - Running in simulation")
                logger.info("=" * 80)
                if config.DEMO_SKIP_WEBSOCKET:
                    logger.info("WebSocket connection skipped in demo mode")
                    return True
            
            # Connect to data feed
            if config.WEBSOCKET_ENABLED and not config.DEMO_SKIP_WEBSOCKET:
                logger.info("Connecting to WebSocket...")
                if not self.data_feed.connect():
                    logger.error("Failed to connect to data feed")
                    if not config.DEMO_MODE:
                        return False
                    else:
                        logger.warning("Continuing in demo mode despite connection failure")
                        return True
                
                # Subscribe to LTP
                instruments = [{'exchange': config.UNDERLYING_EXCHANGE, 'symbol': config.PRIMARY_UNDERLYING}]
                self.data_feed.subscribe_ltp(instruments)
                
                logger.info(f"Subscribed to {config.PRIMARY_UNDERLYING} LTP stream")
            
            # Start bias engine
            self.bias_engine.start()
            
            # Start Greeks background refresh if enabled
            if getattr(config, 'GREEKS_BACKGROUND_REFRESH', True) and getattr(config, 'USE_REAL_GREEKS_DATA', True):
                self.greeks_manager.start_background_refresh()
                logger.info("Greeks background refresh started")
            
            # Set running flag
            self.running = True
            
            logger.info("Strategy started successfully")
            logger.info("="*80)
            
            # Main loop
            self._run_loop()
            
        except Exception as e:
            logger.error(f"Error starting strategy: {e}")
            self.stop()
            return False
    
    def _execute_automated_order(self, symbol: str, action: str, option_type: str) -> dict:
        """Execute automated order with dynamic strike selection and position sizing"""
        try:
            # Get current NIFTY LTP
            nifty_ltp = self.data_feed.get_ltp('NIFTY', 'NFO')
            if not nifty_ltp or nifty_ltp <= 0:
                logger.warning(f"Invalid NIFTY LTP: {nifty_ltp}")
                return None
            
            # Auto strike selection
            atm_strike = (int(nifty_ltp / 100) * 100)
            if option_type == "CE":
                # For Call buying: ATM or slightly OTM
                strike = atm_strike if action == "SELL" else atm_strike + 100
            else:  # PE
                # For Put buying: ATM or slightly OTM
                strike = atm_strike if action == "SELL" else atm_strike - 100
            
            # Get symbol and expiry
            expiry = self._get_current_expiry()
            option_symbol = f"NIFTY{expiry}{strike}{option_type}"
            
            # Auto position sizing (2% risk per trade)
            total_capital = config.STARTING_CAPITAL if hasattr(config, 'STARTING_CAPITAL') else 100000
            risk_per_trade = total_capital * config.RISK_PER_TRADE
            
            # Get option price for position sizing
            option_price = self.data_feed.get_ltp(option_symbol, 'NFO')
            if not option_price or option_price <= 0:
                logger.warning(f"Could not get price for {option_symbol}")
                return None
            
            # Calculate quantity: each lot of NIFTY option = 1 quantity = 75 shares
            quantity = max(1, int(risk_per_trade / (option_price * 75)))
            
            # Place order via OpenAlgo API
            response = self.client.optionsorder(
                'NFO',
                option_symbol,
                action.upper(),
                quantity,
                'MARKET',
                0,
                'MIS',
                'REGULAR',
                'DAY',
                '',
                'GTT',
                'CANCEL',
                0
            )
            
            if response and response.get('status') == 'success':
                order_id = response.get('orderid', 'UNKNOWN')
                logger.info(
                    f"✅ ORDER PLACED: {action} {quantity} {option_symbol} | "
                    f"Order ID: {order_id} | Strike: {strike}"
                )
                return response
            else:
                logger.warning(f"Order failed: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error in _execute_automated_order: {e}")
            return None
    
    def _run_loop(self):
        """Main strategy loop"""
        logger.info("Entering main trading loop...")
        
        # Expiry refresh tracking (time-based, following OpenAlgo best practices)
        last_expiry_refresh = 0
        EXPIRY_REFRESH_INTERVAL = 300  # 5 minutes
        
        try:
            while self.running:
                # Check daily limits
                if not self._check_daily_limits():
                    logger.warning("Daily limits exceeded, stopping")
                    self.running = False
                    break

                # Check trading hours
                if not self._is_trading_allowed():
                    time.sleep(5)
                    continue

                # Refresh expiry data every 5 minutes (not every iteration!)
                current_time = time.time()
                if current_time - last_expiry_refresh >= EXPIRY_REFRESH_INTERVAL:
                    self.expiry_manager.refresh_expiry_chain(config.PRIMARY_UNDERLYING)
                    expiry_stats = self.expiry_manager.get_expiry_statistics()
                    logger.info(f"✅ Expiry refreshed: {expiry_stats}")
                    last_expiry_refresh = current_time

                # Get expiry rules (lightweight, can be called every iteration)
                expiry_rules = self.expiry_manager.apply_expiry_rules()

                # Get latest market data with freshness check
                ltp_data = self.data_feed.get_ltp_with_timestamp(config.PRIMARY_UNDERLYING)

                # 🔴 CHECK DATA FRESHNESS
                if not ltp_data:
                    logger.warning("❌ NO DATA from broker - waiting for connection")
                    time.sleep(2)
                    continue

                ltp = ltp_data.get('price', 0)
                last_tick_time = ltp_data.get('timestamp')

                # Check if data is stale (older than 5 seconds)
                if last_tick_time:
                    age_sec = (datetime.now() - last_tick_time).total_seconds()
                    if age_sec > 5:  # config.DATA_FRESHNESS_TOLERANCE
                        logger.error(f"❌ STALE DATA: Last tick {age_sec:.1f}s old - HALTING trades")
                        logger.error(f"   WebSocket may be disconnected. Waiting for fresh data...")
                        time.sleep(3)
                        continue

                if not ltp or ltp <= 0:
                    logger.warning("Invalid LTP received, waiting...")
                    time.sleep(1)
                    continue

                # Update market state
                bias_state = self.bias_engine.get_bias()

                # For expiry scalping: If bias is UNKNOWN, determine manually
                # Use recent price trend to decide bullish/bearish
                if bias_state.value == "UNKNOWN":
                    # Default to PE (bearish) for most market conditions
                    bias_state = BiasState.BEARISH  # Force PE selection for testing
                    logger.info(f"⚠️ Bias was UNKNOWN, forcing {bias_state.value} for entry")

                bias_confidence = self.bias_engine.get_confidence()
                if bias_confidence <= 0:
                    bias_confidence = 50  # Default confidence for expiry scalping

                # Check for entry signal
                current_option_type = "CE" if bias_state.value == "BULLISH" else "PE"
                action = "BUY"  # Always BUY for entry

                # Get current expiry (format: 30DEC25)
                expiry_date = self._get_current_expiry()
                if not expiry_date:
                    logger.warning("No expiry date available")
                    time.sleep(2)
                    continue

                # Track symbol for Greeks
                atm_strike = round(ltp / 100) * 100
                option_symbol = f"{config.PRIMARY_UNDERLYING}{expiry_date}{int(atm_strike)}{current_option_type}"
                self.greeks_manager.track_symbol(option_symbol)

                # Get real Greeks from API
                greeks_data = self.greeks_manager.get_greeks(
                    symbol=option_symbol,
                    exchange="NFO",
                    underlying_symbol=config.PRIMARY_UNDERLYING,
                    underlying_exchange=config.UNDERLYING_EXCHANGE,
                    force_refresh=False  # Use cached data to respect API rate limit
                )

                # Get previous Greeks for delta/gamma comparison
                current_greeks, prev_greeks = self.greeks_manager.get_rolling_greeks(option_symbol)

                # Validate we have real data before proceeding
                if not greeks_data:
                    logger.warning(f"❌ Failed to get real Greeks for {option_symbol} - SKIPPING entry")
                    time.sleep(2)
                    continue

                # Extract real values
                current_delta = greeks_data.delta
                current_gamma = greeks_data.gamma
                current_iv = greeks_data.iv
                current_oi = greeks_data.oi
                current_ltp = greeks_data.ltp if greeks_data.ltp > 0 else ltp
                current_volume = greeks_data.volume
                bid = greeks_data.bid
                ask = greeks_data.ask

                # 🔴 Fallback for bid/ask on illiquid expiry day
                if bid <= 0:
                    bid = current_ltp * 0.999  # Slightly below LTP
                if ask <= 0:
                    ask = current_ltp * 1.001  # Slightly above LTP

                # Previous values
                if prev_greeks:
                    prev_delta = prev_greeks.delta
                    prev_gamma = prev_greeks.gamma
                    prev_iv = prev_greeks.iv
                    prev_oi = prev_greeks.oi
                    prev_ltp = prev_greeks.ltp
                    prev_volume = prev_greeks.volume
                else:
                    # First time - use current as previous
                    prev_delta = current_delta
                    prev_gamma = current_gamma
                    prev_iv = current_iv
                    prev_oi = current_oi
                    prev_ltp = current_ltp
                    prev_volume = current_volume

                # Calculate spread percentage
                current_spread_percent = ((ask - bid) / current_ltp * 100) if current_ltp > 0 else 0
                oi_change = current_oi - prev_oi

                logger.info(f"Entry Signal Check for {option_symbol}")
                logger.info(f"  Greeks: Δ={current_delta:.4f}, Γ={current_gamma:.4f}, IV={current_iv:.2f}%")
                logger.info(f"  OI: {current_oi} (Δ={oi_change}), Spread: {current_spread_percent:.2f}%")

                # Entry with REAL Greeks data
                logger.info(f"🔍 Calling check_entry_signal() with bias_state={bias_state.value}, bias_confidence={bias_confidence:.0f}%")
                entry_context = self.entry_engine.check_entry_signal(
                    bias_state=bias_state.value,
                    bias_confidence=bias_confidence,
                    current_delta=current_delta,           # ✅ REAL
                    prev_delta=prev_delta,                 # ✅ REAL
                    current_gamma=current_gamma,           # ✅ REAL
                    prev_gamma=prev_gamma,                 # ✅ REAL
                    current_oi=current_oi,                 # ✅ REAL
                    current_oi_change=oi_change,           # ✅ REAL
                    current_ltp=current_ltp,               # ✅ REAL
                    prev_ltp=prev_ltp,                     # ✅ REAL
                    current_volume=current_volume,         # ✅ REAL
                    prev_volume=prev_volume,               # ✅ REAL
                    current_iv=current_iv,                 # ✅ REAL
                    prev_iv=prev_iv,                       # ✅ REAL
                    bid=bid,                               # ✅ REAL
                    ask=ask,                               # ✅ REAL
                    selected_strike=atm_strike,            # ✅ REAL ATM
                    current_spread_percent=current_spread_percent  # ✅ REAL
                )
                logger.info(f"✓ check_entry_signal() returned: {entry_context is not None}")
                if entry_context:
                    logger.info(f"   Entry signal: {entry_context.signal}")

                if entry_context and entry_context.signal != EntrySignal.NO_SIGNAL:
                    logger.info(f"📝 Processing entry: {entry_context.option_type} @ ₹{entry_context.entry_price:.2f}")

                    # Place automated order with dynamic strike selection and position sizing
                    try:
                        response = self._execute_automated_order(
                            symbol=config.PRIMARY_UNDERLYING,
                            action=action,
                            option_type=entry_context.option_type
                        )

                        if response and response.get('status') == 'success':
                            order_id = response.get('orderid')
                            symbol = response.get('symbol')
                            logger.info(f"✅ Order placed: {order_id} | Symbol: {symbol}")

                            # Log to session
                            self.session_logger.log_event('ORDER_PLACED', {
                                'order_id': order_id,
                                'symbol': symbol,
                                'option_type': entry_context.option_type,
                                'entry_price': entry_context.entry_price,
                                'delta': entry_context.entry_delta
                            })

                            # Wait before next entry check
                            time.sleep(5)
                        else:
                            logger.error(f"❌ Order failed: {response}")

                    except Exception as e:
                        logger.error(f"❌ Order placement error: {e}")

                    # Continue to next iteration
                    time.sleep(2)
                    continue

                # Simplified - no exit management for now
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Stopping main loop on keyboard interrupt")
            self.running = False
        except Exception as e:
            logger.error(f"❌ Error in main loop: {e}", exc_info=True)
            time.sleep(5)

        except KeyboardInterrupt:
            logger.info("Stopping main loop on keyboard interrupt")
        except Exception as e:
            logger.error(f"❌ Unhandled error in _run_loop: {e}", exc_info=True)

    def _check_daily_limits(self) -> bool:
        """Basic daily risk guardrails."""
        max_loss = getattr(config, 'MAX_DAILY_LOSS_AMOUNT', None)
        max_trades = getattr(config, 'MAX_TRADES_PER_DAY', None)

        if max_loss is not None and self.daily_pnl < -float(max_loss):
            logger.warning(f"Daily loss limit exceeded: ₹{self.daily_pnl:.2f} vs limit ₹{max_loss}")
            return False

        if max_trades is not None and self.daily_trades >= int(max_trades):
            logger.warning(f"Daily trade limit reached: {self.daily_trades}/{max_trades}")
            return False

        return True

    def _is_trading_allowed(self) -> bool:
        """Check basic session window from config if available."""
        start_str = getattr(config, 'TRADING_SESSION_START', None)
        end_str = getattr(config, 'TRADING_SESSION_END', None)
        if not start_str or not end_str:
            return True

        now = datetime.now().time()
        start_time = datetime.strptime(start_str, "%H:%M").time()
        end_time = datetime.strptime(end_str, "%H:%M").time()
        return start_time <= now <= end_time

    def stop(self):
        """Gracefully stop engines and data feed."""
        logger.info("Stopping ANGEL-X strategy...")
        self.running = False

        try:
            self.bias_engine.stop()
        except Exception as e:
            logger.warning(f"BiasEngine stop warning: {e}")

        try:
            self.data_feed.disconnect()
        except Exception as e:
            logger.warning(f"DataFeed disconnect warning: {e}")

        try:
            if hasattr(self, 'greeks_manager'):
                self.greeks_manager.stop_background_refresh()
        except Exception as e:
            logger.warning(f"Greeks manager stop warning: {e}")

        try:
            if hasattr(self, 'network_monitor'):
                self.network_monitor.stop_monitoring()
        except Exception as e:
            logger.warning(f"Network monitor stop warning: {e}")

    def _get_current_expiry(self) -> str:
        """Get current weekly expiry in format 30DEC25"""
        from datetime import datetime, timedelta

        # Find next Tuesday (NIFTY weekly expiry)
        today = datetime.now()
        days_ahead = (1 - today.weekday()) % 7  # Tuesday is 1
        if days_ahead == 0 and today.hour >= 15:  # After 3 PM on Tuesday
            days_ahead = 7

        next_tuesday = today + timedelta(days=days_ahead)
        return next_tuesday.strftime("%d%b%y").upper()


def main():
    """Main entry point"""
    strategy = AngelXStrategy()
    
    # Skip start() in demo mode - just show it's ready
    if config.DEMO_MODE:
        logger.info("DEMO MODE: Strategy initialized and ready")
        logger.info("To start live trading, set DEMO_MODE = False in config")
        import sys
        sys.stdout.flush()
        sys.stderr.flush()
        return
    
    strategy.start()


if __name__ == "__main__":
    main()
