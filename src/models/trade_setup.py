"""Trade Setup Model with Freshness and Validity Validation.

A TradeSetup represents a complete trading opportunity identified by the scanner
with entry, take-profit, stop-loss, and validity checks.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid
from enum import Enum


class SetupStatus(Enum):
    """Status of a setup through its lifecycle."""
    FRESH = "FRESH"              # Just generated, not yet validated
    VALID = "VALID"              # Passed freshness checks, ready to send
    EXPIRED = "EXPIRED"          # Rejected, too stale
    SENT = "SENT"                # Sent to user
    TRIGGERED = "TRIGGERED"      # User entered trade
    ACTIVE = "ACTIVE"            # Trade tracking
    CLOSED = "CLOSED"            # Trade complete (TP/SL/manual)


@dataclass
class TradeSetup:
    """A complete trading setup with validation.
    
    Attributes:
        setup_id: Unique identifier (UUID)
        ticker: Asset symbol
        signal_direction: 1 for BUY, -1 for SELL
        
        # Price levels
        entry_price: Intended entry level
        take_profit: Target exit level
        stop_loss: Risk management level
        
        # Signal generation context
        signal_bar_timestamp_ms: When the bar closed that triggered signal
        signal_z_score: Momentum z-score strength
        signal_confidence: 0.0-1.0 confidence from scanner
        
        # Validation state
        status: Current status in lifecycle
        created_at_ms: When setup was first identified
        validated_at_ms: When passed freshness checks
        sent_at_ms: When sent to user
        
        # Validation results
        freshness_score: 0-1, where 1.0 = signal just triggered
        market_move_pct: Percentage of move already done
        is_valid: Whether setup passes freshness threshold
        rejection_reason: Why rejected if not valid
    """
    
    # Identity
    setup_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str = ""
    signal_direction: int = 1  # 1 or -1
    
    # Levels
    entry_price: float = 0.0
    take_profit: float = 0.0
    stop_loss: float = 0.0
    
    # Signal context
    signal_bar_timestamp_ms: int = 0
    signal_z_score: float = 0.0
    signal_confidence: float = 0.0
    
    # Tracking
    status: SetupStatus = SetupStatus.FRESH
    created_at_ms: int = field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp() * 1000))
    validated_at_ms: Optional[int] = None
    sent_at_ms: Optional[int] = None
    
    # Validation
    freshness_score: float = 1.0
    market_move_pct: float = 0.0
    is_valid: bool = False
    rejection_reason: Optional[str] = None
    
    def __post_init__(self):
        """Validate and compute derived fields."""
        if self.risk_reward_ratio <= 0:
            raise ValueError("Invalid RR ratio (TP and SL must be on opposite sides of entry)")
    
    @property
    def risk_reward_ratio(self) -> float:
        """Risk/Reward ratio: distance to TP / distance to SL."""
        if self.signal_direction > 0:
            # Long: TP above entry, SL below
            tp_dist = abs(self.take_profit - self.entry_price)
            sl_dist = abs(self.entry_price - self.stop_loss)
        else:
            # Short: TP below entry, SL above
            tp_dist = abs(self.entry_price - self.take_profit)
            sl_dist = abs(self.stop_loss - self.entry_price)
        
        return tp_dist / max(sl_dist, 1e-9)
    
    @property
    def rr_string(self) -> str:
        """RR formatted as 'R:R' (e.g., '3:1')."""
        rr = self.risk_reward_ratio
        return f"{rr:.1f}:1"
    
    def validate_freshness(
        self,
        current_price: float,
        current_time_ms: int,
        max_move_percent: float = 30.0,
        max_age_seconds: int = 300
    ) -> bool:
        """Check if setup is still tradable (not expired).
        
        A setup is expired if:
        1. More than max_move_percent (30%) of the move has occurred
        2. Signal bar is older than max_age_seconds (5 min)
        
        Args:
            current_price: Current market price
            current_time_ms: Current time in milliseconds
            max_move_percent: Max % of move allowed (default 30%)
            max_age_seconds: Max age of signal bar (default 300s = 5 min)
        
        Returns:
            True if setup is fresh and valid, False if expired
        """
        now_ms = current_time_ms
        
        # Check 1: Signal age
        signal_age_ms = now_ms - self.signal_bar_timestamp_ms
        signal_age_sec = signal_age_ms / 1000.0
        
        if signal_age_sec > max_age_seconds:
            self.rejection_reason = f"Signal too old ({signal_age_sec:.0f}s > {max_age_seconds}s)"
            self.is_valid = False
            return False
        
        # Check 2: Market move percentage
        if self.signal_direction > 0:
            # Long: entry above stop loss, TP above entry
            total_range = self.take_profit - self.stop_loss
            current_progress = current_price - self.stop_loss
        else:
            # Short: entry below stop loss, TP below entry
            total_range = self.stop_loss - self.take_profit
            current_progress = self.stop_loss - current_price
        
        if total_range > 0:
            move_pct = (current_progress / total_range) * 100.0
            self.market_move_pct = move_pct
            
            if move_pct > max_move_percent:
                self.rejection_reason = (
                    f"Move already {move_pct:.1f}% (>{max_move_percent}%)"
                )
                self.is_valid = False
                return False
            
            # Calculate freshness score: 1.0 if 0% done, 0.0 if max_move_percent done
            self.freshness_score = max(0.0, 1.0 - (move_pct / max_move_percent))
        
        self.is_valid = True
        self.validated_at_ms = now_ms
        self.status = SetupStatus.VALID
        return True
    
    def distance_to_entry(self, current_price: float) -> float:
        """Distance from current price to entry (pips/points)."""
        return abs(current_price - self.entry_price)
    
    def distance_to_tp(self, current_price: float) -> float:
        """Distance from current price to TP (pips/points)."""
        return abs(current_price - self.take_profit)
    
    def pct_of_move_done(self, current_price: float) -> float:
        """Percentage of move from SL to TP that's been completed (0-100%)."""
        if self.signal_direction > 0:
            total = self.take_profit - self.stop_loss
            current = current_price - self.stop_loss
        else:
            total = self.stop_loss - self.take_profit
            current = self.stop_loss - current_price
        
        if total > 0:
            return (current / total) * 100.0
        return 0.0
    
    def summary(self) -> str:
        """One-line setup summary."""
        direction = "BUY" if self.signal_direction > 0 else "SELL"
        status = "✓" if self.is_valid else "✗"
        return (
            f"{status} {self.ticker} {direction} | "
            f"E={self.entry_price:.4f} TP={self.take_profit:.4f} "
            f"SL={self.stop_loss:.4f} | RR={self.rr_string} | "
            f"Fresh={self.freshness_score:.2f}"
        )


@dataclass
class SignalBatch:
    """Batch of setups generated in one scan cycle."""
    
    scan_time_ms: int
    setups: list = field(default_factory=list)
    scan_interval_seconds: int = 60
    
    def add_setup(self, setup: TradeSetup) -> None:
        """Add a setup to the batch."""
        self.setups.append(setup)
    
    def filter_valid(self) -> list:
        """Return only valid (fresh) setups."""
        return [s for s in self.setups if s.is_valid]
    
    def summary(self) -> str:
        """Batch summary."""
        total = len(self.setups)
        valid = len(self.filter_valid())
        expired = total - valid
        return f"Batch: {total} total, {valid} valid, {expired} expired"
