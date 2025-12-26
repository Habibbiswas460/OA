"""
Market Data Module
Handles market data operations using OpenAlgo:
- Quotes (single and multiple)
- Market depth
- Historical data
- Intervals
- Search
"""

from openalgo import api
from config import config
from src.utils.logger import StrategyLogger
logger = StrategyLogger.get_logger(__name__)


class MarketData:
    """
    Market data handler using OpenAlgo
    """
    
    def __init__(self):
        self.client = api(
            api_key=config.OPENALGO_API_KEY,
            host=config.OPENALGO_HOST,
            ws_url=config.OPENALGO_WS_URL
        )
        
        logger.info("MarketData initialized")
    
    def get_quote(self, symbol, exchange=None):
        """
        Get quote for a single symbol
        
        Args:
            symbol: Trading symbol
            exchange: Exchange (defaults to config.EXCHANGE)
        
        Returns:
            dict: Quote data with open, high, low, ltp, etc.
        """
        try:
            if exchange is None:
                exchange = config.EXCHANGE
            
            response = self.client.quotes(symbol=symbol, exchange=exchange)
            
            if response.get('status') == 'success':
                return response.get('data')
            else:
                logger.error(f"Failed to get quote for {symbol}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting quote: {e}")
            return None
    
    def get_multi_quotes(self, symbols_list):
        """
        Get quotes for multiple symbols
        
        Args:
            symbols_list: List of dicts [{"symbol": "RELIANCE", "exchange": "NSE"}, ...]
        
        Returns:
            list: List of quote data
        """
        try:
            response = self.client.multiquotes(symbols=symbols_list)
            
            if response.get('status') == 'success':
                return response.get('results', [])
            else:
                logger.error("Failed to get multiple quotes")
                return []
                
        except Exception as e:
            logger.error(f"Error getting multiple quotes: {e}")
            return []
    
    def get_depth(self, symbol, exchange=None):
        """
        Get market depth for a symbol
        
        Args:
            symbol: Trading symbol
            exchange: Exchange
        
        Returns:
            dict: Market depth with bids and asks
        """
        try:
            if exchange is None:
                exchange = config.EXCHANGE
            
            response = self.client.depth(symbol=symbol, exchange=exchange)
            
            if response.get('status') == 'success':
                return response.get('data')
            else:
                logger.error(f"Failed to get depth for {symbol}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting depth: {e}")
            return None
    
    def get_history(self, symbol, interval, start_date, end_date, exchange=None):
        """
        Get historical candle data
        
        Args:
            symbol: Trading symbol
            interval: Candle interval (1m, 5m, 15m, 1h, D)
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            exchange: Exchange
        
        Returns:
            DataFrame: Historical data
        """
        try:
            if exchange is None:
                exchange = config.EXCHANGE
            
            response = self.client.history(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start_date=start_date,
                end_date=end_date
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            return None
    
    def get_intervals(self):
        """
        Get available intervals for historical data
        
        Returns:
            dict: Available intervals
        """
        try:
            response = self.client.intervals()
            
            if response.get('status') == 'success':
                return response.get('data')
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting intervals: {e}")
            return None
    
    def search_symbol(self, query, exchange=None):
        """
        Search for symbols
        
        Args:
            query: Search query string
            exchange: Exchange to search in
        
        Returns:
            list: List of matching symbols
        """
        try:
            if exchange is None:
                exchange = config.EXCHANGE
            
            response = self.client.search(query=query, exchange=exchange)
            
            if response.get('status') == 'success':
                return response.get('data', [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error searching symbols: {e}")
            return []
    
    def get_symbol_info(self, symbol, exchange=None):
        """
        Get detailed symbol information
        
        Args:
            symbol: Trading symbol
            exchange: Exchange
        
        Returns:
            dict: Symbol details (lotsize, tick_size, freeze_qty, etc.)
        """
        try:
            if exchange is None:
                exchange = config.EXCHANGE
            
            response = self.client.symbol(symbol=symbol, exchange=exchange)
            
            if response.get('status') == 'success':
                return response.get('data')
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting symbol info: {e}")
            return None
    
    def get_instruments(self, exchange=None):
        """
        Get all instruments for an exchange
        
        Args:
            exchange: Exchange
        
        Returns:
            DataFrame: All instruments
        """
        try:
            if exchange is None:
                exchange = config.EXCHANGE
            
            response = self.client.instruments(exchange=exchange)
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting instruments: {e}")
            return None
    
    def get_holidays(self, year=None):
        """
        Get market holidays
        
        Args:
            year: Year (defaults to current year)
        
        Returns:
            list: List of holidays
        """
        try:
            if year is None:
                from datetime import datetime
                year = datetime.now().year
            
            response = self.client.holidays(year=year)
            
            if response.get('status') == 'success':
                return response.get('data', [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting holidays: {e}")
            return []
    
    def get_timings(self, date=None):
        """
        Get market timings for a specific date
        
        Args:
            date: Date in YYYY-MM-DD format
        
        Returns:
            list: Trading timings for exchanges
        """
        try:
            if date is None:
                from datetime import datetime
                date = datetime.now().strftime("%Y-%m-%d")
            
            response = self.client.timings(date=date)
            
            if response.get('status') == 'success':
                return response.get('data', [])
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error getting timings: {e}")
            return []
