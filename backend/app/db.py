"""SQLite 连接与建表。符号表缓存、分析任务与结果缓存共用同一个库文件。"""
import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).resolve().parent.parent / "data.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS symbols (
    market     TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    name       TEXT NOT NULL,
    alt_name   TEXT,
    PRIMARY KEY (market, symbol)
);
CREATE TABLE IF NOT EXISTS symbols_meta (
    market     TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    task_id    TEXT PRIMARY KEY,
    cache_key  TEXT NOT NULL,
    request    TEXT NOT NULL,
    status     TEXT NOT NULL,
    result     TEXT,
    error      TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_cache_key ON tasks(cache_key, status);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn
