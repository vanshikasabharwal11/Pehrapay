import os
import sqlite3
import hmac
import hashlib
import json
import secrets
from typing import Optional
from dotenv import load_dotenv
from backend.mandates.models import SpendingMandate

# Load env variables from backend directory or current directory
load_dotenv()
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Define database path relative to project root
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "pehrapay.db")

def ensure_signing_secret():
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    root_env = os.path.join(root_dir, ".env")
    backend_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    
    secret = None
    
    # 1. Read first match from root .env
    if os.path.exists(root_env):
        with open(root_env, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("MANDATE_SIGNING_SECRET="):
                    secret = line.strip().split("=", 1)[1].strip()
                    if secret:
                        break
                        
    # 2. Read first match from backend .env if not found in root
    if not secret and os.path.exists(backend_env):
        with open(backend_env, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("MANDATE_SIGNING_SECRET="):
                    secret = line.strip().split("=", 1)[1].strip()
                    if secret:
                        break

    # 3. Fallback to process env
    if not secret:
        secret = os.getenv("MANDATE_SIGNING_SECRET")

    # 4. If key exists, ensure it is set in process memory and return
    if secret:
        os.environ["MANDATE_SIGNING_SECRET"] = secret
        return secret

    # 5. If completely absent, generate and write a single key
    secret = secrets.token_hex(32)
    if os.path.exists(root_env):
        with open(root_env, "a", encoding="utf-8") as f:
            f.write(f"\nMANDATE_SIGNING_SECRET={secret}\n")
        print(f"[ENV SETUP] Generated and added MANDATE_SIGNING_SECRET to root .env")
    else:
        with open(root_env, "w", encoding="utf-8") as f:
            f.write(f"MANDATE_SIGNING_SECRET={secret}\n")
        print(f"[ENV SETUP] Created root .env and added MANDATE_SIGNING_SECRET")

    # Mirror to backend .env if folder exists
    backend_dir = os.path.dirname(os.path.dirname(__file__))
    if os.path.exists(backend_dir):
        with open(backend_env, "a", encoding="utf-8") as f:
            f.write(f"\nMANDATE_SIGNING_SECRET={secret}\n")
            
    os.environ["MANDATE_SIGNING_SECRET"] = secret
    return secret

# Ensure key exists at load time
ensure_signing_secret()

class MandateStore:
    def __init__(self):
        os.makedirs(DB_DIR, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(DB_PATH)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if version or human_review_threshold columns are missing in existing mandates table
            cursor.execute("PRAGMA table_info(mandates)")
            columns = [col[1] for col in cursor.fetchall()]
            if len(columns) > 0 and ("version" not in columns or "human_review_threshold" not in columns):
                cursor.execute("DROP TABLE mandates")
                
            # Check PRAGMA for audit_logs migrations
            cursor.execute("PRAGMA table_info(audit_logs)")
            audit_columns = [col[1] for col in cursor.fetchall()]
            if len(audit_columns) > 0:
                if "mandate_version" not in audit_columns:
                    cursor.execute("DROP TABLE audit_logs")
                else:
                    if "order_id" not in audit_columns:
                        cursor.execute("ALTER TABLE audit_logs ADD COLUMN order_id TEXT")
                    if "payment_id" not in audit_columns:
                        cursor.execute("ALTER TABLE audit_logs ADD COLUMN payment_id TEXT")
                    if "status" not in audit_columns:
                        cursor.execute("ALTER TABLE audit_logs ADD COLUMN status TEXT")
                    if "settlement_timestamp" not in audit_columns:
                        cursor.execute("ALTER TABLE audit_logs ADD COLUMN settlement_timestamp INTEGER")
                    if "is_recommendation_accepted" not in audit_columns:
                        cursor.execute("ALTER TABLE audit_logs ADD COLUMN is_recommendation_accepted INTEGER DEFAULT 0")

            # Create Mandates Table with composite primary key (mandate_id, version)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mandates (
                    mandate_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL, -- 'active' or 'superseded'
                    purpose TEXT NOT NULL,
                    max_amount REAL NOT NULL,
                    allowed_category TEXT NOT NULL,
                    allowed_merchant_trust_level REAL NOT NULL,
                    max_transactions INTEGER NOT NULL,
                    current_transactions INTEGER DEFAULT 0,
                    expiry_timestamp INTEGER NOT NULL,
                    human_review_threshold REAL,
                    signature TEXT NOT NULL,
                    PRIMARY KEY (mandate_id, version)
                )
            """)
            
            # Create Audit Logs Table including mandate_version and settlement lifecycle fields
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    mandate_id TEXT NOT NULL,
                    mandate_version INTEGER NOT NULL,
                    buyer_request TEXT NOT NULL,
                    intent_item TEXT NOT NULL,
                    intent_price REAL NOT NULL,
                    intent_quantity INTEGER NOT NULL,
                    intent_total REAL NOT NULL,
                    intent_merchant_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    order_id TEXT,
                    payment_id TEXT,
                    status TEXT,
                    settlement_timestamp INTEGER,
                    is_recommendation_accepted INTEGER DEFAULT 0
                )
            """)
            
            # Create System Settings Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()

    def compute_signature(self, version: int, max_amount: float, allowed_category: str, 
                          allowed_merchant_trust_level: float, max_transactions: int, 
                          expiry_timestamp: int, human_review_threshold: Optional[float]) -> str:
        """
        Computes the HMAC-SHA256 signature for the mandate fields, including version and human review threshold.
        """
        secret = os.getenv("MANDATE_SIGNING_SECRET", "")
        # Serialize fields deterministically
        payload = {
            "version": int(version),
            "max_amount": float(max_amount),
            "allowed_category": allowed_category.lower(),
            "allowed_merchant_trust_level": float(allowed_merchant_trust_level),
            "max_transactions": int(max_transactions),
            "expiry_timestamp": int(expiry_timestamp),
            "human_review_threshold": float(human_review_threshold) if human_review_threshold is not None else None
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hmac.new(secret.encode("utf-8"), serialized.encode("utf-8"), hashlib.sha256).hexdigest()

    def create_mandate(self, mandate_id: str, mandate: SpendingMandate) -> dict:
        """
        Stores a SpendingMandate. If it exists, makes existing active mandate superseded, 
        bumps version, generates HMAC signature, and initializes transaction count to 0.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get current max version
            cursor.execute("SELECT MAX(version) FROM mandates WHERE mandate_id = ?", (mandate_id,))
            max_ver_row = cursor.fetchone()
            max_ver = max_ver_row[0] if max_ver_row and max_ver_row[0] is not None else 0
            
            new_version = max_ver + 1
            
            # Supersede old versions of this mandate
            cursor.execute("""
                UPDATE mandates 
                SET status = 'superseded' 
                WHERE mandate_id = ?
            """, (mandate_id,))
            
            # Compute signature with version and threshold
            signature = self.compute_signature(
                version=new_version,
                max_amount=mandate.max_amount,
                allowed_category=mandate.allowed_category,
                allowed_merchant_trust_level=mandate.allowed_merchant_trust_level,
                max_transactions=mandate.max_transactions,
                expiry_timestamp=mandate.expiry_timestamp,
                human_review_threshold=mandate.human_review_threshold
            )
            
            # Insert new active version
            cursor.execute("""
                INSERT INTO mandates (
                    mandate_id, version, status, purpose, max_amount, allowed_category, 
                    allowed_merchant_trust_level, max_transactions, 
                    current_transactions, expiry_timestamp, human_review_threshold, signature
                ) VALUES (?, ?, 'active', ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """, (
                mandate_id,
                new_version,
                mandate.purpose,
                mandate.max_amount,
                mandate.allowed_category,
                mandate.allowed_merchant_trust_level,
                mandate.max_transactions,
                mandate.expiry_timestamp,
                mandate.human_review_threshold,
                signature
            ))
            conn.commit()
            
        return self.get_mandate(mandate_id, new_version)

    def get_mandate(self, mandate_id: str, version: Optional[int] = None) -> Optional[dict]:
        """
        Retrieves a mandate by its ID. If version is specified, retrieves that specific version.
        Otherwise, retrieves the currently active version.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if version is not None:
                cursor.execute("SELECT * FROM mandates WHERE mandate_id = ? AND version = ?", (mandate_id, version))
            else:
                cursor.execute("SELECT * FROM mandates WHERE mandate_id = ? AND status = 'active'", (mandate_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "mandate_id": row[0],
                "version": row[1],
                "status": row[2],
                "purpose": row[3],
                "max_amount": row[4],
                "allowed_category": row[5],
                "allowed_merchant_trust_level": row[6],
                "max_transactions": row[7],
                "current_transactions": row[8],
                "expiry_timestamp": row[9],
                "human_review_threshold": row[10],
                "signature": row[11]
            }

    def increment_transaction_count(self, mandate_id: str, version: Optional[int] = None) -> bool:
        """
        Increments the transaction count for a mandate (active or specific version).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if version is not None:
                cursor.execute("""
                    UPDATE mandates 
                    SET current_transactions = current_transactions + 1 
                    WHERE mandate_id = ? AND version = ?
                """, (mandate_id, version))
            else:
                cursor.execute("""
                    UPDATE mandates 
                    SET current_transactions = current_transactions + 1 
                    WHERE mandate_id = ? AND status = 'active'
                """, (mandate_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_spent_amount(self, mandate_id: str, version: Optional[int] = None) -> float:
        """
        Calculates total reserved/spent amount (sum of intent_total for APPROVED transactions) for a mandate version.

        NOTE ON BUDGET TIMING:
        Budget reservation occurs at AUTHORIZATION time (when decision == 'APPROVE') to prevent 
        concurrent agent requests from exceeding the cumulative cap before settlement completes.
        Once the transaction is settled via webhook, its status transitions to 'PAID_SETTLED' 
        without altering the reserved budget total (preventing double-deduction).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if version is not None:
                cursor.execute("""
                    SELECT SUM(intent_total) FROM audit_logs 
                    WHERE mandate_id = ? AND mandate_version = ? AND decision = 'APPROVE'
                """, (mandate_id, version))
            else:
                cursor.execute("""
                    SELECT SUM(intent_total) FROM audit_logs 
                    WHERE mandate_id = ? AND decision = 'APPROVE'
                """, (mandate_id,))
            row = cursor.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0

    def log_audit(self, timestamp: int, mandate_id: str, buyer_request: str, 
                  intent: dict, decision: str, reason: str, mandate_version: Optional[int] = None,
                  order_id: Optional[str] = None, payment_id: Optional[str] = None,
                  status: Optional[str] = None, settlement_timestamp: Optional[int] = None,
                  is_recommendation_accepted: bool = False) -> int:
        """
        Appends a record to the policy audit log. Returns the inserted log_id.
        """
        if mandate_version is None:
            # Try to resolve currently active version
            mandate = self.get_mandate(mandate_id)
            mandate_version = mandate["version"] if mandate else 1
            
        intent_total = intent.get("price", 0.0) * intent.get("quantity", 0)
        rec_acc_int = 1 if is_recommendation_accepted else 0
        final_status = status or ("AUTHORIZED" if decision == "APPROVE" else ("SUSPENDED" if decision == "HUMAN_REVIEW" else "BLOCKED"))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_logs (
                    timestamp, mandate_id, mandate_version, buyer_request, intent_item, 
                    intent_price, intent_quantity, intent_total, 
                    intent_merchant_id, decision, reason,
                    order_id, payment_id, status, settlement_timestamp, is_recommendation_accepted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                mandate_id,
                mandate_version,
                buyer_request,
                intent.get("item", ""),
                intent.get("price", 0.0),
                intent.get("quantity", 0),
                intent_total,
                intent.get("merchant_id", ""),
                decision,
                reason,
                order_id,
                payment_id,
                final_status,
                settlement_timestamp,
                rec_acc_int
            ))
            conn.commit()
            return cursor.lastrowid

    def get_audit_log_by_order_id(self, order_id: str) -> Optional[dict]:
        """
        Retrieves a single audit log entry by Razorpay order_id.
        """
        if not order_id:
            return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audit_logs WHERE order_id = ? ORDER BY log_id DESC LIMIT 1", (order_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "log_id": row[0],
                "timestamp": row[1],
                "mandate_id": row[2],
                "mandate_version": row[3],
                "buyer_request": row[4],
                "intent_item": row[5],
                "intent_price": row[6],
                "intent_quantity": row[7],
                "intent_total": row[8],
                "intent_merchant_id": row[9],
                "decision": row[10],
                "reason": row[11],
                "order_id": row[12] if len(row) > 12 else None,
                "payment_id": row[13] if len(row) > 13 else None,
                "status": row[14] if len(row) > 14 else (row[10] if len(row) > 10 else None),
                "settlement_timestamp": row[15] if len(row) > 15 else None,
                "is_recommendation_accepted": bool(row[16]) if len(row) > 16 else False
            }

    def update_transaction_settlement(self, order_id: str, payment_id: str, settlement_timestamp: int) -> Optional[dict]:
        """
        Idempotently updates an order's status from AUTHORIZED to PAID_SETTLED.
        Returns the updated transaction dict, or None if order_id is not found.
        """
        record = self.get_audit_log_by_order_id(order_id)
        if not record:
            return None

        # Idempotency: If already settled, return existing record without double-deduction or state corruption
        if record.get("status") == "PAID_SETTLED":
            return record

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE audit_logs 
                SET status = 'PAID_SETTLED', payment_id = ?, settlement_timestamp = ?
                WHERE order_id = ?
            """, (payment_id, settlement_timestamp, order_id))
            conn.commit()

        return self.get_audit_log_by_order_id(order_id)

    def get_analytics_summary(self) -> dict:
        """
        Computes real live-session analytics strictly from SQLite audit_logs table.
        Zero fabricated metrics — every field derives directly from query results.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Total Requests
            cursor.execute("SELECT COUNT(*) FROM audit_logs")
            total_requests = cursor.fetchone()[0] or 0
            
            # 2. Approved Count & Total Approved GMV
            cursor.execute("SELECT COUNT(*), SUM(intent_total) FROM audit_logs WHERE decision = 'APPROVE'")
            app_row = cursor.fetchone()
            approved_count = app_row[0] or 0
            total_approved_value = float(app_row[1] or 0.0)
            
            # 3. Settled Count & Total Settled Value
            cursor.execute("SELECT COUNT(*), SUM(intent_total) FROM audit_logs WHERE status = 'PAID_SETTLED'")
            set_row = cursor.fetchone()
            settled_count = set_row[0] or 0
            total_settled_value = float(set_row[1] or 0.0)
            
            # 4. Rejected Count
            cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE decision = 'REJECT'")
            rejected_count = cursor.fetchone()[0] or 0
            
            # 5. Recommendation Acceptance Count
            cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE is_recommendation_accepted = 1")
            rec_accepted_count = cursor.fetchone()[0] or 0
            
            # 6. Distinct Merchants with Approved Transactions
            cursor.execute("SELECT COUNT(DISTINCT intent_merchant_id) FROM audit_logs WHERE decision = 'APPROVE' AND intent_merchant_id != ''")
            distinct_merchants_count = cursor.fetchone()[0] or 0
            
            # Real calculated rates
            approval_rate = round((approved_count / total_requests) * 100, 1) if total_requests > 0 else 0.0
            rec_acceptance_rate = round((rec_accepted_count / approved_count) * 100, 1) if approved_count > 0 else 0.0
            
            return {
                "total_requests": total_requests,
                "approved_count": approved_count,
                "total_approved_value": total_approved_value,
                "settled_count": settled_count,
                "total_settled_value": total_settled_value,
                "rejected_count": rejected_count,
                "approval_rate": approval_rate,
                "rec_accepted_count": rec_accepted_count,
                "rec_acceptance_rate": rec_acceptance_rate,
                "distinct_merchants_count": distinct_merchants_count
            }

    def get_audit_logs(self, mandate_id: Optional[str] = None) -> list:
        """
        Retrieves audit logs, optionally filtered by mandate_id.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if mandate_id:
                cursor.execute("SELECT * FROM audit_logs WHERE mandate_id = ? ORDER BY timestamp DESC", (mandate_id,))
            else:
                cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC")
            
            logs = []
            for row in cursor.fetchall():
                logs.append({
                    "log_id": row[0],
                    "timestamp": row[1],
                    "mandate_id": row[2],
                    "mandate_version": row[3],
                    "buyer_request": row[4],
                    "intent_item": row[5],
                    "intent_price": row[6],
                    "intent_quantity": row[7],
                    "intent_total": row[8],
                    "intent_merchant_id": row[9],
                    "decision": row[10],
                    "reason": row[11],
                    "order_id": row[12] if len(row) > 12 else None,
                    "payment_id": row[13] if len(row) > 13 else None,
                    "status": row[14] if len(row) > 14 and row[14] else (row[10] if len(row) > 10 else None),
                    "settlement_timestamp": row[15] if len(row) > 15 else None,
                    "is_recommendation_accepted": bool(row[16]) if len(row) > 16 else False
                })
            return logs

    def is_agent_paused(self) -> bool:
        """
        Returns True if the system is currently in emergency paused state.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_settings WHERE key = 'agent_paused'")
            row = cursor.fetchone()
            if not row:
                return False
            return row[0] == "true"

    def set_agent_paused(self, paused: bool):
        """
        Sets the global emergency paused state in the SQLite settings table.
        """
        val_str = "true" if paused else "false"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM system_settings WHERE key = 'agent_paused'")
            cursor.execute("INSERT INTO system_settings (key, value) VALUES ('agent_paused', ?)", (val_str,))
            conn.commit()
