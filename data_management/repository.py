from typing import Any

from db import ensure_price_scope_columns, ensure_warning_score_columns, ensure_warning_unique_key, get_connection


def _execute_many(sql: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    with get_connection() as connection:
        with connection.cursor() as cursor:
            return cursor.executemany(sql, rows)


def clear_demo_data() -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM warnings")
            cursor.execute("DELETE FROM product_prices")
            cursor.execute("DELETE FROM news")


def insert_news(rows: list[dict]) -> int:
    sql = """
    INSERT INTO news
      (title, content, source, publish_time, url, region, category, summary, keywords)
    VALUES
      (%(title)s, %(content)s, %(source)s, %(publish_time)s, %(url)s, %(region)s,
       %(category)s, %(summary)s, %(keywords)s)
    ON DUPLICATE KEY UPDATE
      content = VALUES(content),
      source = VALUES(source),
      publish_time = VALUES(publish_time),
      region = VALUES(region),
      category = VALUES(category),
      summary = VALUES(summary),
      keywords = VALUES(keywords)
    """
    return _execute_many(sql, rows)


def insert_prices(rows: list[dict]) -> int:
    ensure_price_scope_columns()
    rows = [
        {
            "province": "",
            "city": "",
            "market_name": "",
            "source_level": "",
            "source_url": "",
            **row,
        }
        for row in rows
    ]
    sql = """
    INSERT INTO product_prices
      (product_name, price, unit, region, province, city, market_name, source_level, date, source, source_url)
    VALUES
      (%(product_name)s, %(price)s, %(unit)s, %(region)s, %(province)s, %(city)s,
       %(market_name)s, %(source_level)s, %(date)s, %(source)s, %(source_url)s)
    ON DUPLICATE KEY UPDATE
      price = VALUES(price),
      unit = VALUES(unit),
      province = VALUES(province),
      city = VALUES(city),
      market_name = VALUES(market_name),
      source_level = VALUES(source_level),
      source_url = VALUES(source_url)
    """
    return _execute_many(sql, rows)


def prune_news(limit: int = 50) -> int:
    if limit <= 0:
        return 0

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, url
                FROM news
                ORDER BY id DESC
                LIMIT 18446744073709551615 OFFSET %s
                """,
                (limit,),
            )
            old_rows = list(cursor.fetchall())
            if not old_rows:
                return 0

            old_ids = [row["id"] for row in old_rows]
            old_urls = [row["url"] for row in old_rows if row.get("url")]

            if old_urls:
                placeholders = ", ".join(["%s"] * len(old_urls))
                cursor.execute(f"DELETE FROM warnings WHERE url IN ({placeholders})", tuple(old_urls))

            placeholders = ", ".join(["%s"] * len(old_ids))
            cursor.execute(f"DELETE FROM news WHERE id IN ({placeholders})", tuple(old_ids))
            return cursor.rowcount


def prune_prices(limit: int = 50) -> int:
    if limit <= 0:
        return 0

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM product_prices
                ORDER BY id DESC
                LIMIT 18446744073709551615 OFFSET %s
                """,
                (limit,),
            )
            old_ids = [row["id"] for row in cursor.fetchall()]
            if not old_ids:
                return 0

            placeholders = ", ".join(["%s"] * len(old_ids))
            cursor.execute(f"DELETE FROM product_prices WHERE id IN ({placeholders})", tuple(old_ids))
            return cursor.rowcount


def insert_warnings(rows: list[dict]) -> int:
    ensure_warning_score_columns()
    ensure_warning_unique_key()
    rows = [
        {
            "local_match_score": 0,
            "source_score": 0,
            "evidence_score": 0,
            "confidence": 0,
            "evidence_summary": "",
            "evidence_links": "",
            **row,
        }
        for row in rows
    ]
    sql = """
    INSERT INTO warnings
      (title, region, product, risk_type, risk_score, risk_level, keyword_score,
       price_score, heat_score, region_score, local_match_score, source_score,
       evidence_score, confidence, positive_adjustment, trigger_words, evidence_summary, evidence_links, reason,
       suggestion, source, category, url)
    VALUES
      (%(title)s, %(region)s, %(product)s, %(risk_type)s, %(risk_score)s,
       %(risk_level)s, %(keyword_score)s, %(price_score)s, %(heat_score)s,
       %(region_score)s, %(local_match_score)s, %(source_score)s, %(evidence_score)s,
       %(confidence)s, %(positive_adjustment)s, %(trigger_words)s, %(evidence_summary)s,
       %(evidence_links)s,
       %(reason)s, %(suggestion)s, %(source)s, %(category)s, %(url)s)
    ON DUPLICATE KEY UPDATE
      title = VALUES(title),
      region = VALUES(region),
      product = VALUES(product),
      risk_score = VALUES(risk_score),
      risk_level = VALUES(risk_level),
      keyword_score = VALUES(keyword_score),
      price_score = VALUES(price_score),
      heat_score = VALUES(heat_score),
      region_score = VALUES(region_score),
      local_match_score = VALUES(local_match_score),
      source_score = VALUES(source_score),
      evidence_score = VALUES(evidence_score),
      confidence = VALUES(confidence),
      positive_adjustment = VALUES(positive_adjustment),
      trigger_words = VALUES(trigger_words),
      evidence_summary = VALUES(evidence_summary),
      evidence_links = VALUES(evidence_links),
      reason = VALUES(reason),
      suggestion = VALUES(suggestion),
      source = VALUES(source),
      category = VALUES(category),
      url = VALUES(url)
    """
    return _execute_many(sql, rows)


def update_warning_score_parts(rows: list[dict]) -> int:
    ensure_warning_score_columns()
    sql = """
    UPDATE warnings
    SET risk_score = %(risk_score)s,
        risk_level = %(risk_level)s,
        keyword_score = %(keyword_score)s,
        price_score = %(price_score)s,
        heat_score = %(heat_score)s,
        region_score = %(region_score)s,
        local_match_score = %(local_match_score)s,
        source_score = %(source_score)s,
        evidence_score = %(evidence_score)s,
        confidence = %(confidence)s,
        positive_adjustment = %(positive_adjustment)s,
        trigger_words = %(trigger_words)s,
        evidence_summary = %(evidence_summary)s,
        evidence_links = %(evidence_links)s
    WHERE id = %(id)s
    """
    return _execute_many(sql, rows)


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())


def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()
