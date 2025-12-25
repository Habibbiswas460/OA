# ANGEL-X Expiry-Day Scalp Trading - Architecture Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ANGEL-X STRATEGY STARTUP                         │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
                    ┌─────────────────────────┐
                    │  AngelXStrategy.__init__│
                    └─────────────────────────┘
                                  ↓
                ┌─────────────────────────────────────┐
                │  Initialize ExpiryManager()         │
                │  refresh_expiry_chain(NIFTY)        │
                └─────────────────────────────────────┘
                                  ↓
                        ┌─────────────────┐
                        │  OpenAlgo API   │
                        │  getoptionchain │
                        │  (fetch expiry) │
                        └─────────────────┘
                                  ↓
                    ┌──────────────────────────┐
                    │ Parse expiry dates from  │
                    │ API response             │
                    └──────────────────────────┘
                                  ↓
                    ┌──────────────────────────┐
                    │ Classify expiry types:   │
                    │ WEEKLY/MONTHLY/QUARTERLY │
                    └──────────────────────────┘
                                  ↓
                    ┌──────────────────────────┐
                    │ Select nearest WEEKLY    │
                    │ expiry (ANGEL-X default) │
                    └──────────────────────────┘
                                  ↓
                        ┌─────────────────────────────┐
                        │ ExpiryInfo object created:  │
                        │ - expiry_date: 2025-02-06   │
                        │ - expiry_type: WEEKLY       │
                        │ - days_to_expiry: 0-7       │
                        └─────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│                     MAIN TRADING LOOP                               │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
                    ┌──────────────────────────┐
                    │ Every 100 trades:        │
                    │ Refresh expiry chain     │
                    │ (update days_to_expiry)  │
                    └──────────────────────────┘
                                  ↓
                ┌─────────────────────────────────────┐
                │ apply_expiry_rules()                │
                │ Returns rule dict based on:         │
                │ - days_to_expiry                    │
                └─────────────────────────────────────┘
                                  ↓
        ┌───────────────────────────────────────────────┐
        │       EXPIRY RULES DECISION TREE              │
        └───────────────────────────────────────────────┘
        
        Is days_to_expiry == 0?
        ├─ YES (EXPIRY DAY)
        │  └─ {pos_factor: 0.30, risk: 0.5%, SL: 3%, time: 5min}
        │
        ├─ days_to_expiry == 1?
        │  └─ {pos_factor: 0.50, risk: 1.0%, SL: 4%, time: 10min}
        │
        ├─ days_to_expiry in [2,3]? (EXPIRY WEEK)
        │  └─ {pos_factor: 0.70, risk: 1.5%, SL: 5%, time: 15min}
        │
        └─ days_to_expiry >= 4? (NORMAL)
           └─ {pos_factor: 1.00, risk: 2.0%, SL: 6%, time: 5min}
                                  ↓
        ┌───────────────────────────────────────────────┐
        │       TRADE ENTRY DECISION                     │
        └───────────────────────────────────────────────┘
                                  ↓
                ┌─────────────────────────────────┐
                │ Check Entry Signal (Bias + Mom) │
                └─────────────────────────────────┘
                                  ↓
                        Entry Signal FOUND?
                        ├─ NO → Wait
                        │
                        └─ YES
                             ↓
                    ┌────────────────────────┐
                    │ Calculate position     │
                    │ size (risk-first)      │
                    └────────────────────────┘
                             ↓
                    ┌────────────────────────────────┐
                    │ Apply expiry position factor:  │
                    │ qty = base_qty × pos_factor    │
                    │ (30% reduction on expiry day)  │
                    └────────────────────────────────┘
                             ↓
                    ┌────────────────────────────────┐
                    │ Build order symbol:            │
                    │ NIFTY18800CE06FEB2025          │
                    │ (via expiry_manager)           │
                    └────────────────────────────────┘
                             ↓
                    ┌────────────────────────────────┐
                    │ Place Order with OpenAlgo:     │
                    │ symbol, qty, price, action     │
                    └────────────────────────────────┘
                             ↓
                    ┌────────────────────────────────┐
                    │ Trade Manager: Open Trade      │
                    │ - entry_time: NOW              │
                    │ - time_in_trade_sec: 0         │
                    └────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────┐
│              TRADE MANAGEMENT LOOP (on each tick)                    │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
                    ┌─────────────────────────┐
                    │ Get latest market data  │
                    │ (LTP, bid, ask, Greeks) │
                    └─────────────────────────┘
                                  ↓
                    ┌─────────────────────────┐
                    │ Call update_trade()     │
                    │ with expiry_rules=dict  │
                    └─────────────────────────┘
                                  ↓
                ┌───────────────────────────────────────┐
                │ Update Trade:                         │
                │ - current_price                       │
                │ - pnl = (price - entry) × qty         │
                │ - time_in_trade_sec = (now - entry)   │
                └───────────────────────────────────────┘
                                  ↓
        ┌─────────────────────────────────────────────────┐
        │      CHECK EXIT TRIGGERS (Priority Order)        │
        └─────────────────────────────────────────────────┘
                                  ↓
        
        ┌──────────────────────────────────────────────────┐
        │ TIER 1: EXPIRY-DAY TIME-BASED EXIT (if enabled)  │
        │ (Highest Priority - Capital Protection)          │
        └──────────────────────────────────────────────────┘
        
        if expiry_rules:
            max_time = 300  # 5 minutes on expiry day
            min_time = 20   # 20 seconds minimum
            
            ┌─ time > max_time?
            │  └─ YES → EXIT IMMEDIATELY
            │     ├─ If profitable: "expiry_time_based_profit_exit"
            │     └─ If loss: "expiry_time_forced_exit_loss"
            │
            └─ time > min_time AND profit?
               └─ YES → EXIT AT PROFIT TARGET
                  └─ "expiry_time_based_target"
                                  ↓
        
        ┌──────────────────────────────────────────────────┐
        │ TIER 2: GREEK-BASED EXITS (if no time exit)      │
        │ (Normal Priority)                                │
        └──────────────────────────────────────────────────┘
        
        ├─ Hard SL hit? → "hard_sl_hit"
        ├─ Target hit? → "target_hit"
        ├─ Delta weakness? → "delta_weakness"
        ├─ Gamma rollover? → "gamma_rollover"
        ├─ Theta damage? → "theta_damage"
        ├─ IV crush? → "iv_crush"
        └─ OI-Price mismatch? → "oi_price_mismatch"
                                  ↓
        
        Exit reason found?
        ├─ NO → Continue holding trade
        │
        └─ YES
             ↓
        ┌──────────────────────────────────────┐
        │ Exit Trade:                          │
        │ - exit_time = NOW                    │
        │ - exit_reason = (reason from above)  │
        │ - Calculate final PnL                │
        └──────────────────────────────────────┘
             ↓
        ┌──────────────────────────────────────┐
        │ Log to Trade Journal:                │
        │ - Entry/Exit prices                  │
        │ - Entry/Exit Greeks                  │
        │ - Exit reason tag                    │
        │ - Duration: 4 min 15 sec             │
        │ - PnL: ₹450 (+3.2%)                  │
        └──────────────────────────────────────┘
             ↓
        ┌──────────────────────────────────────┐
        │ Update Daily Stats:                  │
        │ - daily_pnl += trade.pnl             │
        │ - daily_trades += 1                  │
        └──────────────────────────────────────┘
             ↓
        Loop back to trade entry


┌─────────────────────────────────────────────────────────────────────┐
│                    EXPIRY MANAGER INTERNALS                          │
└─────────────────────────────────────────────────────────────────────┘

fetch_available_expiries(underlying="NIFTY")
    ↓ OpenAlgo API call
┌─ getoptionchain() → {"expiryDates": ["06-02-2025", "13-02-2025", ...]}
│
├─ Parse dates
│
├─ Create list of ExpiryInfo objects
│
├─ Sort by date (ascending)
│
└─ Return: [
    ExpiryInfo(date=06-02-2025, type=WEEKLY, days=0),
    ExpiryInfo(date=13-02-2025, type=WEEKLY, days=7),
    ExpiryInfo(date=27-02-2025, type=MONTHLY, days=21)
  ]

select_nearest_weekly_expiry()
    ↓
├─ Filter expiry_list for type='WEEKLY'
│
├─ Get first (nearest)
│
└─ Return: ExpiryInfo(date=06-02-2025, type=WEEKLY, days=0)

apply_expiry_rules() → Dict
    ↓
├─ Get current selected expiry
│
├─ Calculate days_to_expiry
│
├─ if days == 0:
│  └─ return {pos: 0.30, risk: 0.5%, SL: 3%, time: 300s}
│
├─ elif days == 1:
│  └─ return {pos: 0.50, risk: 1.0%, SL: 4%, time: 600s}
│
├─ elif days in [2,3]:
│  └─ return {pos: 0.70, risk: 1.5%, SL: 5%, time: 900s}
│
└─ else:
   └─ return {pos: 1.00, risk: 2.0%, SL: 6%, time: 300s}

build_order_symbol(strike=18800, option_type="CE")
    ↓
├─ Get expiry_date from selected expiry
│
├─ Format date: "06-02-2025" → "06FEB2025"
│
├─ Construct symbol: "NIFTY" + "18800" + "CE" + "06FEB2025"
│
└─ Return: "NIFTY18800CE06FEB2025"


┌─────────────────────────────────────────────────────────────────────┐
│                    EXAMPLE TRADING DAY                               │
└─────────────────────────────────────────────────────────────────────┘

09:15 - Market Opens
        └─ ExpiryManager detects: NIFTY weekly expires TODAY (0 days)
        └─ Expiry rules set to: pos=30%, risk=0.5%, SL=3%, max=5min
        └─ Log: "EXPIRY DAY DETECTED - Applying extreme caution"

10:30 - Entry Signal
        └─ Bias = BULLISH, Entry = MOM
        └─ Base qty = 100 shares
        └─ Apply expiry factor: 100 × 0.30 = 30 shares
        └─ Build symbol: NIFTY18800CE06FEB2025
        └─ Place order: 30 qty @ ₹150

10:31 - Trade Opened
        └─ Trade ID: abc123
        └─ Entry price: ₹150
        └─ Time in trade: 0 sec

10:33 - Time Check
        └─ time_in_trade = 120 seconds
        └─ min_time = 20 sec ✓ (passed)
        └─ profit = ₹15 (10% gain)
        └─ Check: time > min_time AND profit hit?
        └─ Current price = ₹160 (7% gain = target)
        └─ EXIT → "expiry_time_based_target"

10:33 - Trade Closed
        └─ Exit reason: "expiry_time_based_target"
        └─ Exit price: ₹160
        └─ PnL: ₹300 (10%)
        └─ Duration: 120 seconds
        └─ Log to journal

14:45 - Check Expiry
        └─ Time to close: 15 minutes
        └─ No new trades allowed near close
        └─ Daily trades: 4
        └─ Daily PnL: ₹1,200

15:30 - Market Close
        └─ All trades closed
        └─ End of expiry day
        └─ Tomorrow: Normal trading resumes


┌─────────────────────────────────────────────────────────────────────┐
│                 DECISION FLOW - TRADE ENTRY                          │
└─────────────────────────────────────────────────────────────────────┘

                          Entry Signal?
                             ↓
                        YES ← → NO
                        ↓      ↓
                   Continue   Wait
                        ↓
                   Entry validation
                        ↓
                   Position size
                        ↓
              Get expiry_rules dict
                        ↓
           Apply position_size_factor
                ├─ Expiry day: × 0.30
                ├─ Last day: × 0.50
                ├─ Expiry week: × 0.70
                └─ Normal: × 1.00
                        ↓
            Build OpenAlgo symbol
                        ↓
            Place order with adjusted qty
                        ↓
           Open trade with time tracking
                        ↓
            Enter trade management loop


┌─────────────────────────────────────────────────────────────────────┐
│              EXIT DECISION TREE - COMPLETE PRIORITY                  │
└─────────────────────────────────────────────────────────────────────┘

                    update_trade() called
                            ↓
                  Check exit triggers
                            ↓
        ┌───────────────────────────────────┐
        │ PRIORITY 1: Time-Based (if expiry)|
        └───────────────────────────────────┘
                            ↓
        time > max_time?
        ├─ YES → EXIT (capital protection)
        └─ NO → Continue checking
                            ↓
        time > min_time AND profitable?
        ├─ YES → EXIT (take profit)
        └─ NO → Continue checking
                            ↓
        ┌───────────────────────────────────┐
        │ PRIORITY 2: Greek-Based Exits     |
        └───────────────────────────────────┘
                            ↓
        Hard SL hit? → YES → EXIT
        ↓
        NO
        ↓
        Target hit? → YES → EXIT
        ↓
        NO
        ↓
        Delta weakness? → YES → EXIT
        ↓
        NO
        ↓
        Gamma rollover? → YES → EXIT
        ↓
        NO
        ↓
        Other triggers? → YES → EXIT
        ↓
        NO
        ↓
        CONTINUE HOLDING TRADE
        (return to market tick)


┌─────────────────────────────────────────────────────────────────────┐
│                    POSITION SIZE OVER EXPIRY                         │
└─────────────────────────────────────────────────────────────────────┘

Days to Expiry     Position Size    Risk Per Trade    Hard SL    Max Time
─────────────────────────────────────────────────────────────────────────
7+ days            100%             2.0%              6%         5 min
4-6 days           100%             2.0%              6%         5 min
2-3 days (week)    70%              1.5%              5%         15 min
1 day (last)       50%              1.0%              4%         10 min
0 days (expiry)    30%              0.5%              3%         5 min
─────────────────────────────────────────────────────────────────────────

Graph:

Position Size %
    │                          100%
    │                           │
 90 ├───────────────────────────┤
    │                           │
 80 ├───                        │
    │   │                       │
 70 ├───┤                       │
    │   │                       │
 60 ├───┤                       │
    │   │                       │
 50 ├───┼───┐                   │
    │   │   │                   │
 40 ├───┼───┤                   │
    │   │   │                   │
 30 ├───┼───┼───┐               │
    │   │   │   │               │
    └───┴───┴───┴───────────────┴───── Days to Expiry
      0   1  2-3  4+

Position Size Reduction Schedule:
- 7+ days before expiry: Trade normally (100%)
- 4-6 days: Still normal (100%)
- 2-3 days: Reduce to 70% (expiry week caution)
- 1 day: Reduce to 50% (last day heightened caution)
- 0 days: Reduce to 30% (EXPIRY DAY - extreme caution)

