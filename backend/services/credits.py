"""
Credits Ledger Service — SQLite-backed for MVP.

Business rules:
  - New users get 3 free credits (welcome_bonus)
  - Basic scan: 1 credit
  - Premium scan: 2 credits
  - Pro scan: 3 credits
  - Auto-refund on pipeline failure
  - Balance cannot go negative
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from models.credits import SCAN_COSTS, WELCOME_BONUS, CreditTransaction

_DB_PATH = Path(__file__).parent.parent / "credits.db"


def _get_db() -> sqlite3.Connection:
    db = sqlite3.connect(str(_DB_PATH))
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS credit_transactions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            reason TEXT NOT NULL,
            scan_id TEXT,
            created_at TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_credits_user
        ON credit_transactions(user_id, created_at)
    """)
    db.commit()
    return db


def _ensure_user(db: sqlite3.Connection, user_id: str) -> None:
    """Grant welcome bonus if this is a new user."""
    row = db.execute(
        "SELECT COUNT(*) FROM credit_transactions WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if row[0] == 0:
        txn_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db.execute(
            "INSERT INTO credit_transactions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (txn_id, user_id, WELCOME_BONUS, WELCOME_BONUS, "welcome_bonus", None, now),
        )
        db.commit()


def get_balance(user_id: str) -> int:
    """Get current credit balance for a user."""
    db = _get_db()
    _ensure_user(db, user_id)

    row = db.execute(
        "SELECT balance_after FROM credit_transactions "
        "WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    db.close()

    return row[0] if row else 0


def add_credits(user_id: str, amount: int, reason: str = "purchase") -> CreditTransaction:
    """Add credits to a user's balance."""
    if amount <= 0:
        raise ValueError("Amount must be positive")

    db = _get_db()
    _ensure_user(db, user_id)

    current = get_balance(user_id)
    new_balance = current + amount
    txn_id = str(uuid.uuid4())
    now = datetime.utcnow()

    txn = CreditTransaction(
        id=txn_id,
        user_id=user_id,
        amount=amount,
        balance_after=new_balance,
        reason=reason,
        created_at=now,
    )

    db.execute(
        "INSERT INTO credit_transactions VALUES (?, ?, ?, ?, ?, ?, ?)",
        (txn.id, txn.user_id, txn.amount, txn.balance_after, txn.reason, txn.scan_id, now.isoformat()),
    )
    db.commit()
    db.close()
    return txn


def deduct_credits(
    user_id: str, amount: int, scan_id: str, reason: str = "scan_basic"
) -> CreditTransaction | None:
    """
    Deduct credits for a scan. Returns None if insufficient balance.
    """
    if amount <= 0:
        raise ValueError("Amount must be positive")

    db = _get_db()
    _ensure_user(db, user_id)

    current = get_balance(user_id)
    if current < amount:
        db.close()
        return None

    new_balance = current - amount
    txn_id = str(uuid.uuid4())
    now = datetime.utcnow()

    txn = CreditTransaction(
        id=txn_id,
        user_id=user_id,
        amount=-amount,
        balance_after=new_balance,
        reason=reason,
        scan_id=scan_id,
        created_at=now,
    )

    db.execute(
        "INSERT INTO credit_transactions VALUES (?, ?, ?, ?, ?, ?, ?)",
        (txn.id, txn.user_id, txn.amount, txn.balance_after, txn.reason, txn.scan_id, now.isoformat()),
    )
    db.commit()
    db.close()
    return txn


def refund_credits(user_id: str, scan_id: str) -> CreditTransaction | None:
    """
    Refund credits for a failed scan.
    Finds the original deduction and reverses it.
    """
    db = _get_db()

    # Find the deduction transaction
    row = db.execute(
        "SELECT amount FROM credit_transactions "
        "WHERE user_id = ? AND scan_id = ? AND amount < 0 "
        "ORDER BY created_at DESC LIMIT 1",
        (user_id, scan_id),
    ).fetchone()

    if row is None:
        db.close()
        return None

    refund_amount = abs(row[0])
    current = get_balance(user_id)
    new_balance = current + refund_amount
    txn_id = str(uuid.uuid4())
    now = datetime.utcnow()

    txn = CreditTransaction(
        id=txn_id,
        user_id=user_id,
        amount=refund_amount,
        balance_after=new_balance,
        reason="refund",
        scan_id=scan_id,
        created_at=now,
    )

    db.execute(
        "INSERT INTO credit_transactions VALUES (?, ?, ?, ?, ?, ?, ?)",
        (txn.id, txn.user_id, txn.amount, txn.balance_after, txn.reason, txn.scan_id, now.isoformat()),
    )
    db.commit()
    db.close()
    return txn


def get_history(user_id: str, limit: int = 50) -> list[CreditTransaction]:
    """Get transaction history for a user, newest first."""
    db = _get_db()
    _ensure_user(db, user_id)

    rows = db.execute(
        "SELECT id, user_id, amount, balance_after, reason, scan_id, created_at "
        "FROM credit_transactions WHERE user_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    db.close()

    return [
        CreditTransaction(
            id=r[0], user_id=r[1], amount=r[2], balance_after=r[3],
            reason=r[4], scan_id=r[5], created_at=datetime.fromisoformat(r[6]),
        )
        for r in rows
    ]
