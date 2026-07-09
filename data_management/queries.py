from repository import fetch_all, fetch_one


def list_news(keyword: str = "", category: str = "", region: str = "", limit: int = 20, offset: int = 0):
    sql = "SELECT * FROM news WHERE 1=1"
    params = []
    if keyword:
        sql += " AND (title LIKE %s OR content LIKE %s OR keywords LIKE %s)"
        like = f"%{keyword}%"
        params.extend([like, like, like])
    if category:
        sql += " AND category = %s"
        params.append(category)
    if region:
        sql += " AND region LIKE %s"
        params.append(f"%{region}%")
    sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    return fetch_all(sql, tuple(params))


def get_news(news_id: int):
    return fetch_one("SELECT * FROM news WHERE id = %s", (news_id,))


def list_warnings(risk_level: str = "", region: str = "", product: str = "", limit: int = 20):
    sql = "SELECT * FROM warnings WHERE 1=1"
    params = []
    if risk_level:
        sql += " AND risk_level = %s"
        params.append(risk_level)
    if region:
        sql += " AND region LIKE %s"
        params.append(f"%{region}%")
    if product:
        sql += " AND product LIKE %s"
        params.append(f"%{product}%")
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(limit)
    return fetch_all(sql, tuple(params))


def get_warning(warning_id: int):
    return fetch_one("SELECT * FROM warnings WHERE id = %s", (warning_id,))


def list_prices(product_name: str = "", region: str = "", city: str = ""):
    where_sql = "WHERE 1=1"
    params = []
    if product_name:
        where_sql += " AND product_name = %s"
        params.append(product_name)
    if city:
        where_sql += " AND TRIM(city) = %s"
        params.append(city)
    if region:
        where_sql += " AND region LIKE %s"
        params.append(f"%{region}%")
    area_expr = "TRIM(city)" if city else "COALESCE(NULLIF(TRIM(city), ''), region)"
    sql = f"""
    SELECT p.id, p.product_name, p.price, p.unit,
           COALESCE(NULLIF(TRIM(p.city), ''), p.region) AS region,
           p.province, p.city, p.market_name, p.source_level,
           LEFT(p.date, 10) AS date, p.source, p.source_url, p.created_at
    FROM product_prices p
    JOIN (
      SELECT product_name, {area_expr} AS area, LEFT(date, 10) AS day_label, MAX(id) AS id
      FROM product_prices
      {where_sql}
      GROUP BY product_name, {area_expr}, LEFT(date, 10)
    ) latest ON p.id = latest.id
    ORDER BY latest.day_label DESC, p.id DESC
    """
    return fetch_all(sql, tuple(params))


def overview_stats():
    return {
        "news_count": fetch_one("SELECT COUNT(*) AS count FROM news")["count"],
        "today_news_count": fetch_one(
            "SELECT COUNT(*) AS count FROM news WHERE DATE(created_at) = CURDATE()"
        )["count"],
        "warning_count": fetch_one("SELECT COUNT(*) AS count FROM warnings")["count"],
        "high_warning_count": fetch_one(
            "SELECT COUNT(*) AS count FROM warnings WHERE risk_level IN ('较高风险', '高风险')"
        )["count"],
        "price_count": fetch_one("SELECT COUNT(*) AS count FROM product_prices")["count"],
    }


def category_chart():
    return fetch_all(
        "SELECT category AS name, COUNT(*) AS value FROM news GROUP BY category ORDER BY value DESC"
    )


def price_trend(product_name: str = "", city: str = ""):
    params = []
    if city:
        where_sql = "WHERE TRIM(city) = %s"
        params.append(city)
        if product_name:
            where_sql += " AND product_name = %s"
            params.append(product_name)
        sql = f"""
        SELECT p.product_name, p.city AS region, LEFT(p.date, 10) AS date, p.price, p.unit, p.source_url
        FROM product_prices p
        JOIN (
          SELECT product_name, city, LEFT(date, 10) AS day_label, MAX(id) AS id
          FROM product_prices
          {where_sql}
          GROUP BY product_name, city, LEFT(date, 10)
        ) latest ON p.id = latest.id
        ORDER BY p.product_name, p.city, latest.day_label
        """
        return fetch_all(sql, tuple(params))

    where_sql = "WHERE 1=1"
    if product_name:
        where_sql += " AND product_name = %s"
        params.append(product_name)

    sql = f"""
    SELECT product_name, '河南' AS region, day_label AS date, ROUND(AVG(price), 2) AS price, MAX(unit) AS unit
    FROM (
      SELECT p.product_name, COALESCE(NULLIF(p.city, ''), p.region) AS area,
             LEFT(p.date, 10) AS day_label, p.price, p.unit
      FROM product_prices p
      JOIN (
        SELECT product_name, COALESCE(NULLIF(city, ''), region) AS area, LEFT(date, 10) AS day_label, MAX(id) AS id
        FROM product_prices
        {where_sql}
        GROUP BY product_name, COALESCE(NULLIF(city, ''), region), LEFT(date, 10)
      ) latest ON p.id = latest.id
    ) daily_city_prices
    GROUP BY product_name, day_label
    ORDER BY product_name, day_label
    """
    return fetch_all(sql, tuple(params))


def hotwords_chart(limit: int = 20):
    rows = fetch_all("SELECT keywords FROM news WHERE keywords IS NOT NULL AND keywords <> ''")
    counts = {}
    for row in rows:
        for word in row["keywords"].split("、"):
            word = word.strip()
            if not word:
                continue
            counts[word] = counts.get(word, 0) + 1
    return [
        {"name": word, "value": count}
        for word, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]
