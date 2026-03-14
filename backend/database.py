import sqlite3
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentinelpay.db")

DB_PATH = os.getenv("DB_PATH", "sentinelpay.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS agent_wallets (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        balance REAL NOT NULL DEFAULT 0,
        spend_limit REAL NOT NULL DEFAULT 500,
        weekly_limit REAL NOT NULL DEFAULT 2000,
        current_weekly_spend REAL DEFAULT 0,
        is_frozen INTEGER DEFAULT 0,
        frozen_reason TEXT,
        low_balance_threshold REAL DEFAULT 200,
        blocked_categories TEXT DEFAULT '[]',
        allowed_hours TEXT DEFAULT '{"start": 0, "end": 24}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id TEXT PRIMARY KEY,
        wallet_id TEXT NOT NULL,
        amount REAL NOT NULL,
        merchant TEXT,
        merchant_domain TEXT,
        description TEXT,
        category TEXT,
        status TEXT DEFAULT 'pending',
        risk_score REAL,
        risk_reasons TEXT DEFAULT '[]',
        merchant_score REAL,
        behavior_score REAL,
        policy_score REAL,
        pine_order_id TEXT,
        triggered_by TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(wallet_id) REFERENCES agent_wallets(id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        previous_hash TEXT NOT NULL,
        hash TEXT NOT NULL UNIQUE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS hitl_approvals (
        id TEXT PRIMARY KEY,
        transaction_id TEXT,
        wallet_id TEXT,
        status TEXT DEFAULT 'pending',
        payment_context TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP,
        resolved_by TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ai_analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        threat_level TEXT,
        findings TEXT,
        anomalies TEXT,
        remediations TEXT,
        backend TEXT,
        entry_count INTEGER
    )
    ''')

    conn.commit()
    conn.close()
    logger.info("Database initialized with all tables.")
