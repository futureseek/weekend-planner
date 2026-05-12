import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "route_planner.db")


def get_db_path() -> str:
    return DB_PATH


def init_db():
    """初始化数据库，创建表结构"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = f.read()

    with get_connection() as conn:
        conn.executescript(schema)


@contextmanager
def get_connection():
    """获取数据库连接的上下文管理器"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_query(sql: str, params: tuple = ()) -> list[dict]:
    """执行查询，返回字典列表"""
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def execute_one(sql: str, params: tuple = ()) -> dict | None:
    """执行查询，返回单条记录"""
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None


def execute_write(sql: str, params: tuple = ()) -> int:
    """执行写操作，返回影响行数"""
    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        return cursor.rowcount


def execute_many(sql: str, params_list: list[tuple]) -> int:
    """批量执行写操作"""
    with get_connection() as conn:
        cursor = conn.executemany(sql, params_list)
        return cursor.rowcount
