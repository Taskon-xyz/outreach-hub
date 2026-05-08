#!/usr/bin/env python3
"""
测试清洗脚本的功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
import sqlite3

def backup_database():
    """备份数据库"""
    import shutil
    import datetime

    source = db.DB_PATH
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{source}.backup_{timestamp}"

    shutil.copy2(source, backup)
    print(f"数据库已备份到: {backup}")
    return backup

def test_delete_bots():
    """测试删除bot功能"""
    print("测试删除bot功能...")

    # 先统计bot数量
    conn = sqlite3.connect(db.DB_PATH)
    cursor = conn.execute("SELECT COUNT(*) FROM tg_handles WHERE LOWER(username) LIKE '%bot'")
    tg_bots = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(*) FROM tg_left_users WHERE LOWER(username) LIKE '%bot'")
    left_bots = cursor.fetchone()[0]

    print(f"当前bot数量: tg_handles={tg_bots}, tg_left_users={left_bots}")

    # 执行删除
    total_deleted, tg_deleted, left_deleted = db.delete_bot_handles()

    print(f"删除bot结果: 总计={total_deleted}, tg_handles={tg_deleted}, tg_left_users={left_deleted}")

    # 验证删除
    cursor = conn.execute("SELECT COUNT(*) FROM tg_handles WHERE LOWER(username) LIKE '%bot'")
    tg_remaining = cursor.fetchone()[0]

    cursor = conn.execute("SELECT COUNT(*) FROM tg_left_users WHERE LOWER(username) LIKE '%bot'")
    left_remaining = cursor.fetchone()[0]

    print(f"删除后剩余bot: tg_handles={tg_remaining}, tg_left_users={left_remaining}")

    conn.close()

    return total_deleted > 0

def main():
    print("测试清洗脚本")
    print("=" * 50)

    # 1. 备份数据库
    backup_path = backup_database()
    print()

    # 2. 测试删除bot
    bots_deleted = test_delete_bots()

    if bots_deleted:
        print("\n✅ Bot删除测试成功")
    else:
        print("\n⚠️  未发现bot用户")

    print(f"\n数据库备份在: {backup_path}")
    print("如需恢复，请复制备份文件覆盖原文件。")

if __name__ == "__main__":
    main()