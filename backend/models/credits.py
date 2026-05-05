"""
Credit transaction model.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CreditTransaction:
    id: str
    user_id: str
    amount: int  # positive = purchase/refund, negative = scan cost
    balance_after: int
    reason: str  # "purchase", "scan_basic", "scan_premium", "scan_pro", "refund", "welcome_bonus"
    scan_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount": self.amount,
            "balance_after": self.balance_after,
            "reason": self.reason,
            "scan_id": self.scan_id,
            "created_at": self.created_at.isoformat(),
        }


# Scan cost table
SCAN_COSTS = {
    "basic": 1,    # Mesh + GLB + PLY
    "premium": 2,  # + NeuS-facto refinement + Splat
    "pro": 3,      # + Primitives + E57 + IFC
}

WELCOME_BONUS = 3
