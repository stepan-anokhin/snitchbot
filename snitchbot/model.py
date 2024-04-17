from dataclasses import dataclass


@dataclass
class Config:
    """Bot configuration."""
    token: str  # Security token


class Commands:
    """Bot commands."""
    WATCH = "watch"
    STOP_WATCH = "stopwatch"
    CANCEL = "cancel"