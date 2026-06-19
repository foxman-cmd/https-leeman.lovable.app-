"""Trade Lifecycle Event System with Millisecond Precision Tracking.

This module provides the core event logging infrastructure for tracking every
stage of a trade setup, from generation through closure. Each event includes
millisecond timestamps and complete market context.

Event Types:
    - SETUP_CREATED: Setup identified by scanner (internal state)
    - SETUP_SENT: Signal sent to Telegram (delivery confirmed)
    - SIGNAL_EXPIRED: Setup rejected as too stale (>30% move done)
    - TRIGGERED: Price hit entry point and trade became active
    - TRADE_ACTIVE: Trade is live and tracking
    - TAKE_PROFIT_HIT: Price reached TP level
    - STOP_LOSS_HIT: Price hit SL level
    - TRADE_CLOSED: Trade closed manually or at SL/TP
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any
import json
from pathlib import Path


class EventType(Enum):
    """Trade event types with temporal ordering."""
    SETUP_CREATED = "SETUP_CREATED"
    SETUP_SENT = "SETUP_SENT"
    SIGNAL_EXPIRED = "SIGNAL_EXPIRED"
    TRIGGERED = "TRIGGERED"
    TRADE_ACTIVE = "TRADE_ACTIVE"
    TAKE_PROFIT_HIT = "TAKE_PROFIT_HIT"
    STOP_LOSS_HIT = "STOP_LOSS_HIT"
    TRADE_CLOSED = "TRADE_CLOSED"


@dataclass
class TradeEvent:
    """Single event in a trade's lifecycle.
    
    Attributes:
        event_type: Type of event (EventType enum)
        ticker: Asset symbol (e.g., 'SPY', 'EUR/USD')
        timestamp_ms: UTC timestamp in milliseconds (NOT seconds!)
        signal_direction: 1 for BUY, -1 for SELL
        
        # Entry context
        entry_price: Price level for entry
        take_profit: TP target price
        stop_loss: SL level
        risk_reward_ratio: TP distance / SL distance
        
        # Current market state
        current_price: Market price at event time
        distance_from_entry_pct: (current - entry) / entry * 100 (if triggered)
        distance_to_tp_pct: (tp - current) / current * 100 (if active)
        
        # Signal quality metrics
        confidence: 0.0-1.0 confidence level of signal
        bar_age_seconds: How old was the bar that triggered signal
        z_score: Momentum z-score for this signal
        
        # Rejection reasons (for SIGNAL_EXPIRED)
        rejection_reason: Why was signal rejected?
        
        # Trade results (for CLOSED events)
        exit_price: Actual exit price
        pnl_points: Exit - Entry (in points/pips)
        pnl_percent: (Exit - Entry) / Entry * 100
        
        # Tracking & metadata
        setup_id: Unique ID for this setup (uuid)
        message_id: Telegram message ID (for updates)
        notes: Any additional context
    """
    
    event_type: EventType
    ticker: str
    timestamp_ms: int  # Always milliseconds!
    signal_direction: int  # 1 or -1
    
    # Entry context
    entry_price: float = 0.0
    take_profit: float = 0.0
    stop_loss: float = 0.0
    risk_reward_ratio: float = 0.0
    
    # Market state
    current_price: float = 0.0
    distance_from_entry_pct: Optional[float] = None
    distance_to_tp_pct: Optional[float] = None
    
    # Signal quality
    confidence: float = 0.0
    bar_age_seconds: Optional[int] = None
    z_score: Optional[float] = None
    
    # Rejection/results
    rejection_reason: Optional[str] = None
    exit_price: Optional[float] = None
    pnl_points: Optional[float] = None
    pnl_percent: Optional[float] = None
    
    # Tracking
    setup_id: str = ""
    message_id: Optional[int] = None
    notes: str = ""
    
    def __post_init__(self):
        """Validate event state."""
        if self.timestamp_ms < 1_000_000_000_000:
            # If passed seconds, multiply by 1000
            self.timestamp_ms *= 1000
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization."""
        d = asdict(self)
        d['event_type'] = self.event_type.value
        d['timestamp_iso'] = datetime.fromtimestamp(
            self.timestamp_ms / 1000, tz=timezone.utc
        ).isoformat()
        return d
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str, indent=2)
    
    @property
    def timestamp_iso(self) -> str:
        """ISO 8601 timestamp string."""
        return datetime.fromtimestamp(
            self.timestamp_ms / 1000, tz=timezone.utc
        ).isoformat()
    
    @property
    def summary(self) -> str:
        """One-line summary of event."""
        direction = "BUY" if self.signal_direction > 0 else "SELL"
        return (
            f"{self.timestamp_iso} | {self.ticker} | {direction} | "
            f"{self.event_type.value} | Entry={self.entry_price:.4f} | "
            f"Current={self.current_price:.4f}"
        )


@dataclass
class TradeLifecycle:
    """Complete lifecycle of one trade setup."""
    
    setup_id: str
    ticker: str
    signal_direction: int
    entry_price: float
    take_profit: float
    stop_loss: float
    
    events: Dict[EventType, TradeEvent] = field(default_factory=dict)
    created_at_ms: int = 0
    
    def add_event(self, event: TradeEvent):
        """Add an event to the lifecycle."""
        self.events[event.event_type] = event
        if event.event_type == EventType.SETUP_CREATED and not self.created_at_ms:
            self.created_at_ms = event.timestamp_ms
    
    def is_expired(self) -> bool:
        """Check if setup was explicitly expired."""
        return EventType.SIGNAL_EXPIRED in self.events
    
    def is_triggered(self) -> bool:
        """Check if trade was triggered (not rejected)."""
        return EventType.TRIGGERED in self.events
    
    def is_closed(self) -> bool:
        """Check if trade has final outcome."""
        return any(
            e in self.events for e in [
                EventType.TAKE_PROFIT_HIT,
                EventType.STOP_LOSS_HIT,
                EventType.TRADE_CLOSED
            ]
        )
    
    def total_duration_ms(self) -> int:
        """Duration from creation to final event."""
        if not self.events:
            return 0
        times = [e.timestamp_ms for e in self.events.values()]
        return max(times) - min(times)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert complete lifecycle to dict."""
        return {
            'setup_id': self.setup_id,
            'ticker': self.ticker,
            'direction': self.signal_direction,
            'entry': self.entry_price,
            'tp': self.take_profit,
            'sl': self.stop_loss,
            'created_at_ms': self.created_at_ms,
            'total_duration_ms': self.total_duration_ms(),
            'events': {e.name: evt.to_dict() for e, evt in self.events.items()},
            'is_expired': self.is_expired(),
            'is_triggered': self.is_triggered(),
            'is_closed': self.is_closed(),
        }
    
    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), default=str, indent=2)


class EventLogger:
    """File-based event logger for trade lifecycle tracking."""
    
    def __init__(self, data_dir: str = "data/trade_events"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def log_event(self, event: TradeEvent) -> None:
        """Write a single event to log file."""
        # File named: TICKER_SETUP_ID.jsonl
        filename = self.data_dir / f"{event.ticker}_{event.setup_id}.jsonl"
        
        with open(filename, 'a') as f:
            f.write(event.to_json() + '\n')
    
    def log_lifecycle(self, lifecycle: TradeLifecycle) -> None:
        """Write complete lifecycle to file."""
        filename = self.data_dir / f"lifecycle_{lifecycle.setup_id}.json"
        
        with open(filename, 'w') as f:
            f.write(lifecycle.to_json())
    
    def read_lifecycle(self, setup_id: str) -> Optional[TradeLifecycle]:
        """Read lifecycle from file."""
        filename = self.data_dir / f"lifecycle_{setup_id}.json"
        
        if not filename.exists():
            return None
        
        with open(filename, 'r') as f:
            data = json.load(f)
        
        lifecycle = TradeLifecycle(
            setup_id=data['setup_id'],
            ticker=data['ticker'],
            signal_direction=data['direction'],
            entry_price=data['entry'],
            take_profit=data['tp'],
            stop_loss=data['sl'],
            created_at_ms=data['created_at_ms'],
        )
        
        for event_name, event_data in data['events'].items():
            event_type = EventType[event_name]
            event_data['event_type'] = event_type
            event = TradeEvent(**event_data)
            lifecycle.add_event(event)
        
        return lifecycle
