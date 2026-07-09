from contextlib import contextmanager
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor

from config import DB_CONFIG, DatabaseConfig


SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def connect(config: DatabaseConfig = DB_CONFIG, with_database: bool = True):
    database = config.database if with_database else None
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=database,
        charset=config.charset,
        cursorclass=DictCursor,
        autocommit=False,
    )


@contextmanager
def get_connection():
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_schema() -> None:
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
    connection = connect(with_database=False)
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    ensure_warning_score_columns()
    ensure_price_scope_columns()
    ensure_warning_unique_key()


def ensure_warning_score_columns() -> None:
    columns = {
        "keyword_score": "DECIMAL(5, 1) DEFAULT 0",
        "price_score": "DECIMAL(5, 1) DEFAULT 0",
        "heat_score": "DECIMAL(5, 1) DEFAULT 0",
        "region_score": "DECIMAL(5, 1) DEFAULT 0",
        "local_match_score": "DECIMAL(5, 1) DEFAULT 0",
        "source_score": "DECIMAL(5, 1) DEFAULT 0",
        "evidence_score": "DECIMAL(5, 1) DEFAULT 0",
        "confidence": "DECIMAL(5, 1) DEFAULT 0",
        "positive_adjustment": "DECIMAL(5, 1) DEFAULT 0",
        "evidence_summary": "VARCHAR(500)",
        "evidence_links": "TEXT",
    }
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'warnings'
                """,
                (DB_CONFIG.database,),
            )
            existing = {row["COLUMN_NAME"] for row in cursor.fetchall()}
            for name, definition in columns.items():
                if name not in existing:
                    cursor.execute(f"ALTER TABLE warnings ADD COLUMN {name} {definition}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def ensure_price_scope_columns() -> None:
    columns = {
        "province": "VARCHAR(100)",
        "city": "VARCHAR(100)",
        "market_name": "VARCHAR(100)",
        "source_level": "VARCHAR(50)",
        "source_url": "VARCHAR(500)",
    }
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'product_prices'
                """,
                (DB_CONFIG.database,),
            )
            existing = {row["COLUMN_NAME"] for row in cursor.fetchall()}
            for name, definition in columns.items():
                if name not in existing:
                    cursor.execute(f"ALTER TABLE product_prices ADD COLUMN {name} {definition}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def ensure_warning_unique_key() -> None:
    connection = connect()
    try:
        with connection.cursor() as cursor:
            for index_name, columns in {
                "uk_warning_url_type": "url, risk_type",
                "uk_warning_title_type": "title, risk_type",
            }.items():
                cursor.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM INFORMATION_SCHEMA.STATISTICS
                    WHERE TABLE_SCHEMA = %s
                      AND TABLE_NAME = 'warnings'
                      AND INDEX_NAME = %s
                    """,
                    (DB_CONFIG.database, index_name),
                )
                exists = cursor.fetchone()["count"] > 0
                if not exists:
                    cursor.execute(f"ALTER TABLE warnings ADD UNIQUE KEY {index_name} ({columns})")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
