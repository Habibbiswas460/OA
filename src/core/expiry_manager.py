"""
ANGEL-X Expiry Manager
Auto-detect expiry from OpenAlgo and manage expiry-day special rules
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from enum import Enum
try:
    from openalgo import api
except ImportError:
    api = None
from config import config
from src.utils.logger import StrategyLogger
from src.core.order_manager import OrderManager

logger = StrategyLogger.get_logger(__name__)


class ExpiryType(Enum):
    """Expiry type"""
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"


class ExpiryInfo:
    """Expiry information"""
    def __init__(self, expiry_date: str, expiry_type: ExpiryType, days_to_expiry: int):
        self.expiry_date = expiry_date
        self.expiry_type = expiry_type
        self.days_to_expiry = days_to_expiry
        self.is_expiry_day = days_to_expiry <= 0
        self.is_last_day = days_to_expiry == 0
        self.is_expiry_week = days_to_expiry <= 3


class ExpiryManager:
    """
    ANGEL-X Expiry Manager
    
    Automatically fetches available expiries from OpenAlgo
    and applies expiry-specific trading rules
    """
    
    def __init__(self):
        """Initialize expiry manager"""
        if api is None:
            logger.warning("OpenAlgo library not available")
            self.client = None
        else:
            try:
                self.client = api(
                    api_key=config.OPENALGO_API_KEY,
                    host=config.OPENALGO_HOST,
                    ws_url=config.OPENALGO_WS_URL
                )
                logger.info("ExpiryManager initialized with OpenAlgo API")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAlgo client: {e}")
                self.client = None
        
        self.available_expiries: List[ExpiryInfo] = []
        self.current_expiry: Optional[ExpiryInfo] = None
        self.selected_underlying = config.PRIMARY_UNDERLYING
        self._order_manager = OrderManager()
        
        # Expiry-day rules
        self.expiry_day_rules = {
            'max_position_size': 0.5,  # 50% of normal
            'risk_percent': 0.01,      # 1% only on expiry day
            'min_time_in_trade_sec': 30,  # Exit after 30s if profitable
            'max_time_in_trade_sec': 300,  # Max 5 min
            'strict_sl_percent': 0.05,  # 5% SL only
            'reduce_entry_frequency': True,  # Less aggressive
        }
        
        logger.info("ExpiryManager initialized")
    
    def fetch_available_expiries(self, underlying: str) -> List[ExpiryInfo]:
        """
        Fetch available expiries from OpenAlgo for given underlying
        Gracefully handles if API method is not available
        
        Args:
            underlying: NIFTY or BANKNIFTY
        
        Returns:
            List of ExpiryInfo objects sorted by date
        """
        if not self.client:
            logger.error("OpenAlgo client not initialized")
            # Return default weekly expiries (Thursday and next Thursday)
            return self._get_default_expiries()
        
        try:
            # Try to get option chain from OpenAlgo
            # Use generic method call as getoptionchain may not be available
            if hasattr(self.client, 'getoptionchain'):
                response = self.client.getoptionchain(
                    exchange='NFO',
                    symbol=underlying
                )
            elif hasattr(self.client, 'get_option_chain'):
                response = self.client.get_option_chain(
                    exchange='NFO',
                    symbol=underlying
                )
            else:
                logger.warning(f"OpenAlgo API does not support option chain fetching")
                # Return default expiries
                return self._get_default_expiries()
            
            if not response:
                logger.warning(f"No option chain data for {underlying}, using defaults")
                return self._get_default_expiries()
            
            # Extract unique expiry dates from response
            expiry_dates = set()
            if isinstance(response, list):
                for item in response:
                    if 'expiry' in item:
                        expiry_dates.add(item['expiry'])
            
            if not expiry_dates:
                logger.warning(f"No expiry dates found in option chain, using defaults")
                return self._get_default_expiries()
            
            # Convert to ExpiryInfo objects
            today = datetime.now().date()
            expiry_list = []
            
            for exp_date_str in sorted(expiry_dates):
                try:
                    # Parse date (format may vary, try common formats)
                    exp_date = None
                    for fmt in ['%d%b%y', '%d-%b-%y', '%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            exp_date = datetime.strptime(exp_date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    
                    if not exp_date:
                        logger.warning(f"Could not parse expiry date: {exp_date_str}")
                        continue
                        continue
                    
                    # Calculate days to expiry
                    days_to_exp = (exp_date - today).days
                    
                    # Determine expiry type
                    if days_to_exp <= 7:
                        exp_type = ExpiryType.WEEKLY
                    elif days_to_exp <= 30:
                        exp_type = ExpiryType.MONTHLY
                    else:
                        exp_type = ExpiryType.QUARTERLY
                    
                    expiry_info = ExpiryInfo(
                        expiry_date=exp_date_str,
                        expiry_type=exp_type,
                        days_to_expiry=days_to_exp
                    )
                    
                    expiry_list.append(expiry_info)
                
                except Exception as e:
                    logger.warning(f"Error processing expiry date {exp_date_str}: {e}")
                    continue
            
            # Sort by days to expiry
            expiry_list.sort(key=lambda x: x.days_to_expiry)
            
            self.available_expiries = expiry_list
            
            logger.info(f"Fetched {len(expiry_list)} available expiries for {underlying}")
            for exp in expiry_list[:5]:  # Log first 5
                logger.info(f"  Expiry: {exp.expiry_date} ({exp.expiry_type.value}, {exp.days_to_expiry} days)")
            
            return expiry_list
        
        except AttributeError as e:
            logger.warning(f"OpenAlgo API method not available: {e}")
            # Return default expiries when API method not available
            return self._get_default_expiries()
        except Exception as e:
            logger.error(f"Error fetching expiries: {e}")
            # Return default expiries on error
            return self._get_default_expiries()
    
    def _get_default_expiries(self) -> List[ExpiryInfo]:
        """
        Get default weekly expiries (next 4 Tuesdays)
        NIFTY weekly options expire every TUESDAY
        Auto-detects next available expiry dates
        
        Returns:
            List of ExpiryInfo objects for upcoming weekly expiries
        """
        today = datetime.now().date()
        current_time = datetime.now().time()
        weekday = today.weekday()  # 0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, 5=Saturday, 6=Sunday
        
        # Calculate days to next Tuesday (weekday=1)
        if weekday < 1:
            # Monday: Use tomorrow (Tuesday)
            days_to_next_tuesday = 1 - weekday
        elif weekday == 1:
            # Tuesday: If before 15:30, use today; otherwise next week
            if current_time.hour < 15 or (current_time.hour == 15 and current_time.minute < 30):
                days_to_next_tuesday = 0  # Today's expiry (still valid)
            else:
                days_to_next_tuesday = 7  # Next Tuesday
        else:
            # Wednesday-Sunday: Use next Tuesday
            days_to_next_tuesday = (7 - weekday + 1) % 7
            if days_to_next_tuesday == 0:
                days_to_next_tuesday = 7
        
        # Generate next 4 weekly expiries (Tuesdays)
        expiry_list = []
        for week in range(4):
            expiry_date = today + timedelta(days=days_to_next_tuesday + (week * 7))
            days_to_exp = (expiry_date - today).days
            
            # Verify it's actually Tuesday
            if expiry_date.weekday() != 1:
                logger.error(f"Expiry calculation error: {expiry_date} is not Tuesday!")
                continue
            
            expiry_list.append(ExpiryInfo(
                expiry_date=expiry_date.strftime('%d%b%y').upper(),
                expiry_type=ExpiryType.WEEKLY,
                days_to_expiry=days_to_exp
            ))
        
        if not expiry_list:
            logger.error("Failed to calculate default expiries!")
            return []
        
        logger.info(f"Auto-detected weekly expiries (NIFTY Tuesdays):")
        for i, exp in enumerate(expiry_list):
            exp_date = today + timedelta(days=exp.days_to_expiry)
            logger.info(f"  Week {i+1}: {exp.expiry_date} - {exp_date.strftime('%A, %d %B %Y')} ({exp.days_to_expiry} days)")
        
        self.available_expiries = expiry_list
        return expiry_list
    
    def select_nearest_weekly_expiry(self) -> Optional[ExpiryInfo]:
        """
        Select nearest weekly expiry (default for ANGEL-X scalping)
        
        Returns:
            ExpiryInfo object or None if not found
        """
        if not self.available_expiries:
            logger.warning("No available expiries to select from, fetching...")
            self.fetch_available_expiries(self.selected_underlying)
        
        if not self.available_expiries:
            logger.error("Still no available expiries after fetch attempt")
            return None
        
        # Find nearest weekly expiry
        for expiry in self.available_expiries:
            if expiry.expiry_type == ExpiryType.WEEKLY and expiry.days_to_expiry >= 0:
                self.current_expiry = expiry
                logger.info(f"Selected expiry: {expiry.expiry_date} ({expiry.days_to_expiry} days to expiry)")
                return expiry
        
        logger.warning("No suitable weekly expiry found, using first available")
        if self.available_expiries:
            self.current_expiry = self.available_expiries[0]
            return self.current_expiry
        
        return None
    
    def get_current_expiry(self) -> Optional[ExpiryInfo]:
        """Get currently selected expiry"""
        return self.current_expiry
    
    def is_expiry_day(self) -> bool:
        """Check if today is expiry day"""
        if not self.current_expiry:
            return False
        return self.current_expiry.is_last_day
    
    def is_expiry_week(self) -> bool:
        """Check if we're in expiry week"""
        if not self.current_expiry:
            return False
        return self.current_expiry.is_expiry_week
    
    def get_days_to_expiry(self) -> int:
        """Get days remaining to expiry"""
        if not self.current_expiry:
            return -1
        return self.current_expiry.days_to_expiry
    
    def apply_expiry_rules(self) -> Dict:
        """
        Get expiry-adjusted trading rules
        
        Returns:
            Dict with adjusted parameters based on expiry proximity
        """
        if not self.current_expiry:
            return config.__dict__.copy()
        
        days_left = self.current_expiry.days_to_expiry
        
        adjusted_rules = {
            'max_position_size_factor': 1.0,
            'risk_percent': config.RISK_PER_TRADE_OPTIMAL,  # Already in percentage form (e.g., 1)
            'hard_sl_percent': config.HARD_SL_PERCENT_MIN,  # Already in percentage form (e.g., 5)
            'min_time_in_trade': 0,
            'max_time_in_trade': 3600,
            'entry_frequency_factor': 1.0,
            'gamma_exit_sensitivity': 1.0,
        }
        
        if self.is_expiry_day():
            logger.warning("*** EXPIRY DAY ***")
            adjusted_rules = {
                'max_position_size_factor': 0.3,  # 30% of normal
                'risk_percent': 0.5,  # 0.5% risk only
                'hard_sl_percent': 3.0,  # 3% only
                'min_time_in_trade': 20,  # Exit if profitable after 20s
                'max_time_in_trade': 300,  # Max 5 min
                'entry_frequency_factor': 0.2,  # Reduce entries
                'gamma_exit_sensitivity': 2.0,  # Exit faster on gamma weakness
            }
        elif days_left <= 1:
            logger.warning("*** LAST TRADING DAY BEFORE EXPIRY ***")
            adjusted_rules = {
                'max_position_size_factor': 0.5,
                'risk_percent': 1.0,  # 1% risk
                'hard_sl_percent': 4.0,
                'min_time_in_trade': 30,
                'max_time_in_trade': 600,  # Max 10 min
                'entry_frequency_factor': 0.5,
                'gamma_exit_sensitivity': 1.5,
            }
        elif days_left <= 3:
            logger.info("Expiry week: Adjusting rules for lower volatility")
            adjusted_rules = {
                'max_position_size_factor': 0.7,
                'risk_percent': 1.5,  # 1.5% risk
                'hard_sl_percent': 5.0,
                'min_time_in_trade': 30,
                'max_time_in_trade': 900,  # 15 min
                'entry_frequency_factor': 0.8,
                'gamma_exit_sensitivity': 1.2,
            }
        
        logger.info(
            f"Expiry rules applied ({days_left} days): "
            f"Position size: {adjusted_rules['max_position_size_factor']*100:.0f}%, "
            f"Risk: {adjusted_rules['risk_percent']:.2f}%, "
            f"SL: {adjusted_rules['hard_sl_percent']:.1f}%, "
            f"Max duration: {adjusted_rules['max_time_in_trade']}s"
        )
        
        return adjusted_rules
    
    def get_expiry_statistics(self) -> Dict:
        """Get expiry statistics for reporting"""
        if not self.current_expiry:
            return {'error': 'No expiry selected'}
        
        exp = self.current_expiry
        
        return {
            'selected_expiry': exp.expiry_date,
            'expiry_type': exp.expiry_type.value,
            'days_to_expiry': exp.days_to_expiry,
            'is_expiry_day': exp.is_expiry_day,
            'is_expiry_week': exp.is_expiry_week,
            'trading_rules_applied': 'expiry_day' if exp.is_last_day else 'expiry_week' if exp.is_expiry_week else 'normal'
        }
    
    def refresh_expiry_chain(self, underlying: str) -> bool:
        """
        Refresh expiry list and select nearest weekly
        
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Refreshing expiry chain for {underlying}...")
        
        expiries = self.fetch_available_expiries(underlying)
        if not expiries:
            logger.error("Failed to fetch expiries")
            return False
        
        selected = self.select_nearest_weekly_expiry()
        if not selected:
            logger.error("Failed to select expiry")
            return False
        
        return True
    
    def get_option_symbol(
        self,
        strike: int,
        option_type: str,
        underlying: str = None
    ) -> str:
        """
        Build option symbol for OpenAlgo order
        
        Args:
            strike: Strike price
            option_type: CE or PE
            underlying: NIFTY or BANKNIFTY (defaults to current underlying)
        
        Returns:
            Option symbol string (e.g., "NIFTY18800CE30DEC2025")
        """
        if underlying is None:
            underlying = self.selected_underlying
        
        if not self.current_expiry:
            logger.warning("No expiry selected, cannot build symbol")
            return ""
        
        # Format: UNDERLYING + STRIKE + TYPE + EXPIRYDATE
        # Example: NIFTY18800CE30DEC2025
        
        symbol = f"{underlying}{strike}{option_type}{self.current_expiry.expiry_date}"
        logger.log_order({'type': 'SYMBOL_BUILT_MANUAL', 'symbol': symbol})
        return symbol

    def get_option_symbol_by_offset(
        self,
        underlying: str,
        expiry_date: str,
        offset: str,
        option_type: str
    ) -> Optional[str]:
        """Resolve option symbol using OpenAlgo `optionsymbol` via OrderManager."""
        try:
            resp = self._order_manager.resolve_option_symbol(
                underlying=underlying,
                expiry_date=expiry_date,
                offset=offset,
                option_type=option_type
            )
            if resp and resp.get('status') == 'success':
                symbol = resp.get('symbol')
                logger.log_order({'type': 'SYMBOL_RESOLVED', 'symbol': symbol, 'offset': offset, 'expiry_date': expiry_date})
                return symbol
            logger.log_order({'type': 'SYMBOL_RESOLVE_FAILED', 'response': resp})
            return None
        except Exception as e:
            logger.error(f"Error resolving symbol by offset: {e}")
            return None
    
    def build_order_symbol(self, strike: int, option_type: str) -> str:
        """
        Build complete option symbol for order placement
        
        Args:
            strike: Strike price
            option_type: CE or PE
        
        Returns:
            Complete symbol string for OpenAlgo
        """
        return self.get_option_symbol(strike, option_type)
