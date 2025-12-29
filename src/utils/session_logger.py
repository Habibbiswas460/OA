"""
Session Logger - Advanced logging with session tracking
Tracks complete trading sessions with detailed metrics and analysis
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import threading


class SessionLogger:
    """
    Advanced session-based logging system
    Tracks complete trading sessions with metrics, events, and analytics
    """
    
    def __init__(self, session_id: str = None):
        """
        Initialize session logger
        
        Args:
            session_id: Unique session identifier (auto-generated if None)
        """
        self.session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.session_start = datetime.now()
        
        # Create session directory
        self.session_dir = Path("sessions") / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        
        # Session data
        self.session_data = {
            'session_id': self.session_id,
            'start_time': self.session_start.isoformat(),
            'end_time': None,
            'status': 'ACTIVE',
            'mode': 'PAPER',  # PAPER or LIVE
            'events': [],
            'trades': [],
            'metrics': {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'total_pnl': 0,
                'max_drawdown': 0,
                'greeks_api_calls': 0,
                'cache_hit_rate': 0
            },
            'errors': [],
            'warnings': []
        }
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
        # Setup file handlers
        self._setup_file_logging()
        
        # Log session start
        self.log_event('SESSION_START', {
            'session_id': self.session_id,
            'timestamp': self.session_start.isoformat()
        })
    
    def _setup_file_logging(self):
        """Setup file-based logging for session"""
        # Main session log
        self.session_log_file = self.session_dir / "session.log"
        
        # Events log (JSON)
        self.events_log_file = self.session_dir / "events.jsonl"
        
        # Trades log (JSON)
        self.trades_log_file = self.session_dir / "trades.jsonl"
        
        # Errors log
        self.errors_log_file = self.session_dir / "errors.log"
        
        # Create logger
        self.logger = logging.getLogger(f"session_{self.session_id}")
        self.logger.setLevel(logging.DEBUG)
        
        # File handler
        fh = logging.FileHandler(self.session_log_file)
        fh.setLevel(logging.DEBUG)
        
        # Format
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        fh.setFormatter(formatter)
        
        self.logger.addHandler(fh)
    
    def log_event(self, event_type: str, data: Dict[str, Any]):
        """
        Log an event to the session
        
        Args:
            event_type: Type of event (e.g., TRADE_ENTRY, SIGNAL_DETECTED)
            data: Event data dictionary
        """
        with self.lock:
            event = {
                'timestamp': datetime.now().isoformat(),
                'type': event_type,
                'data': data
            }
            
            # Add to session data
            self.session_data['events'].append(event)
            
            # Write to events log (JSONL format)
            with open(self.events_log_file, 'a') as f:
                f.write(json.dumps(event) + '\n')
            
            # Log to session log
            self.logger.info(f"{event_type}: {json.dumps(data)}")
    
    def log_trade(self, trade_data: Dict[str, Any]):
        """
        Log a trade to the session
        
        Args:
            trade_data: Trade information dictionary
        """
        with self.lock:
            trade = {
                'timestamp': datetime.now().isoformat(),
                **trade_data
            }
            
            # Add to session data
            self.session_data['trades'].append(trade)
            
            # Update metrics
            self.session_data['metrics']['total_trades'] += 1
            
            if 'pnl' in trade_data:
                pnl = float(trade_data['pnl'])
                self.session_data['metrics']['total_pnl'] += pnl
                
                if pnl > 0:
                    self.session_data['metrics']['wins'] += 1
                elif pnl < 0:
                    self.session_data['metrics']['losses'] += 1
            
            # Write to trades log (JSONL format)
            with open(self.trades_log_file, 'a') as f:
                f.write(json.dumps(trade) + '\n')
            
            # Log to session log
            self.logger.info(f"TRADE: {json.dumps(trade_data)}")
    
    def log_error(self, error_type: str, error_msg: str, details: Dict = None):
        """
        Log an error to the session
        
        Args:
            error_type: Type of error
            error_msg: Error message
            details: Additional error details
        """
        with self.lock:
            error = {
                'timestamp': datetime.now().isoformat(),
                'type': error_type,
                'message': error_msg,
                'details': details or {}
            }
            
            # Add to session data
            self.session_data['errors'].append(error)
            
            # Write to errors log
            with open(self.errors_log_file, 'a') as f:
                f.write(f"{error['timestamp']} | {error_type}: {error_msg}\n")
                if details:
                    f.write(f"  Details: {json.dumps(details)}\n")
            
            # Log to session log
            self.logger.error(f"{error_type}: {error_msg} | {details}")
    
    def log_warning(self, warning_type: str, warning_msg: str):
        """
        Log a warning to the session
        
        Args:
            warning_type: Type of warning
            warning_msg: Warning message
        """
        with self.lock:
            warning = {
                'timestamp': datetime.now().isoformat(),
                'type': warning_type,
                'message': warning_msg
            }
            
            # Add to session data
            self.session_data['warnings'].append(warning)
            
            # Log to session log
            self.logger.warning(f"{warning_type}: {warning_msg}")
    
    def update_metrics(self, metrics: Dict[str, Any]):
        """
        Update session metrics
        
        Args:
            metrics: Metrics dictionary to update
        """
        with self.lock:
            self.session_data['metrics'].update(metrics)
    
    def set_mode(self, mode: str):
        """
        Set trading mode (PAPER or LIVE)
        
        Args:
            mode: Trading mode
        """
        with self.lock:
            self.session_data['mode'] = mode
            self.log_event('MODE_CHANGE', {'mode': mode})
    
    def end_session(self, reason: str = "NORMAL"):
        """
        End the trading session
        
        Args:
            reason: Reason for ending session
        """
        with self.lock:
            self.session_data['end_time'] = datetime.now().isoformat()
            self.session_data['status'] = 'ENDED'
            
            # Calculate session duration
            duration = datetime.now() - self.session_start
            self.session_data['duration_seconds'] = duration.total_seconds()
            
            # Log end event
            self.log_event('SESSION_END', {
                'reason': reason,
                'duration_seconds': duration.total_seconds()
            })
            
            # Save final session summary
            self._save_session_summary()
            
            self.logger.info(f"Session ended: {reason}")
    
    def _save_session_summary(self):
        """Save complete session summary to JSON"""
        summary_file = self.session_dir / "session_summary.json"
        
        with open(summary_file, 'w') as f:
            json.dump(self.session_data, f, indent=2)
        
        # Also create a human-readable report
        self._create_session_report()
    
    def _create_session_report(self):
        """Create human-readable session report"""
        report_file = self.session_dir / "session_report.txt"
        
        with open(report_file, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write(f"ANGEL-X TRADING SESSION REPORT\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Session ID: {self.session_id}\n")
            f.write(f"Mode: {self.session_data['mode']}\n")
            f.write(f"Status: {self.session_data['status']}\n")
            f.write(f"Start Time: {self.session_data['start_time']}\n")
            f.write(f"End Time: {self.session_data['end_time']}\n")
            
            if 'duration_seconds' in self.session_data:
                duration = self.session_data['duration_seconds']
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                seconds = int(duration % 60)
                f.write(f"Duration: {hours:02d}:{minutes:02d}:{seconds:02d}\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("TRADING METRICS\n")
            f.write("=" * 80 + "\n\n")
            
            metrics = self.session_data['metrics']
            f.write(f"Total Trades: {metrics['total_trades']}\n")
            f.write(f"Wins: {metrics['wins']}\n")
            f.write(f"Losses: {metrics['losses']}\n")
            
            if metrics['total_trades'] > 0:
                win_rate = metrics['wins'] / metrics['total_trades'] * 100
                f.write(f"Win Rate: {win_rate:.2f}%\n")
            
            f.write(f"Total P&L: ₹{metrics['total_pnl']:.2f}\n")
            f.write(f"Max Drawdown: ₹{metrics['max_drawdown']:.2f}\n")
            f.write(f"Greeks API Calls: {metrics['greeks_api_calls']}\n")
            f.write(f"Cache Hit Rate: {metrics['cache_hit_rate']:.1f}%\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("ERRORS & WARNINGS\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Total Errors: {len(self.session_data['errors'])}\n")
            f.write(f"Total Warnings: {len(self.session_data['warnings'])}\n")
            
            if self.session_data['errors']:
                f.write("\nRecent Errors:\n")
                for error in self.session_data['errors'][-10:]:
                    f.write(f"  [{error['timestamp']}] {error['type']}: {error['message']}\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write("END OF REPORT\n")
            f.write("=" * 80 + "\n")
    
    def get_session_info(self) -> Dict[str, Any]:
        """Get current session information"""
        with self.lock:
            return {
                'session_id': self.session_id,
                'status': self.session_data['status'],
                'mode': self.session_data['mode'],
                'start_time': self.session_data['start_time'],
                'uptime_seconds': (datetime.now() - self.session_start).total_seconds(),
                'metrics': self.session_data['metrics'].copy(),
                'errors_count': len(self.session_data['errors']),
                'warnings_count': len(self.session_data['warnings'])
            }
    
    def get_recent_events(self, count: int = 50) -> List[Dict]:
        """Get recent events"""
        with self.lock:
            return self.session_data['events'][-count:]
    
    def get_trades(self) -> List[Dict]:
        """Get all trades in session"""
        with self.lock:
            return self.session_data['trades'].copy()


# Global session logger instance
_session_logger = None


def get_session_logger(session_id: str = None) -> SessionLogger:
    """
    Get or create global session logger instance
    
    Args:
        session_id: Session ID (creates new if None and no existing)
    
    Returns:
        SessionLogger instance
    """
    global _session_logger
    
    if _session_logger is None:
        _session_logger = SessionLogger(session_id)
    
    return _session_logger


def end_current_session(reason: str = "NORMAL"):
    """End current session"""
    global _session_logger
    
    if _session_logger:
        _session_logger.end_session(reason)
        _session_logger = None
