"""Live Price Validation Engine.

Validates setups against real-time market prices before sending signals.
Prevents sending signals for trades that are already 30%+ complete.
"""

from datetime import datetime, timezone
from typing import Optional, List
import logging
from src.models.trade_setup import TradeSetup, SignalBatch
from src.models.trade_event import TradeEvent, EventType

logger = logging.getLogger(__name__)


class LiveValidator:
    """Validates trade setups against live market data."""
    
    def __init__(self, max_move_percent: float = 30.0, max_age_seconds: int = 300):
        """Initialize validator.
        
        Args:
            max_move_percent: Reject setup if >this% of move done (default 30%)
            max_age_seconds: Reject setup if bar is older than this (default 5 min)
        """
        self.max_move_percent = max_move_percent
        self.max_age_seconds = max_age_seconds
    
    def validate_setup(
        self,
        setup: TradeSetup,
        current_price: float,
        current_time_ms: Optional[int] = None
    ) -> tuple:
        """Validate a single setup against live market price.
        
        Returns:
            (is_valid: bool, rejection_reason: Optional[str])
        """
        if current_time_ms is None:
            current_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        # Let setup handle validation
        is_fresh = setup.validate_freshness(
            current_price=current_price,
            current_time_ms=current_time_ms,
            max_move_percent=self.max_move_percent,
            max_age_seconds=self.max_age_seconds
        )
        
        return is_fresh, setup.rejection_reason
    
    def validate_batch(
        self,
        batch: SignalBatch,
        price_data: dict,
        current_time_ms: Optional[int] = None
    ) -> tuple:
        """Validate a batch of setups.
        
        Args:
            batch: SignalBatch with setups to validate
            price_data: Dict[ticker] -> current_price
            current_time_ms: Current time in ms
        
        Returns:
            (valid_setups: List[TradeSetup], events: List[TradeEvent])
        """
        if current_time_ms is None:
            current_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        valid_setups = []
        events = []
        
        for setup in batch.setups:
            if setup.ticker not in price_data:
                logger.warning(f"No price data for {setup.ticker}, skipping")
                continue
            
            current_price = price_data[setup.ticker]
            is_valid, rejection_reason = self.validate_setup(
                setup, current_price, current_time_ms
            )
            
            if is_valid:
                valid_setups.append(setup)
                logger.info(f"✓ {setup.summary()}")
            else:
                # Create EXPIRED event
                direction = "BUY" if setup.signal_direction > 0 else "SELL"
                event = TradeEvent(
                    event_type=EventType.SIGNAL_EXPIRED,
                    ticker=setup.ticker,
                    timestamp_ms=current_time_ms,
                    signal_direction=setup.signal_direction,
                    entry_price=setup.entry_price,
                    take_profit=setup.take_profit,
                    stop_loss=setup.stop_loss,
                    current_price=current_price,
                    confidence=setup.signal_confidence,
                    bar_age_seconds=int((current_time_ms - setup.signal_bar_timestamp_ms) / 1000),
                    rejection_reason=rejection_reason,
                    setup_id=setup.setup_id,
                    notes=f"Rejected: {rejection_reason}"
                )
                events.append(event)
                logger.info(f"✗ EXPIRED: {setup.summary()} | Reason: {rejection_reason}")
        
        return valid_setups, events


def create_setup_from_signal(
    ticker: str,
    signal_value: float,
    signal_z_score: float,
    signal_confidence: float,
    bar_price: float,
    bar_timestamp_ms: int,
    atr_value: float,
    atr_multiplier: float = 1.0,
) -> TradeSetup:
    """Create a TradeSetup from scanner output.
    
    Uses ATR for stop loss placement (industry standard).
    
    Args:
        ticker: Asset symbol
        signal_value: 1 for BUY, -1 for SELL
        signal_z_score: Z-score magnitude (|z|)
        signal_confidence: 0-1 confidence
        bar_price: Price at bar close
        bar_timestamp_ms: Bar timestamp in ms
        atr_value: Average True Range for this asset
        atr_multiplier: Multiplier for SL (default 1.0x ATR)
    
    Returns:
        TradeSetup ready for validation
    """
    direction = int(signal_value)
    
    if direction > 0:
        # BUY: entry = bar_price, SL = entry - ATR, TP = entry + 3*ATR
        entry = bar_price
        stop_loss = bar_price - (atr_value * atr_multiplier)
        take_profit = bar_price + (3 * atr_value * atr_multiplier)
    else:
        # SELL: entry = bar_price, SL = entry + ATR, TP = entry - 3*ATR
        entry = bar_price
        stop_loss = bar_price + (atr_value * atr_multiplier)
        take_profit = bar_price - (3 * atr_value * atr_multiplier)
    
    setup = TradeSetup(
        ticker=ticker,
        signal_direction=direction,
        entry_price=entry,
        take_profit=take_profit,
        stop_loss=stop_loss,
        signal_bar_timestamp_ms=bar_timestamp_ms,
        signal_z_score=signal_z_score,
        signal_confidence=signal_confidence,
    )
    
    return setup


# Validation thresholds for different scenarios
VALIDATION_PROFILES = {
    "conservative": {
        "max_move_percent": 20.0,  # Reject if 20%+ done
        "max_age_seconds": 180,     # Reject if older than 3 min
    },
    "moderate": {
        "max_move_percent": 30.0,  # Reject if 30%+ done
        "max_age_seconds": 300,     # Reject if older than 5 min
    },
    "aggressive": {
        "max_move_percent": 50.0,  # Reject if 50%+ done
        "max_age_seconds": 600,     # Reject if older than 10 min
    },
}


def get_validator(profile: str = "moderate") -> LiveValidator:
    """Get a preconfigured validator.
    
    Args:
        profile: One of "conservative", "moderate", "aggressive"
    
    Returns:
        Configured LiveValidator
    """
    if profile not in VALIDATION_PROFILES:
        raise ValueError(f"Unknown profile: {profile}")
    
    params = VALIDATION_PROFILES[profile]
    return LiveValidator(**params)
