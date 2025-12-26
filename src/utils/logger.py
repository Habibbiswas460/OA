"""
Logging module for strategy
Handles all logging, debugging, and audit trail
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from config import config


class StrategyLogger:
    """Centralized logging system for the trading strategy"""
    
    _instances = {}
    
    def __init__(self, name="StrategyLogger"):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, config.LOG_LEVEL))
        
        # Prevent duplicate handlers
        if not self.logger.handlers:
            self._setup_handlers()
    
    @classmethod
    def get_logger(cls, name="StrategyLogger"):
        """Get or create logger instance"""
        if name not in cls._instances:
            cls._instances[name] = cls(name)
        inst = cls._instances[name]
        lg = inst.logger
        # Attach proxy methods for custom logging helpers if missing
        if not hasattr(lg, 'log_order'):
            lg.log_order = lambda order_data, _inst=inst: _inst.log_order(order_data)
        if not hasattr(lg, 'log_trade'):
            lg.log_trade = lambda trade_data, _inst=inst: _inst.log_trade(trade_data)
        if not hasattr(lg, 'log_signal'):
            lg.log_signal = lambda signal_data, _inst=inst: _inst.log_signal(signal_data)
        if not hasattr(lg, 'log_market_data'):
            lg.log_market_data = lambda data, _inst=inst: _inst.log_market_data(data)
        if not hasattr(lg, 'log_risk_event'):
            lg.log_risk_event = lambda event, _inst=inst: _inst.log_risk_event(event)
        if not hasattr(lg, 'log_position'):
            lg.log_position = lambda position_data, _inst=inst: _inst.log_position(position_data)
        if not hasattr(lg, 'log_pnl'):
            lg.log_pnl = lambda pnl_data, _inst=inst: _inst.log_pnl(pnl_data)
        return lg
    
    def _setup_handlers(self):
        """Setup console and file handlers"""
        formatter = logging.Formatter(config.LOG_FORMAT)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # File handler
        if config.LOG_TO_FILE:
            log_dir = Path(config.LOG_DIR)
            log_dir.mkdir(exist_ok=True)
            
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = log_dir / f"strategy_{today}.log"
            
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(getattr(logging, config.LOG_LEVEL))
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            
            # Separate file for trades
            trade_log_file = log_dir / f"trades_{today}.log"
            self.trade_handler = logging.FileHandler(trade_log_file)
            self.trade_handler.setLevel(logging.INFO)
            self.trade_handler.setFormatter(formatter)
    
    def debug(self, message):
        """Log debug message"""
        self.logger.debug(message)
    
    def info(self, message):
        """Log info message"""
        self.logger.info(message)
    
    def warning(self, message):
        """Log warning message"""
        self.logger.warning(message)
    
    def error(self, message):
        """Log error message"""
        self.logger.error(message)
    
    def critical(self, message):
        """Log critical message"""
        self.logger.critical(message)
    
    def log_trade(self, trade_data):
        """Log trade-specific information"""
        if config.LOG_TO_FILE and hasattr(self, 'trade_handler'):
            trade_logger = logging.getLogger(f"{self.name}.trades")
            trade_logger.addHandler(self.trade_handler)
            trade_logger.setLevel(logging.INFO)
            
            msg = f"TRADE | {trade_data}"
            trade_logger.info(msg)
    
    def log_order(self, order_data):
        """Log order-specific information"""
        self.info(f"ORDER | {order_data}")
    
    def log_signal(self, signal_data):
        """Log trading signal"""
        self.info(f"SIGNAL | {signal_data}")
    
    def log_market_data(self, data):
        """Log market data updates"""
        self.debug(f"MARKET | {data}")
    
    def log_risk_event(self, event):
        """Log risk management events"""
        self.warning(f"RISK | {event}")
    
    def log_position(self, position_data):
        """Log position updates"""
        self.info(f"POSITION | {position_data}")
    
    def log_pnl(self, pnl_data):
        """Log P&L updates"""
        self.info(f"PNL | {pnl_data}")


# Global logger instance
logger = StrategyLogger()
