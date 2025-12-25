"""
ANGEL-X Trade Journal
Comprehensive logging of every trade for analysis, backtesting, and ML learning
"""

import csv
import json
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
from config import config
from src.utils.logger import StrategyLogger

logger = StrategyLogger.get_logger(__name__)


@dataclass
class TradeRecord:
    """Complete trade record with all details"""
    # Trade identification
    trade_id: str
    timestamp_entry: datetime
    timestamp_exit: datetime
    duration_seconds: int
    
    # Instrument details
    underlying: str
    strike: int
    option_type: str  # CE or PE
    expiry_date: str
    
    # Entry details
    entry_price: float
    entry_delta: float
    entry_gamma: float
    entry_theta: float
    entry_vega: float
    entry_iv: float
    entry_spread: float
    entry_bid: float
    entry_ask: float
    entry_volume: int
    entry_oi: int
    
    # Exit details
    exit_price: float
    exit_delta: float
    exit_gamma: float
    exit_theta: float
    exit_vega: float
    exit_iv: float
    exit_spread: float
    exit_volume: int
    exit_oi: int
    
    # P&L
    pnl_amount: float
    pnl_percent: float
    qty: int
    
    # Reasons
    entry_reason_tags: List[str]  # e.g., ['delta_jump', 'oi_build', 'volume_spike']
    exit_reason_tags: List[str]  # e.g., ['hard_sl', 'delta_weakness', 'gamma_rollover']
    
    # Risk management
    original_sl_price: float
    original_sl_percent: float
    original_target_price: float
    original_target_percent: float
    
    # Violations
    rule_violations: List[str]  # e.g., ['no_averaging', 'sl_widened']
    
    # Notes
    notes: str = ""
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for CSV/JSON export"""
        data = asdict(self)
        # Convert datetime objects to ISO format strings
        data['timestamp_entry'] = self.timestamp_entry.isoformat()
        data['timestamp_exit'] = self.timestamp_exit.isoformat()
        # Convert lists to JSON strings
        data['entry_reason_tags'] = json.dumps(self.entry_reason_tags)
        data['exit_reason_tags'] = json.dumps(self.exit_reason_tags)
        data['rule_violations'] = json.dumps(self.rule_violations)
        return data


class TradeJournal:
    """
    Manages trade logging and analysis
    Supports CSV export for backtesting and future ML learning
    """
    
    def __init__(self, output_dir: str = "./journal"):
        """Initialize trade journal"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.trades: List[TradeRecord] = []
        self.trade_counter = 0
        
        # CSV file paths
        self.csv_file = self.output_dir / f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.json_file = self.output_dir / f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Statistics
        self.daily_pnl = 0.0
        self.winning_trades = 0
        self.losing_trades = 0
        
        logger.info(f"TradeJournal initialized - Output: {self.output_dir}")
    
    def log_trade(
        self,
        underlying: str,
        strike: int,
        option_type: str,
        expiry_date: str,
        entry_price: float,
        exit_price: float,
        qty: int,
        entry_delta: float,
        entry_gamma: float,
        entry_theta: float,
        entry_vega: float,
        entry_iv: float,
        exit_delta: float,
        exit_gamma: float,
        exit_theta: float,
        exit_vega: float,
        exit_iv: float,
        entry_spread: float,
        exit_spread: float,
        entry_reason_tags: List[str],
        exit_reason_tags: List[str],
        original_sl_price: float,
        original_sl_percent: float,
        original_target_price: float,
        original_target_percent: float,
        entry_bid: float = 0,
        entry_ask: float = 0,
        entry_volume: int = 0,
        entry_oi: int = 0,
        exit_volume: int = 0,
        exit_oi: int = 0,
        rule_violations: Optional[List[str]] = None,
        notes: str = ""
    ) -> TradeRecord:
        """
        Log a completed trade
        """
        self.trade_counter += 1
        trade_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self.trade_counter:03d}"
        
        now = datetime.now()
        # Estimate exit time (for real implementation, use actual exit time)
        exit_time = now
        duration = 60  # Default 1 minute (will be updated when trade actually exits)
        
        # Calculate P&L
        pnl_amount = (exit_price - entry_price) * qty
        pnl_percent = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        
        # Update statistics
        self.daily_pnl += pnl_amount
        if pnl_amount > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        # Create record
        record = TradeRecord(
            trade_id=trade_id,
            timestamp_entry=now,
            timestamp_exit=exit_time,
            duration_seconds=duration,
            underlying=underlying,
            strike=strike,
            option_type=option_type,
            expiry_date=expiry_date,
            entry_price=entry_price,
            entry_delta=entry_delta,
            entry_gamma=entry_gamma,
            entry_theta=entry_theta,
            entry_vega=entry_vega,
            entry_iv=entry_iv,
            entry_spread=entry_spread,
            entry_bid=entry_bid,
            entry_ask=entry_ask,
            entry_volume=entry_volume,
            entry_oi=entry_oi,
            exit_price=exit_price,
            exit_delta=exit_delta,
            exit_gamma=exit_gamma,
            exit_theta=exit_theta,
            exit_vega=exit_vega,
            exit_iv=exit_iv,
            exit_spread=exit_spread,
            exit_volume=exit_volume,
            exit_oi=exit_oi,
            pnl_amount=pnl_amount,
            pnl_percent=pnl_percent,
            qty=qty,
            entry_reason_tags=entry_reason_tags,
            exit_reason_tags=exit_reason_tags,
            original_sl_price=original_sl_price,
            original_sl_percent=original_sl_percent,
            original_target_price=original_target_price,
            original_target_percent=original_target_percent,
            rule_violations=rule_violations or [],
            notes=notes
        )
        
        self.trades.append(record)
        
        # Log to file
        self._write_trade_to_csv(record)
        self._write_trade_to_json(record)
        
        # Console log summary
        status = "✓ WIN" if pnl_amount > 0 else "✗ LOSS"
        logger.info(
            f"{status} | {underlying} {strike}{option_type} | "
            f"Entry: ₹{entry_price:.2f} Exit: ₹{exit_price:.2f} | "
            f"PnL: ₹{pnl_amount:.2f} ({pnl_percent:+.2f}%) | "
            f"Reasons: Entry=[{','.join(entry_reason_tags)}] Exit=[{','.join(exit_reason_tags)}]"
        )
        
        return record
    
    def _write_trade_to_csv(self, record: TradeRecord):
        """Write trade record to CSV"""
        try:
            data = record.to_dict()
            
            # Check if file exists (first write includes headers)
            file_exists = self.csv_file.exists() and self.csv_file.stat().st_size > 0
            
            with open(self.csv_file, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=data.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(data)
        except Exception as e:
            logger.error(f"Error writing trade to CSV: {e}")
    
    def _write_trade_to_json(self, record: TradeRecord):
        """Write trade record to JSON (append to array)"""
        try:
            data = record.to_dict()
            
            # Load existing trades if file exists
            trades = []
            if self.json_file.exists():
                with open(self.json_file, 'r') as f:
                    trades = json.load(f)
            
            # Append new trade
            trades.append(data)
            
            # Write back
            with open(self.json_file, 'w') as f:
                json.dump(trades, f, indent=2)
        except Exception as e:
            logger.error(f"Error writing trade to JSON: {e}")
    
    def get_daily_stats(self) -> Dict:
        """Get daily trading statistics"""
        total_trades = len(self.trades)
        winning_trades = self.winning_trades
        losing_trades = self.losing_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # P&L stats
        total_pnl = sum(t.pnl_amount for t in self.trades)
        avg_pnl = (total_pnl / total_trades) if total_trades > 0 else 0
        
        # Greeks stats
        avg_entry_delta = sum(t.entry_delta for t in self.trades) / total_trades if total_trades > 0 else 0
        avg_entry_gamma = sum(t.entry_gamma for t in self.trades) / total_trades if total_trades > 0 else 0
        
        # Duration stats
        avg_duration = sum(t.duration_seconds for t in self.trades) / total_trades if total_trades > 0 else 0
        
        stats = {
            'timestamp': datetime.now().isoformat(),
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate_percent': round(win_rate, 2),
            'total_pnl': round(total_pnl, 2),
            'avg_pnl_per_trade': round(avg_pnl, 2),
            'best_trade_pnl': round(max((t.pnl_amount for t in self.trades), default=0), 2),
            'worst_trade_pnl': round(min((t.pnl_amount for t in self.trades), default=0), 2),
            'avg_entry_delta': round(avg_entry_delta, 3),
            'avg_entry_gamma': round(avg_entry_gamma, 4),
            'avg_duration_seconds': round(avg_duration, 1),
        }
        
        return stats
    
    def print_daily_summary(self):
        """Print daily trading summary"""
        stats = self.get_daily_stats()
        
        logger.info("="*80)
        logger.info("DAILY TRADING SUMMARY")
        logger.info("="*80)
        logger.info(f"Total Trades: {stats['total_trades']} (Win: {stats['winning_trades']}, Loss: {stats['losing_trades']})")
        logger.info(f"Win Rate: {stats['win_rate_percent']:.2f}%")
        logger.info(f"Total P&L: ₹{stats['total_pnl']:.2f}")
        logger.info(f"Avg P&L/Trade: ₹{stats['avg_pnl_per_trade']:.2f}")
        logger.info(f"Best Trade: ₹{stats['best_trade_pnl']:.2f}")
        logger.info(f"Worst Trade: ₹{stats['worst_trade_pnl']:.2f}")
        logger.info(f"Avg Entry Delta: {stats['avg_entry_delta']:.3f}")
        logger.info(f"Avg Duration: {stats['avg_duration_seconds']:.1f} seconds")
        logger.info("="*80)
    
    def get_entry_reason_stats(self) -> Dict[str, int]:
        """Analyze which entry reasons work best"""
        reason_pnl = {}
        reason_count = {}
        
        for trade in self.trades:
            for reason in trade.entry_reason_tags:
                if reason not in reason_pnl:
                    reason_pnl[reason] = 0
                    reason_count[reason] = 0
                reason_pnl[reason] += trade.pnl_amount
                reason_count[reason] += 1
        
        return {
            'by_pnl': reason_pnl,
            'by_count': reason_count,
            'by_avg': {r: reason_pnl[r] / reason_count[r] if reason_count[r] > 0 else 0 
                      for r in reason_pnl}
        }
    
    def get_exit_reason_stats(self) -> Dict[str, int]:
        """Analyze which exit reasons are most common"""
        reason_count = {}
        reason_wins = {}
        
        for trade in self.trades:
            for reason in trade.exit_reason_tags:
                if reason not in reason_count:
                    reason_count[reason] = 0
                    reason_wins[reason] = 0
                reason_count[reason] += 1
                if trade.pnl_amount > 0:
                    reason_wins[reason] += 1
        
        return {
            'by_count': reason_count,
            'by_wins': reason_wins,
            'win_rate_by_exit': {r: reason_wins[r] / reason_count[r] * 100 if reason_count[r] > 0 else 0
                                for r in reason_count}
        }
    
    def export_summary_report(self):
        """Export a comprehensive summary report"""
        report_file = self.output_dir / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        with open(report_file, 'w') as f:
            f.write("="*80 + "\n")
            f.write("ANGEL-X TRADING STRATEGY - DAILY SUMMARY REPORT\n")
            f.write("="*80 + "\n\n")
            
            # Daily stats
            stats = self.get_daily_stats()
            f.write("STATISTICS\n")
            f.write("-"*80 + "\n")
            for key, value in stats.items():
                f.write(f"{key}: {value}\n")
            
            f.write("\n\nENTRY REASON ANALYSIS\n")
            f.write("-"*80 + "\n")
            entry_stats = self.get_entry_reason_stats()
            for reason, count in entry_stats['by_count'].items():
                avg_pnl = entry_stats['by_avg'].get(reason, 0)
                f.write(f"{reason}: {count} trades, avg P&L: ₹{avg_pnl:.2f}\n")
            
            f.write("\n\nEXIT REASON ANALYSIS\n")
            f.write("-"*80 + "\n")
            exit_stats = self.get_exit_reason_stats()
            for reason, count in exit_stats['by_count'].items():
                wins = exit_stats['by_wins'].get(reason, 0)
                win_rate = exit_stats['win_rate_by_exit'].get(reason, 0)
                f.write(f"{reason}: {count} times, {wins} wins, {win_rate:.1f}% win rate\n")
            
            f.write("\n\nTRADE-BY-TRADE DETAILS\n")
            f.write("-"*80 + "\n")
            for trade in self.trades:
                f.write(f"\n[{trade.trade_id}]\n")
                f.write(f"Instrument: {trade.underlying} {trade.strike}{trade.option_type}\n")
                f.write(f"Entry: ₹{trade.entry_price:.2f} (Δ{trade.entry_delta:.2f}, Γ{trade.entry_gamma:.4f})\n")
                f.write(f"Exit: ₹{trade.exit_price:.2f} (Δ{trade.exit_delta:.2f}, Γ{trade.exit_gamma:.4f})\n")
                f.write(f"P&L: ₹{trade.pnl_amount:.2f} ({trade.pnl_percent:+.2f}%)\n")
                f.write(f"Duration: {trade.duration_seconds}s\n")
                f.write(f"Entry: {','.join(trade.entry_reason_tags)}\n")
                f.write(f"Exit: {','.join(trade.exit_reason_tags)}\n")
                if trade.rule_violations:
                    f.write(f"Violations: {','.join(trade.rule_violations)}\n")
        
        logger.info(f"Summary report exported to: {report_file}")
        return report_file
