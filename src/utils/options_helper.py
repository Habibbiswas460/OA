"""
Options Helper Module
Handles options-specific operations using OpenAlgo:
- Options orders (ATM, ITM, OTM)
- Options multi-leg orders (Iron Condor, Spreads)
- Option chain data
- Options Greeks
- Synthetic futures
- Option symbol lookup
"""

from openalgo import api
from config import config
from src.utils.logger import StrategyLogger
logger = StrategyLogger.get_logger(__name__)


class OptionsHelper:
    """
    Options trading helper using OpenAlgo
    """
    
    def __init__(self):
        self.client = api(
            api_key=config.OPENALGO_API_KEY,
            host=config.OPENALGO_HOST,
            ws_url=config.OPENALGO_WS_URL
        )
        
        self.strategy = config.STRATEGY_NAME
        
        logger.info("OptionsHelper initialized")

    def compute_offset(self, underlying: str, expiry_date: str, strike: float, option_type: str, exchange: str = None) -> str:
        """Compute ITM/OTM/ATM offset label relative to ATM strike."""
        if exchange is None:
            exchange = config.UNDERLYING_EXCHANGE
        atm = self.get_atm_strike(underlying, expiry_date, exchange)
        if not atm:
            logger.warning("ATM strike not available; defaulting to ATM")
            return "ATM"
        try:
            diff = float(strike) - float(atm)
            step = int(round(abs(diff) / 50))  # NIFTY strikes in 50 increments
            if step == 0:
                return "ATM"
            if option_type.upper() == "CE":
                # CE: strike below ATM is ITM, above ATM is OTM
                return ("ITM" + str(step)) if diff < 0 else ("OTM" + str(step))
            else:
                # PE: strike above ATM is ITM, below ATM is OTM
                return ("ITM" + str(step)) if diff > 0 else ("OTM" + str(step))
        except Exception as e:
            logger.error(f"Error computing offset: {e}")
            return "ATM"
    
    def place_option_order(self, underlying, expiry_date, offset, option_type, 
                          action, quantity, price_type="MARKET", product="NRML", 
                          exchange=None, split_size=0):
        """
        Place options order (ATM, ITM, OTM)
        
        Args:
            underlying: Underlying symbol (NIFTY, BANKNIFTY, etc.)
            expiry_date: Expiry in format DDMMMYY (e.g., 30DEC25)
            offset: ATM, ITM1-10, OTM1-10
            option_type: CE or PE
            action: BUY or SELL
            quantity: Lot quantity
            price_type: MARKET or LIMIT
            product: MIS or NRML
            exchange: Underlying exchange (defaults to UNDERLYING_EXCHANGE)
            split_size: Auto-split size (0 = no split)
        
        Returns:
            dict: Order response with symbol and orderid
        """
        try:
            if exchange is None:
                exchange = config.UNDERLYING_EXCHANGE
            
            response = self.client.optionsorder(
                strategy=self.strategy,
                underlying=underlying,
                exchange=exchange,
                expiry_date=expiry_date,
                offset=offset,
                option_type=option_type,
                action=action,
                quantity=quantity,
                pricetype=price_type,
                product=product,
                splitsize=split_size
            )
            
            if response.get('status') == 'success':
                logger.log_order({
                    'action': 'OPTIONS_ORDER',
                    'orderid': response.get('orderid'),
                    'symbol': response.get('symbol'),
                    'offset': offset,
                    'option_type': option_type
                })
            else:
                logger.error(f"Options order failed: {response}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error placing options order: {e}")
            return None
    
    def place_multi_leg_order(self, underlying, legs, exchange=None, expiry_date=None):
        """
        Place multi-leg options order (Iron Condor, Spreads, Straddle, Strangle)
        
        Args:
            underlying: Underlying symbol
            legs: List of leg dicts, each with:
                  - offset: ATM, ITM1, OTM2, etc.
                  - option_type: CE or PE
                  - action: BUY or SELL
                  - quantity: Lot quantity
                  - expiry_date: (optional, for different expiries)
            exchange: Underlying exchange
            expiry_date: Common expiry (if legs don't specify)
        
        Returns:
            dict: Multi-order response with results for each leg
        
        Example legs for Iron Condor:
            [
                {"offset": "OTM6", "option_type": "CE", "action": "BUY", "quantity": 75},
                {"offset": "OTM6", "option_type": "PE", "action": "BUY", "quantity": 75},
                {"offset": "OTM4", "option_type": "CE", "action": "SELL", "quantity": 75},
                {"offset": "OTM4", "option_type": "PE", "action": "SELL", "quantity": 75}
            ]
        """
        try:
            if exchange is None:
                exchange = config.UNDERLYING_EXCHANGE
            
            # Build kwargs
            kwargs = {
                'strategy': self.strategy,
                'underlying': underlying,
                'exchange': exchange,
                'legs': legs
            }
            
            # Add common expiry if specified
            if expiry_date:
                kwargs['expiry_date'] = expiry_date
            
            response = self.client.optionsmultiorder(**kwargs)
            
            if response.get('status') == 'success':
                logger.info(f"Multi-leg order placed: {len(response.get('results', []))} legs")
            else:
                logger.error(f"Multi-leg order failed: {response}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error placing multi-leg order: {e}")
            return None
    
    def get_option_chain(self, underlying, expiry_date, exchange=None, strike_count=None):
        """
        Get option chain data
        
        Args:
            underlying: Underlying symbol
            expiry_date: Expiry in DDMMMYY format
            exchange: Underlying exchange
            strike_count: Number of strikes around ATM (None = full chain)
        
        Returns:
            dict: Option chain with CE/PE data for each strike
        """
        try:
            if exchange is None:
                exchange = config.UNDERLYING_EXCHANGE
            
            kwargs = {
                'underlying': underlying,
                'exchange': exchange,
                'expiry_date': expiry_date
            }
            
            if strike_count is not None:
                kwargs['strike_count'] = strike_count
            
            response = self.client.optionchain(**kwargs)
            
            if response.get('status') == 'success':
                return response
            else:
                logger.error(f"Failed to get option chain: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting option chain: {e}")
            return None
    
    def get_option_greeks(self, symbol, exchange="NFO", interest_rate=0.0, 
                         underlying_symbol=None, underlying_exchange=None):
        """
        Calculate option Greeks (Delta, Gamma, Theta, Vega, Rho)
        
        Args:
            symbol: Option symbol
            exchange: Option exchange (NFO)
            interest_rate: Risk-free interest rate
            underlying_symbol: Underlying symbol
            underlying_exchange: Underlying exchange
        
        Returns:
            dict: Greeks data with delta, gamma, theta, vega, rho, IV
        """
        try:
            kwargs = {
                'symbol': symbol,
                'exchange': exchange,
                'interest_rate': interest_rate
            }
            
            if underlying_symbol:
                kwargs['underlying_symbol'] = underlying_symbol
            if underlying_exchange:
                kwargs['underlying_exchange'] = underlying_exchange
            
            response = self.client.optiongreeks(**kwargs)
            
            if response.get('status') == 'success':
                return response
            else:
                logger.error(f"Failed to get option Greeks: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting option Greeks: {e}")
            return None
    
    def get_option_symbol(self, underlying, expiry_date, offset, option_type, 
                         exchange=None):
        """
        Get option symbol from offset
        
        Args:
            underlying: Underlying symbol
            expiry_date: Expiry in DDMMMYY format
            offset: ATM, ITM1-10, OTM1-10
            option_type: CE or PE
            exchange: Underlying exchange
        
        Returns:
            dict: Symbol info with symbol, lotsize, freeze_qty, etc.
        """
        try:
            if exchange is None:
                exchange = config.UNDERLYING_EXCHANGE
            
            response = self.client.optionsymbol(
                underlying=underlying,
                exchange=exchange,
                expiry_date=expiry_date,
                offset=offset,
                option_type=option_type
            )
            
            if response.get('status') == 'success':
                return response
            else:
                logger.error(f"Failed to get option symbol: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting option symbol: {e}")
            return None
    
    def get_synthetic_future(self, underlying, expiry_date, exchange=None):
        """
        Calculate synthetic future price from options
        
        Args:
            underlying: Underlying symbol
            expiry_date: Expiry in DDMMMYY format
            exchange: Underlying exchange
        
        Returns:
            dict: Synthetic future price and ATM strike
        """
        try:
            if exchange is None:
                exchange = config.UNDERLYING_EXCHANGE
            
            response = self.client.syntheticfuture(
                underlying=underlying,
                exchange=exchange,
                expiry_date=expiry_date
            )
            
            if response.get('status') == 'success':
                return response
            else:
                logger.error(f"Failed to get synthetic future: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting synthetic future: {e}")
            return None
    
    def get_expiry_dates(self, symbol, exchange="NFO", instrumenttype="options"):
        """
        Get available expiry dates for a symbol
        
        Args:
            symbol: Symbol (NIFTY, BANKNIFTY, etc.)
            exchange: Exchange (NFO)
            instrumenttype: options or futures
        
        Returns:
            list: List of expiry dates
        """
        try:
            response = self.client.expiry(
                symbol=symbol,
                exchange=exchange,
                instrumenttype=instrumenttype
            )
            
            if response.get('status') == 'success':
                return response.get('data', [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting expiry dates: {e}")
            return []
    
    def calculate_margin_required(self, positions):
        """
        Calculate margin requirement for positions
        
        Args:
            positions: List of position dicts with symbol, exchange, action, etc.
        
        Returns:
            dict: Margin details with span and exposure
        """
        try:
            response = self.client.margin(positions=positions)
            
            if response.get('status') == 'success':
                return response.get('data')
            else:
                logger.error(f"Failed to calculate margin: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error calculating margin: {e}")
            return None
    
    def get_atm_strike(self, underlying, expiry_date, exchange=None):
        """
        Get ATM strike price for underlying
        
        Args:
            underlying: Underlying symbol
            expiry_date: Expiry date
            exchange: Underlying exchange
        
        Returns:
            float: ATM strike price
        """
        try:
            chain = self.get_option_chain(underlying, expiry_date, exchange, strike_count=1)
            
            if chain and chain.get('status') == 'success':
                return chain.get('atm_strike')
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting ATM strike: {e}")
            return None
