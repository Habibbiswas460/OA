"""
ANGEL-X Order Manager
OpenAlgo API integration with execution safeguards
Optimized for local network with retry logic and timeout handling
"""

import logging
import time
from enum import Enum
from typing import Optional
try:
    from openalgo import api
except ImportError:
    api = None
from config import config
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)


class OrderAction(Enum):
    """Order action"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class ProductType(Enum):
    """Product type"""
    MIS = "MIS"
    NRML = "NRML"


class OrderManager:
    """
    ANGEL-X Order Manager
    Interfaces with OpenAlgo API for order placement and management
    With retry logic and timeout handling for local network resilience
    """
    
    def __init__(self):
        """Initialize order manager"""
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
                logger.info(f"OrderManager initialized with OpenAlgo API")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAlgo client: {e}")
                self.client = None
        
        self.active_orders = {}
        self.order_counter = 0

    def _simulate_response(self, payload: dict) -> dict:
        """Simulate an order response in PAPER_TRADING mode"""
        import random
        sim = {
            'status': 'success',
            'orderid': f"PAPER_{int(time.time())}_{random.randint(1000,9999)}"
        }
        sim.update(payload)
        return sim
    
    def _api_call_with_retry(self, api_func, *args, **kwargs):
        """
        Execute API call with retry logic and timeout handling
        
        Args:
            api_func: The API function to call
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            API response or None if all retries fail
        """
        retry_count = 0
        max_retries = config.API_RETRY_ATTEMPTS
        
        while retry_count < max_retries:
            try:
                # Add timeout to kwargs if not already present
                if 'timeout' not in kwargs:
                    kwargs['timeout'] = config.API_REQUEST_TIMEOUT
                
                result = api_func(*args, **kwargs)
                return result
                
            except TimeoutError:
                retry_count += 1
                logger.warning(f"API call timeout (attempt {retry_count}/{max_retries})")
                if retry_count < max_retries:
                    time.sleep(config.API_RETRY_DELAY)
                    
            except ConnectionError as e:
                retry_count += 1
                logger.warning(f"Connection error: {e} (attempt {retry_count}/{max_retries})")
                if retry_count < max_retries:
                    time.sleep(config.API_RETRY_DELAY)
                    
            except Exception as e:
                retry_count += 1
                logger.error(f"API error: {e} (attempt {retry_count}/{max_retries})")
                if retry_count < max_retries:
                    time.sleep(config.API_RETRY_DELAY)
        
        logger.error(f"API call failed after {max_retries} attempts")
        return None
    
    def place_order(
        self,
        exchange: str,
        symbol: str,
        action: OrderAction,
        order_type: OrderType,
        price: float,
        quantity: int,
        product: ProductType = ProductType.MIS
    ) -> Optional[dict]:
        """
        Place an order with retry logic
        Supports both paper trading (simulated) and live trading
        
        Args:
            exchange: NSE, BSE, MCX, NCDEX
            symbol: Stock/option symbol
            action: BUY or SELL
            order_type: MARKET or LIMIT
            price: Order price (for LIMIT orders)
            quantity: Number of units
            product: MIS or NRML
        
        Returns:
            Order response dict or None if failed
        """
        
        if not self.client and not config.PAPER_TRADING:
            logger.error("OrderManager not initialized with API client")
            return None
        
        try:
            # Pre-execution checks
            if quantity <= 0:
                logger.warning(f"Invalid quantity: {quantity}")
                return None
            
            if order_type == OrderType.LIMIT and price <= 0:
                logger.warning(f"Invalid price for LIMIT order: {price}")
                return None
            
            # PAPER TRADING MODE - Simulate order locally
            if config.PAPER_TRADING:
                simulated_order = self._simulate_response({
                    'exchange': exchange,
                    'symbol': symbol,
                    'action': action.value,
                    'price': price,
                    'quantity': quantity,
                    'product': product.value,
                    'order_type': order_type.value,
                    'message': 'Paper order simulated locally',
                    'timestamp': time.time()
                })
                order_id = simulated_order['orderid']
                self.active_orders[order_id] = simulated_order
                logger.info(
                    f"📄 PAPER ORDER: {action.value} {quantity} {symbol} @ ₹{price:.2f} | "
                    f"Order ID: {order_id}"
                )
                return simulated_order
                logger.warning(f"Invalid price for LIMIT order: {price}")
                return None
            
            # Prepare order parameters
            order_params = {
                'exchange': exchange,
                'symbol': symbol,
                'action': action.value,
                'price_type': order_type.value,
                'price': price if order_type == OrderType.LIMIT else 0,
                'quantity': quantity,
                'product': product.value,
                'order_type': 'REGULAR',
                'strategy': config.STRATEGY_NAME
            }
            
            # Place order via OpenAlgo
            response = self.client.placeorder(**order_params)
            
            if response and 'status' in response:
                order_id = response.get('orderid')
                self.active_orders[order_id] = response
                
                logger.info(
                    f"Order placed: {action.value} {quantity} {symbol} @ ₹{price:.2f} | "
                    f"Order ID: {order_id}"
                )
                
                return response
            else:
                logger.error(f"Order placement failed: {response}")
                return None
        
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None

    def resolve_option_symbol(self, underlying: str, expiry_date: str, offset: str, option_type: str) -> Optional[dict]:
        """Resolve an option symbol via OpenAlgo optionsymbol"""
        try:
            if config.PAPER_TRADING:
                # Simulate symbol resolution
                return {
                    'status': 'success',
                    'symbol': f"{underlying}{expiry_date}{offset}{option_type}",
                    'exchange': 'NFO',
                    'lotsize': config.MINIMUM_LOT_SIZE
                }
            if not self.client:
                return None
            resp = self._api_call_with_retry(
                self.client.optionsymbol,
                underlying=underlying,
                exchange=config.DEFAULT_UNDERLYING_EXCHANGE,
                expiry_date=expiry_date,
                offset=offset,
                option_type=option_type
            )
            return resp
        except Exception as e:
            logger.error(f"Error resolving option symbol: {e}")
            return None

    def place_option_order(
        self,
        strategy: str,
        underlying: str,
        expiry_date: str,
        offset: str,
        option_type: str,
        action: str,
        quantity: int,
        pricetype: Optional[str] = None,
        product: Optional[str] = None,
        splitsize: int = 0
    ) -> Optional[dict]:
        """Place an options order using OpenAlgo optionsorder (ATM/ITM/OTM offset)."""
        try:
            pricetype = pricetype or config.DEFAULT_OPTION_PRICE_TYPE
            product = product or config.DEFAULT_OPTION_PRODUCT
            payload = {
                'strategy': strategy,
                'underlying': underlying,
                'exchange': config.DEFAULT_UNDERLYING_EXCHANGE,
                'expiry_date': expiry_date,
                'offset': offset,
                'option_type': option_type,
                'action': action,
                'quantity': quantity,
                'pricetype': pricetype,
                'product': product,
                'splitsize': splitsize
            }
            logger.log_order({'type': 'OPTIONSORDER_INTENT', **payload})
            if config.PAPER_TRADING:
                sim = self._simulate_response(payload)
                self.active_orders[sim['orderid']] = sim
                logger.info(f"📄 PAPER OPTIONS ORDER: {payload}")
                return sim
            if not self.client:
                logger.error("OpenAlgo client not initialized")
                return None
            resp = self._api_call_with_retry(self.client.optionsorder, **payload)
            if resp and resp.get('status') == 'success':
                # Check if analyzer mode (paper trading)
                if resp.get('mode') == 'analyze':
                    logger.warning(f"⚠️ ANALYZER MODE: Order simulated, not live. Response: {resp}")
                    logger.log_order({'type': 'OPTIONSORDER_ANALYZER', 'response': resp})
                else:
                    logger.info(f"Options order placed: {resp}")
                    logger.log_order({'type': 'OPTIONSORDER_PLACED', 'response': resp})
                self.active_orders[resp.get('orderid')] = resp
                return resp
            logger.error(f"Options order failed: {resp}")
            logger.log_order({'type': 'OPTIONSORDER_REJECTED', 'response': resp})
            return None
        except Exception as e:
            logger.error(f"Error placing options order: {e}")
            return None

    def place_options_multi_order(
        self,
        strategy: str,
        underlying: str,
        legs: list,
        expiry_date: Optional[str] = None
    ) -> Optional[dict]:
        """Place multi-leg options order using optionsmultiorder."""
        try:
            payload = {
                'strategy': strategy,
                'underlying': underlying,
                'exchange': config.DEFAULT_UNDERLYING_EXCHANGE,
            }
            if expiry_date:
                payload['expiry_date'] = expiry_date
            payload['legs'] = legs
            logger.log_order({'type': 'MULTIORDER_INTENT', **payload})
            if config.PAPER_TRADING:
                sim = self._simulate_response(payload)
                logger.info(f"📄 PAPER OPTIONS MULTI ORDER: {payload}")
                logger.log_order({'type': 'MULTIORDER_PAPER', 'response': sim})
                return sim
            if not self.client:
                logger.error("OpenAlgo client not initialized")
                return None
            resp = self._api_call_with_retry(self.client.optionsmultiorder, **payload)
            if resp and resp.get('status') == 'success':
                # Check if analyzer mode (paper trading)
                if resp.get('mode') == 'analyze':
                    logger.warning(f"⚠️ ANALYZER MODE: Multi-order simulated, not live. Response: {resp}")
                    logger.log_order({'type': 'MULTIORDER_ANALYZER', 'response': resp})
                else:
                    logger.info(f"Options multi-order placed: {resp}")
                    logger.log_order({'type': 'MULTIORDER_PLACED', 'response': resp})
                return resp
            logger.error(f"Options multi-order failed: {resp}")
            logger.log_order({'type': 'MULTIORDER_REJECTED', 'response': resp})
            return None
        except Exception as e:
            logger.error(f"Error placing options multi-order: {e}")
            return None

    def place_basket_order(self, orders: list) -> Optional[dict]:
        """Place a basket of equity orders."""
        try:
            if config.PAPER_TRADING:
                sim = self._simulate_response({'orders': orders})
                logger.info(f"📄 PAPER BASKET ORDER: {orders}")
                return sim
            if not self.client:
                logger.error("OpenAlgo client not initialized")
                return None
            resp = self._api_call_with_retry(self.client.basketorder, orders=orders)
            if resp and resp.get('status') == 'success':
                logger.info(f"Basket order placed: {resp}")
                return resp
            logger.error(f"Basket order failed: {resp}")
            return None
        except Exception as e:
            logger.error(f"Error placing basket order: {e}")
            return None

    def place_split_order(
        self,
        symbol: str,
        exchange: str,
        action: str,
        quantity: int,
        splitsize: int,
        price_type: str,
        product: str
    ) -> Optional[dict]:
        """Place split order using OpenAlgo splitorder."""
        try:
            payload = {
                'symbol': symbol,
                'exchange': exchange,
                'action': action,
                'quantity': quantity,
                'splitsize': splitsize,
                'price_type': price_type,
                'product': product
            }
            if config.PAPER_TRADING:
                sim = self._simulate_response(payload)
                logger.info(f"📄 PAPER SPLIT ORDER: {payload}")
                return sim
            if not self.client:
                logger.error("OpenAlgo client not initialized")
                return None
            resp = self._api_call_with_retry(self.client.splitorder, **payload)
            if resp and resp.get('status') == 'success':
                logger.info(f"Split order placed: {resp}")
                return resp
            logger.error(f"Split order failed: {resp}")
            return None
        except Exception as e:
            logger.error(f"Error placing split order: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        if not self.client:
            return False
        
        try:
            response = self.client.cancelorder(order_id=order_id)
            if response:
                logger.info(f"Order cancelled: {order_id}")
                self.active_orders.pop(order_id, None)
                return True
            return False
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False
    
    def modify_order(
        self,
        order_id: str,
        new_price: float,
        new_quantity: int
    ) -> bool:
        """Modify an order"""
        if not self.client:
            return False
        
        try:
            response = self.client.modifyorder(
                order_id=order_id,
                price=new_price,
                quantity=new_quantity
            )
            if response:
                logger.info(f"Order modified: {order_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error modifying order: {e}")
            return False
    
    def get_order_status(self, order_id: str) -> Optional[dict]:
        """Get order status"""
        if not self.client:
            return None
        
        try:
            response = self.client.orderbook()
            if response:
                for order in response:
                    if order.get('orderid') == order_id:
                        return order
            return None
        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            return None
    
    def get_position(self, symbol: str) -> Optional[dict]:
        """Get current position"""
        if not self.client:
            return None
        
        try:
            response = self.client.positionbook()
            if response:
                for position in response:
                    if position.get('symbol') == symbol:
                        return position
            return None
        except Exception as e:
            logger.error(f"Error getting position: {e}")
            return None
    
    def close_position(self, symbol: str) -> bool:
        """Close entire position"""
        if not self.client:
            return False
        
        try:
            position = self.get_position(symbol)
            if not position:
                return False
            
            qty = position.get('netqty', 0)
            if qty == 0:
                return True
            
            action = OrderAction.SELL if qty > 0 else OrderAction.BUY
            
            response = self.place_order(
                exchange='NSE',
                symbol=symbol,
                action=action,
                order_type=OrderType.MARKET,
                price=0,
                quantity=abs(qty)
            )
            
            return response is not None
        
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False
    
    def get_all_orders(self) -> list:
        """Get all active orders"""
        if not self.client:
            return []
        
        try:
            return self.client.orderbook() or []
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return []
    
    def get_all_positions(self) -> list:
        """Get all positions"""
        if not self.client:
            return []
        
        try:
            return self.client.positionbook() or []
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
