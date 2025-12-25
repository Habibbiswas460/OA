"""
Network Resilience Helper
Local network optimization with connection monitoring and auto-recovery
"""

import time
import logging
from datetime import datetime
from threading import Thread, Event, Lock
from config import config
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)


class NetworkMonitor:
    """
    Monitors network connectivity and data flow health
    Alerts on connection issues and data flow problems
    """
    
    def __init__(self):
        self.monitoring = False
        self.monitor_thread = None
        self.stop_monitor = Event()
        self.data_lock = Lock()
        
        # Health metrics
        self.last_api_call_time = time.time()
        self.last_websocket_tick = time.time()
        self.api_call_count = 0
        self.api_error_count = 0
        self.websocket_reconnect_count = 0
        
        # Alerts
        self.alerts = []
        self.max_alerts = 100
        
        logger.info("NetworkMonitor initialized")
    
    def start_monitoring(self):
        """Start network health monitoring"""
        if not self.monitoring:
            self.monitoring = True
            self.stop_monitor.clear()
            self.monitor_thread = Thread(
                target=self._monitor_loop,
                daemon=True,
                name="NetworkMonitor"
            )
            self.monitor_thread.start()
            logger.info("Network monitoring started")
    
    def stop_monitoring(self):
        """Stop network monitoring"""
        self.monitoring = False
        self.stop_monitor.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Network monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop"""
        while not self.stop_monitor.is_set():
            try:
                self._check_websocket_health()
                self._check_api_health()
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(5)
    
    def _check_websocket_health(self):
        """Check WebSocket data flow"""
        time_since_last_tick = time.time() - self.last_websocket_tick
        
        if time_since_last_tick > config.WEBSOCKET_TICK_TIMEOUT:
            alert = {
                'timestamp': datetime.now().isoformat(),
                'type': 'websocket_timeout',
                'duration_seconds': time_since_last_tick,
                'threshold_seconds': config.WEBSOCKET_TICK_TIMEOUT
            }
            self._add_alert(alert)
            logger.warning(f"WebSocket: No ticks for {time_since_last_tick:.0f}s")
    
    def _check_api_health(self):
        """Check API call health"""
        error_rate = 0
        if self.api_call_count > 0:
            error_rate = self.api_error_count / self.api_call_count
        
        if error_rate > 0.3:  # More than 30% errors
            alert = {
                'timestamp': datetime.now().isoformat(),
                'type': 'api_error_rate_high',
                'error_rate': error_rate,
                'total_calls': self.api_call_count,
                'error_count': self.api_error_count
            }
            self._add_alert(alert)
            logger.warning(f"API error rate high: {error_rate:.1%} ({self.api_error_count}/{self.api_call_count})")
    
    def _add_alert(self, alert):
        """Add alert to queue"""
        with self.data_lock:
            self.alerts.append(alert)
            # Keep only recent alerts
            if len(self.alerts) > self.max_alerts:
                self.alerts = self.alerts[-self.max_alerts:]
    
    def record_api_call(self, success=True):
        """Record API call result"""
        with self.data_lock:
            self.last_api_call_time = time.time()
            self.api_call_count += 1
            if not success:
                self.api_error_count += 1
    
    def record_websocket_tick(self):
        """Record WebSocket tick received"""
        with self.data_lock:
            self.last_websocket_tick = time.time()
    
    def record_websocket_reconnect(self):
        """Record WebSocket reconnection"""
        with self.data_lock:
            self.websocket_reconnect_count += 1
    
    def get_health_status(self):
        """Get current network health status"""
        with self.data_lock:
            error_rate = 0
            if self.api_call_count > 0:
                error_rate = self.api_error_count / self.api_call_count
            
            time_since_last_tick = time.time() - self.last_websocket_tick
            
            return {
                'timestamp': datetime.now().isoformat(),
                'api_calls': self.api_call_count,
                'api_errors': self.api_error_count,
                'api_error_rate': error_rate,
                'websocket_reconnects': self.websocket_reconnect_count,
                'time_since_last_tick': time_since_last_tick,
                'alerts_count': len(self.alerts),
                'recent_alerts': self.alerts[-5:] if self.alerts else []
            }
    
    def get_alerts(self, limit=None):
        """Get recent alerts"""
        with self.data_lock:
            if limit:
                return self.alerts[-limit:]
            return self.alerts[:]


class ConnectionPool:
    """
    Simple connection pool for managing multiple API connections
    Helps with load distribution and failover
    """
    
    def __init__(self, pool_size=3):
        self.pool_size = pool_size
        self.connections = []
        self.available_connections = []
        self.pool_lock = Lock()
        
        logger.info(f"ConnectionPool initialized with size {pool_size}")
    
    def add_connection(self, connection):
        """Add connection to pool"""
        with self.pool_lock:
            self.connections.append(connection)
            self.available_connections.append(connection)
    
    def get_connection(self, timeout=5):
        """Get available connection from pool"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            with self.pool_lock:
                if self.available_connections:
                    return self.available_connections.pop(0)
            
            time.sleep(0.1)
        
        logger.warning(f"No available connections after {timeout}s")
        return None
    
    def return_connection(self, connection):
        """Return connection to pool"""
        with self.pool_lock:
            if connection not in self.available_connections:
                self.available_connections.append(connection)


# Global network monitor instance
_network_monitor = None


def get_network_monitor():
    """Get or create global network monitor"""
    global _network_monitor
    if _network_monitor is None:
        _network_monitor = NetworkMonitor()
    return _network_monitor
