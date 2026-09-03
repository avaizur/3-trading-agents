from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"


class TradeDecision(str, Enum):
    BUY = "BUY"
    WATCH = "WATCH"
    REJECT = "REJECT"


class CriticRecommendation(str, Enum):
    CONTINUE = "CONTINUE"
    CAUTION = "CAUTION"
    BLOCK = "BLOCK"


class MarketSnapshot(BaseModel):
    symbol: str = Field(min_length=1)
    price: float = Field(gt=0)
    volume: Optional[float] = Field(default=None, ge=0)
    timestamp: datetime
    source: str = Field(min_length=1)


class VerificationResult(BaseModel):
    symbol: str
    status: VerificationStatus
    freshness_ok: bool
    verifier_confidence: float = Field(ge=0, le=1)


class TraderRecommendation(BaseModel):
    agent: str
    symbol: str
    decision: TradeDecision
    confidence: float = Field(ge=0, le=1)
    entry: Optional[float] = Field(default=None, gt=0)
    stop: Optional[float] = Field(default=None, gt=0)
    target: Optional[float] = Field(default=None, gt=0)
    holding_period: str

    @model_validator(mode="after")
    def validate_levels(self):
        if self.decision == TradeDecision.BUY:
            if None in (self.entry, self.stop, self.target):
                raise ValueError("BUY requires entry, stop and target")

            if not self.stop < self.entry < self.target:
                raise ValueError(
                    "Phase 1 long-only requires stop < entry < target"
                )

        return self


class CriticReview(BaseModel):
    symbol: str
    recommendation: CriticRecommendation


class RiskDecision(BaseModel):
    allowed: bool
    reason: str
    position_size: float = 0
    planned_risk: float = 0
    reward_risk: float = 0


class PortfolioDecision(BaseModel):
    allowed: bool
    reason: str
    total_open_risk_pct: float
