import sys

from db import ensure_warning_score_columns, ensure_warning_unique_key, get_connection
from repository import fetch_all, fetch_one


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    ensure_warning_score_columns()
    before = fetch_one("SELECT COUNT(*) AS count FROM warnings")["count"]
    duplicate_groups = fetch_all(
        """
        SELECT title, risk_type, COUNT(*) AS count, MAX(id) AS keep_id
        FROM warnings
        GROUP BY title, risk_type
        HAVING COUNT(*) > 1
        """
    )

    deleted = 0
    with get_connection() as connection:
        with connection.cursor() as cursor:
            for group in duplicate_groups:
                cursor.execute(
                    """
                    DELETE FROM warnings
                    WHERE title = %s AND risk_type = %s AND id <> %s
                    """,
                    (group["title"], group["risk_type"], group["keep_id"]),
                )
                deleted += cursor.rowcount

    ensure_warning_unique_key()
    after = fetch_one("SELECT COUNT(*) AS count FROM warnings")["count"]

    print("预警重复记录清理完成")
    print(f"清理前: {before}")
    print(f"删除重复: {deleted}")
    print(f"清理后: {after}")


if __name__ == "__main__":
    main()
