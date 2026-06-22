"""清理 report_metadata 中的假报告数据.

Seed 脚本插入的报告记录使用指向 /reports/ 目录（系统根目录）的 file_path，
这些文件实际上不存在。此脚本删除这些假记录。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)


def main():
    db = Session()
    try:
        # Find fake reports: file_path starts with '/reports/' but file doesn't exist
        result = db.execute(
            text("""
                SELECT id, report_type, report_date, file_path, status
                FROM report_metadata
                WHERE file_path LIKE '/reports/%'
            """)
        ).fetchall()

        if not result:
            print("✅ No fake report records found")
            return

        print(f"🗑️ Found {len(result)} fake report records:")
        for r in result:
            print(f"   #{r[0]} {r[1]} ({r[2]}) | {r[3]} | {r[4]}")

        # Delete them
        db.execute(text("DELETE FROM report_metadata WHERE file_path LIKE '/reports/%'"))
        db.commit()
        print(f"✅ Deleted {len(result)} fake report records")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
