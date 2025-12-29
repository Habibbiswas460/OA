"""
ANGEL-X: Professional Options Scalping Strategy
Greeks + OI Momentum System for NIFTY/BANKNIFTY weeklies
Scalp duration: 1-5 minutes | Risk-first architecture

EXAMPLE CONFIGURATION FILE
Copy this file to config.py and update with your credentials
"""

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_TO_FILE = True
LOG_DIR = "./logs"

# ============================================================================
# OpenAlgo API Configuration
# ============================================================================
OPENALGO_API_KEY = "9f9607c800af242c7efe0527d9019b196939af8d97a42d7096e356900fbe29b0"  # Replace with your actual API key
OPENALGO_HOST = "http://habiqx.cc:5000"  # Replace with your OpenAlgo server
OPENALGO_WS_URL = "ws://habiqx.cc:8765"  # Replace with your WebSocket URL
STRATEGY_NAME = "ANGEL-X"
OPENALGO_CLIENT_ID = "your_client_id" 

# ============================================================================
# SYMBOL CONFIGURATION - ANGEL-X ALLOWED INSTRUMENTS
# ============================================================================
# Primary symbols (NIFTY/BANKNIFTY weeklies ONLY)
ALLOWED_UNDERLYING = ["NIFTY", "BANKNIFTY"]
PRIMARY_UNDERLYING = "NIFTY"  # Default
UNDERLYING_EXCHANGE = "NSE_INDEX"

# Options scalp configuration
OPTION_EXPIRY = "weekly"  # Weekly options only (liquid)
ALLOWED_STRIKES_RANGE = 5  # ATM ±5 strikes scan
OPTION_PRODUCT = "MIS"  # Intraday only (scalp)
MINIMUM_LOT_SIZE = 75  # 1 lot = 75 qty

# ============================================================================
# 1) TIME WINDOW FILTERS - TRADEABLE HOURS
# ============================================================================
TRADING_SESSION_START = "09:15"
TRADING_SESSION_END = "15:30"

# No trade periods
NO_TRADE_START_TIME = "09:15"     # Opening manipulation zone
NO_TRADE_END_TIME = "09:20"
NO_TRADE_LAST_MINUTES = 45        # Last 45 min before close (expiry risk)

# Best trading windows (most liquid + stable)
BEST_TRADING_WINDOWS = [
    ("09:25", "12:33"),  # Morning + lunch
    ("13:30", "14:45")   # Post-lunch (before final rush)
]

# ============================================================================
# 2) MARKET CONTEXT FILTERS
# ============================================================================
# Volatility thresholds (IV proxy if VIX unavailable)
IV_EXTREMELY_LOW_THRESHOLD = 15.0   # Skip if IV too low (theta eats)
IV_EXTREMELY_HIGH_THRESHOLD = 50.0  # Only quick scalps if IV too high
IV_SAFE_ZONE = (20.0, 40.0)         # Optimal IV range

# Market structure (micro-trend) detection
MICRO_TREND_LOOKBACK_CANDLES = 5    # For HH-HL, LL-LH detection
CHOPPY_MARKET_THRESHOLD = 0.4       # If market is sideways >40%, reduce trade frequency

# ============================================================================
# 3) BIAS ENGINE - MARKET STATE THRESHOLDS
# ============================================================================
# Bullish Bias Requirements (CALL side permission)
BULLISH_DELTA_MIN = 0.45            # Delta ≥ 0.45
BULLISH_GAMMA_RISING = True         # Gamma must be increasing
BULLISH_OI_VOLUME_ALIGN = True      # OI ↑ + LTP ↑ + Volume ↑

# Bearish Bias Requirements (PUT side permission)
BEARISH_DELTA_MAX = -0.45           # Delta ≤ -0.45
BEARISH_GAMMA_RISING = True         # Gamma must be increasing
BEARISH_OI_VOLUME_ALIGN = True      # OI ↑ + LTP ↑ + Volume ↑

# No Trade Bias Conditions
NO_TRADE_DELTA_WEAK = 0.35          # If delta < 0.35, weak direction
NO_TRADE_GAMMA_FLAT = 0.01          # If gamma change < 0.01, flat
NO_TRADE_OI_PRICE_MISMATCH = True   # OI↑ but LTP flat = trap
NO_TRADE_IV_DROP_THRESHOLD = -5.0   # IV dropping % while price flat

# ============================================================================
# 4) STRIKE SELECTION ENGINE - OPTION HEALTH PROFILE
# ============================================================================
# Greeks ideal scalping band
IDEAL_DELTA_CALL = (0.45, 0.65)     # Call delta zone
IDEAL_DELTA_PUT = (-0.65, -0.45)    # Put delta zone
IDEAL_GAMMA_MIN = 0.002             # Minimum gamma for scalp
IDEAL_THETA_MAX = -0.05             # Max time decay allowed (option basis)
IDEAL_VEGA_MIN = 0.01               # Minimum vega (IV sensitivity)

# Liquidity & Spread Filters (mandatory)
MAX_SPREAD_PERCENT = 1.0            # Spread ≤ 1% of LTP
MIN_VOLUME_THRESHOLD = 50           # Minimum traded contracts
MIN_OI_THRESHOLD = 100              # Minimum open interest

# ============================================================================
# 5) ENTRY ENGINE - TRIGGER CONDITIONS
# ============================================================================
# All must align for entry
ENTRY_LTP_RISING = True             # Current LTP > Previous LTP
ENTRY_VOLUME_RISING = True          # Current Volume > Previous Volume
ENTRY_OI_RISING = True              # Current OI ≥ Previous OI
ENTRY_GAMMA_RISING = True           # Current Gamma > Previous Gamma
ENTRY_DELTA_POWER_ZONE = True       # Delta in 0.45-0.60 band

# Entry rejection thresholds (even if bias exists)
REJECT_OI_FLAT_THRESHOLD = 0.002    # OI rising but LTP flat
REJECT_IV_DROP_PERCENT = -3.0       # IV dropping >3%
REJECT_SPREAD_WIDENING = 1.5        # Spread jump >1.5%
REJECT_DELTA_SPIKE_COLLAPSE = 0.20  # Delta spikes then collapses

# Entry profit target
ENTRY_PROFIT_TARGET_PERCENT = 7.0   # +7% target for early exits on expiry

# ============================================================================
# 6) POSITION SIZING ENGINE - RISK PARAMETERS
# ============================================================================
# Per trade risk limits (options scalp = lower risk)
RISK_PER_TRADE_MIN = 0.01           # 1% minimum
RISK_PER_TRADE_MAX = 0.05           # 5% maximum (scalp limit)
RISK_PER_TRADE_OPTIMAL = 0.02       # 2% recommended

# Hard SL percent (premium-based)
HARD_SL_PERCENT_MIN = 0.06          # 6% minimum SL
HARD_SL_PERCENT_MAX = 0.08          # 8% typical SL
HARD_SL_PERCENT_EXCEED_SKIP = 0.10  # >10% SL needed → skip trade

# Capital & Position limits
CAPITAL = 100000                     # Total trading capital
MAX_CONCURRENT_POSITIONS = 1         # Only 1 position at a time (scalp style)
MAX_POSITION_SIZE = 100              # Maximum qty per trade (in units, not lots)
AUTO_POSITION_SIZING = True          # Auto-calc position from risk%

# Non-negotiable rules enforcement
ENFORCE_NO_AVERAGING = True          # Forbidden
ENFORCE_SL_NO_WIDENING = True        # Forbidden
ENFORCE_RECOVERY_NO_SIZE_INCREASE = True  # Forbidden

# ============================================================================
# 7) EXECUTION ENGINE - ORDER RULES
# ============================================================================
# Pre-execution checks
PRE_EXEC_SPREAD_SAFETY = True        # Re-check spread before order
PRE_EXEC_LTP_JUMP_TOLERANCE = 0.5   # % tolerance for LTP movement
PRE_EXEC_LIQUIDITY_RECHECK = True    # Verify liquidity alive

# Order placement strategy
USE_MARKET_ORDERS = False            # False = use limit orders (safer)
USE_AGGRESSIVE_LIMITS = False        # False = conservative limits
LIMIT_ORDER_OFFSET_PERCENT = 0.5     # 0.5% offset from LTP

# ============================================================================
# 8) TRADE MANAGEMENT ENGINE - GREEK-BASED EXITS
# ============================================================================
# Hard Stop-Loss (absolute, no exceptions)
HARD_SL_PREMIUM_PERCENT = 0.07       # -7% premium → exit immediately

# Greek-based exit triggers (edge gone)
EXIT_DELTA_WEAKNESS_PERCENT = 0.15   # Delta degrades >15% → exit
EXIT_GAMMA_ROLLOVER = True           # Gamma stops rising → exit
EXIT_THETA_DAMAGE_THRESHOLD = -0.05  # Theta dominates + price flat → exit
EXIT_IV_CRUSH_PERCENT = -5.0         # IV drops >5% + price stalls → exit
EXIT_OI_PRICE_MISMATCH = True        # OI↑ but price flat consistently → exit

# Profit protection
PROFIT_PARTIAL_BOOKING = True        # Partial exit at first target
PROFIT_FIRST_TARGET_PERCENT = 0.065  # +6.5% first target
REMAINING_GREEK_TRAILING = True      # Remaining qty = Greek trailing

# ============================================================================
# 9) TRAP DETECTION ENGINE
# ============================================================================
# OI Trap patterns detection
DETECT_OI_TRAP_NO_PREMIUM_RISE = True      # OI↑ but premium flat
DETECT_OI_TRAP_PREMIUM_RISE_NO_OI = True   # Premium↑ but OI↓
DETECT_OI_TRAP_SPIKE_NO_FOLLOW = True      # OI spike with no continuation

# IV Trap patterns detection
DETECT_IV_TRAP_SUDDEN_DROP = True          # IV drops >5% post-entry
DETECT_IV_TRAP_CHOPPY_UNDERLYING = True    # High IV + choppy price

# Spread/Slippage Trap detection
DETECT_SPREAD_TRAP_WIDE_ENTRY = True       # Entry with >1.5% spread
DETECT_LIQUIDITY_DROP = True               # Volume/OI suddenly vanish

# ============================================================================
# 10) DAILY RISK MANAGEMENT - KILL SWITCH
# ============================================================================
# Daily maximum loss (account protection)
MAX_DAILY_LOSS_PERCENT = 0.03        # 3% of capital max daily loss
MAX_DAILY_LOSS_AMOUNT = 3000         # OR hard amount (whichever lower)

# Consecutive loss control
CONSECUTIVE_LOSS_LIMIT = 2           # 2 consecutive losses → cooldown
COOLDOWN_AFTER_CONSECUTIVE_LOSS = 15 # 15 min pause after 2 losses
STOP_TRADING_AFTER_N_LOSSES = 3      # 3 losses in a row → stop day

# Trade frequency control
MAX_TRADES_PER_DAY = 5               # Maximum trades/day (opportunity-based, not forced)
TRADE_FREQUENCY_CONTROL = True       # Don't overtrade

# ============================================================================
# 11) LOGGING & JOURNAL
# ============================================================================
ENABLE_TRADE_JOURNAL = True          # Capture every trade
JOURNAL_FIELDS = [
    'timestamp', 'underlying', 'strike', 'option_type',
    'entry_price', 'entry_delta', 'entry_gamma', 'entry_theta', 'entry_vega', 'entry_iv',
    'exit_price', 'exit_delta', 'exit_gamma', 'exit_reason',
    'pnl_amount', 'pnl_percent', 'time_in_trade_seconds',
    'entry_spread', 'exit_spread',
    'entry_reason_tags', 'exit_reason_tags',
    'rule_violations'
]

ENABLE_BACKTEST_LOGGING = True       # For future ML/tuning
ENABLE_DEBUG_LOGGING = False         # Set True for troubleshooting

# ============================================================================
# 12) INSTITUTIONAL RULES (Non-negotiable)
# ============================================================================
"""
Rule 1: Bias gives permission; Entry gives timing.
Rule 2: Greeks lead; price confirms.
Rule 3: If Greeks agree but price doesn't move → trust price, exit.
Rule 4: No averaging. No revenge. No exceptions.
Rule 5: Risk manager has veto power.
Rule 6: When Gamma peaks, don't hope — exit.
Rule 7: Survival first. Then profit.
"""

# ============================================================================
# 13) WEBSOCKET & DATA STREAMING
# ============================================================================
WEBSOCKET_ENABLED = True
WEBSOCKET_RECONNECT_DELAY = 5
WEBSOCKET_PING_INTERVAL = 30

# Data health requirements
DATA_FRESHNESS_TOLERANCE = 5         # seconds (if stale > 5s, no trade)
REQUIRE_BID_ASK_BOTH = True          # Both bid & ask required
MIN_VALID_SPREAD = 0.01              # Minimum meaningful spread

# Bias engine update interval
BIAS_UPDATE_INTERVAL = 60             # seconds

# ============================================================================
# Logging Configuration
# ============================================================================
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_TO_FILE = True
LOG_DIR = "logs"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# ============================================================================
# Trading Hours
# ============================================================================
MARKET_START_TIME = "09:15"
MARKET_END_TIME = "15:30"
SQUARE_OFF_TIME = "15:15"

# ============================================================================
# Mode Configuration
# ============================================================================
PAPER_TRADING = False  # Set to True for paper trading
DRY_RUN = False  # Set to True for testing without orders
ANALYZER_MODE = True  # OpenAlgo analyzer mode (simulated responses)

# ============================================================================
# Notification Settings
# ============================================================================
ENABLE_NOTIFICATIONS = False
OPENALGO_TELEGRAM_USERNAME = ""  # Your OpenAlgo login username for telegram alerts
