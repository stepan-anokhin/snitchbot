from dataclasses import dataclass


@dataclass
class Config:
    """Bot configuration."""
    token: str  # Security token
