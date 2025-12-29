#!/usr/bin/env python3
"""
OpenAlgo Execution Engine for ANGEL-X
Complete integration with OpenAlgo APIs for order execution and data fetching

Features:
1. Real-time Greeks & market data via API calls
2. Order execution (single-leg and multi-leg)
3. Position management and tracking
4. WebSocket streaming (LTP, quotes, depth)
5. Analyze mode for backtesting
"""

import time
import logging
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    from openalgo import api
except ImportError:
    api = None

from config import config
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)


class ExecutionMode(Enum):
    """Execution mode"""
    LIVE = "LIVE"
    ANALYZE = "ANALYZE"
    PAPER = "PAPER"


@dataclass
class GreeksSnapshot:
    """Greeks data snapshot"""
    symbol: str
    delta: float
    gamma: float
    theta: float
    vega: float
    iv: float
    ltp: float
    bid: float
    ask: float
    oi: int
    volume: int
    timestamp: datetime


@dataclass
class ExecutionResult:
    """Order execution result"""
    success: bool
    order_id: Optional[str] = None
    symbol: Optional[str] = None
    message: str = ""
    response: Optional[Dict] = None


class OpenAlgoExecutor:
    """
    OpenAlgo Execution Engine
    
    Manages:
    1. API connections
    2. Data fetching (Greeks, quotes, chains)
    3. Order execution
    4. Position tracking
    5. Streaming data
    """
    
    def __init__(self, mode: ExecutionMode = ExecutionMode.ANALYZE):
        """Initialize executor"""
        self.mode = mode
        self.client = None
        
        # Initialize OpenAlgo client
        self._init_client()
        
        # Stats
        self.total_orders = 0
        self.successful_orders = 0
        self.failed_orders = 0
        
        logger.info(f"✅ OpenAlgo Executor initialized in {mode.name} mode")
    
    def _init_client(self):
        """Initialize OpenAlgo API client"""
        if not api:
            logger.warning("OpenAlgo library not available")
            return
        
        try:
            self.client = api(
                api_key=config.OPENALGO_API_KEY,
                host=config.OPENALGO_HOST,
                ws_url=config.OPENALGO_WS_URL
            )
            logger.info(f"OpenAlgo client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAlgo client: {e}")
            self.client = None
    
    # ========================================================================
    # DATA FETCHING METHODS
    # ========================================================================
    
    def fetch_greeks(self, symbol: str, exchange: str = "NFO") -> Optional[GreeksSnapshot]:
        """
        Fetch Greeks data via optiongreeks API
        
        Args:
            symbol: Option symbol (e.g., "NIFTY30DEC2526000CE")
            exchange: NFO for options
        
        Returns:
            GreeksSnapshot with all Greeks data
        """
        try:
            if not self.client:
                logger.error("OpenAlgo client not available")
                return None
            
            response = self.client.optiongreeks(
                symbol=symbol,
                exchange=exchange,
                underlying_symbol=config.PRIMARY_UNDERLYING,
                underlying_exchange=config.UNDERLYING_EXCHANGE
            )
            
            if not response or response.get('status') != 'success':
                logger.error(f"Failed to fetch Greeks for {symbol}")
                return None
            
            data = response.get('data', {})
            greeks = data.get('greeks', {})
            quote = data.get('quote', {})
            
            snapshot = GreeksSnapshot(
                symbol=symbol,
                delta=greeks.get('delta', 0.0),
                gamma=greeks.get('gamma', 0.0),
                theta=greeks.get('theta', 0.0),
                vega=greeks.get('vega', 0.0),
                iv=greeks.get('implied_volatility', data.get('implied_volatility', 0.0)),
                ltp=quote.get('ltp', 0.0),
                bid=quote.get('bid', 0.0),
                ask=quote.get('ask', 0.0),
                oi=quote.get('oi', 0),
                volume=quote.get('volume', 0),
                timestamp=datetime.now()
            )
            
            logger.debug(f"Greeks fetched: {symbol} | Δ={snapshot.delta:.4f} Γ={snapshot.gamma:.6f} IV={snapshot.iv:.2f}%")
            return snapshot
            
        except Exception as e:
            logger.error(f"Exception fetching Greeks: {e}")
            return None
    
    def fetch_option_chain(self, underlying: str, expiry_date: str, 
                          strike_count: int = 5) -> Optional[Dict]:
        """
        Fetch option chain via optionchain API
        
        Args:
            underlying: NIFTY, BANKNIFTY
            expiry_date: DDMMMYY format
            strike_count: Number of strikes around ATM
        
        Returns:
            Option chain data with all strikes
        """
        try:
            if not self.client:
                return None
            
            response = self.client.optionchain(
                underlying=underlying,
                exchange=config.UNDERLYING_EXCHANGE,
                expiry_date=expiry_date,
                strike_count=strike_count
            )
            
            if response and response.get('status') == 'success':
                logger.info(f"Option chain fetched: {underlying} {expiry_date} | ATM: {response.get('atm_strike')}")
                return response
            else:
                logger.error(f"Failed to fetch option chain")
                return None
                
        except Exception as e:
            logger.error(f"Exception fetching option chain: {e}")
            return None
    
    def fetch_option_symbol(self, underlying: str, expiry_date: str,
                           offset: str, option_type: str) -> Optional[Dict]:
        """
        Resolve option symbol by offset via optionsymbol API
        
        Args:
            underlying: NIFTY
            expiry_date: 30DEC25
            offset: ATM, OTM1, ITM2, etc.
            option_type: CE or PE
        
        Returns:
            Dict with symbol, lotsize, etc.
        """
        try:
            if not self.client:
                return None
            
            response = self.client.optionsymbol(
                underlying=underlying,
                exchange=config.UNDERLYING_EXCHANGE,
                expiry_date=expiry_date,
                offset=offset,
                option_type=option_type
            )
            
            if response and response.get('status') == 'success':
                symbol = response.get('data', {}).get('symbol') or response.get('symbol')
                logger.debug(f"Symbol resolved: {symbol}")
                return response
            else:
                logger.error(f"Failed to resolve symbol")
                return None
                
        except Exception as e:
            logger.error(f"Exception resolving symbol: {e}")
            return None
    
    def fetch_quotes(self, symbol: str, exchange: str = "NSE") -> Optional[Dict]:
        """
        Fetch quotes via quotes API
        
        Returns:
            Quote data with LTP, bid, ask, volume, OI
        """
        try:
            if not self.client:
                return None
            
            response = self.client.quotes(symbol=symbol, exchange=exchange)
            
            if response and response.get('status') == 'success':
                return response.get('data', response)
            else:
                return None
                
        except Exception as e:
            logger.error(f"Exception fetching quotes: {e}")
            return None
    
    # ========================================================================
    # ORDER EXECUTION METHODS
    # ========================================================================
    
    def execute_option_order(self, underlying: str, expiry_date: str,
                            offset: str, option_type: str, action: str,
                            quantity: int, pricetype: str = "MARKET",
                            product: str = "NRML") -> ExecutionResult:
        """
        Execute single option order via optionsorder API
        
        Args:
            underlying: NIFTY
            expiry_date: 30DEC25
            offset: ATM, OTM1, etc.
            option_type: CE or PE
            action: BUY or SELL
            quantity: Lot quantity (75 for NIFTY)
            pricetype: MARKET or LIMIT
            product: NRML or MIS
        
        Returns:
            ExecutionResult with order details
        """
        try:
            logger.info(f"Executing order: {action} {quantity}x {offset} {option_type}")
            
            if not self.client:
                logger.error("OpenAlgo client not available")
                self.failed_orders += 1
                return ExecutionResult(success=False, message="Client not available")
            
            response = self.client.optionsorder(
                strategy=config.STRATEGY_NAME,
                underlying=underlying,
                exchange=config.UNDERLYING_EXCHANGE,
                expiry_date=expiry_date,
                offset=offset,
                option_type=option_type,
                action=action,
                quantity=quantity,
                pricetype=pricetype,
                product=product,
                splitsize=0
            )
            
            if not response or response.get('status') != 'success':
                logger.error(f"Order execution failed: {response}")
                self.failed_orders += 1
                self.total_orders += 1
                
                return ExecutionResult(
                    success=False,
                    message=response.get('message', 'Order failed') if isinstance(response, dict) else str(response),
                    response=response
                )
            
            order_id = response.get('orderid')
            symbol = response.get('symbol')
            
            logger.info(f"✅ Order executed: {order_id} | {symbol}")
            
            self.successful_orders += 1
            self.total_orders += 1
            
            return ExecutionResult(
                success=True,
                order_id=order_id,
                symbol=symbol,
                message="Order executed successfully",
                response=response
            )
            
        except Exception as e:
            logger.error(f"Exception executing order: {e}")
            self.failed_orders += 1
            self.total_orders += 1
            
            return ExecutionResult(success=False, message=str(e))
    
    def execute_multileg_order(self, underlying: str, expiry_date: str,
                              legs: List[Dict], strategy_name: str = None) -> ExecutionResult:
        """
        Execute multi-leg order via optionsmultiorder API
        
        Args:
            underlying: NIFTY
            expiry_date: 30DEC25
            legs: List of leg dicts
            strategy_name: Custom strategy name
        
        Returns:
            ExecutionResult
        """
        try:
            if not self.client:
                logger.error("OpenAlgo client not available")
                return ExecutionResult(success=False, message="Client not available")
            
            logger.info(f"Executing multi-leg order: {len(legs)} legs")
            
            response = self.client.optionsmultiorder(
                strategy=strategy_name or config.STRATEGY_NAME,
                underlying=underlying,
                exchange=config.UNDERLYING_EXCHANGE,
                expiry_date=expiry_date,
                legs=legs
            )
            
            if not response or response.get('status') != 'success':
                logger.error(f"Multi-leg order failed: {response}")
                self.failed_orders += 1
                
                return ExecutionResult(
                    success=False,
                    message=response.get('message', 'Multi-leg failed') if isinstance(response, dict) else str(response),
                    response=response
                )
            
            results = response.get('results', [])
            logger.info(f"✅ Multi-leg order executed: {len(results)} legs")
            
            self.successful_orders += len(results)
            self.total_orders += len(results)
            
            return ExecutionResult(
                success=True,
                message=f"All {len(results)} legs executed",
                response=response
            )
            
        except Exception as e:
            logger.error(f"Exception executing multi-leg order: {e}")
            self.failed_orders += 1
            
            return ExecutionResult(success=False, message=str(e))
    
    # ========================================================================
    # STATISTICS
    # ========================================================================
    
    def get_stats(self) -> Dict:
        """Get execution statistics"""
        total = self.total_orders
        success_rate = (self.successful_orders / total * 100) if total > 0 else 0
        
        return {
            'total_orders': self.total_orders,
            'successful': self.successful_orders,
            'failed': self.failed_orders,
            'success_rate': success_rate,
            'mode': self.mode.name
        }
    
    def print_summary(self):
        """Print execution summary"""
        stats = self.get_stats()
        
        logger.info("=" * 70)
        logger.info("OPENALGO EXECUTOR SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Mode: {stats['mode']}")
        logger.info(f"Total Orders: {stats['total_orders']}")
        logger.info(f"Successful: {stats['successful']} ✅")
        logger.info(f"Failed: {stats['failed']} ❌")
        logger.info(f"Success Rate: {stats['success_rate']:.1f}%")
        logger.info("=" * 70)


# Global executor instance
_executor = None


def get_executor(mode: ExecutionMode = None) -> OpenAlgoExecutor:
    """Get or create executor instance"""
    global _executor
    
    if _executor is None:
        if mode is None:
            if config.DEMO_MODE:
                mode = ExecutionMode.PAPER
            elif config.PAPER_TRADING:
                mode = ExecutionMode.ANALYZE
            else:
                mode = ExecutionMode.LIVE
        
        _executor = OpenAlgoExecutor(mode)
    
    return _executor
