import sys
import argparse
from pathlib import Path

_CURRENT_DIR = Path(__file__).resolve().parent
if str(_CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CURRENT_DIR))

from db import initialize_schema  # noqa: E402


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize MySQL schema for the agri warning project.")
    parser.add_argument(
        "--reset-demo",
        action="store_true",
        help="Clear existing data and rebuild demo records from bundled CSV files.",
    )
    args = parser.parse_args()

    initialize_schema()
    print("MySQL 数据表结构检查完成，已有业务数据已保留。")

    if args.reset_demo:
        from pipeline import rebuild_from_demo_data  # noqa: E402

        result = rebuild_from_demo_data(clear_first=True)
        print("演示数据已重建，原有新闻、价格和预警已清空。")
        print(f"新闻入库: {result['news']}")
        print(f"价格入库: {result['prices']}")
        print(f"预警入库: {result['warnings']}")


if __name__ == "__main__":
    main()

