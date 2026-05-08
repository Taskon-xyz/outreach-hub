#!/usr/bin/env python3
"""
测试 Telegram API 连接和用户状态检查
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db

async def test_telegram_client():
    """测试 Telegram 客户端连接"""
    try:
        from telethon import TelegramClient
        print("导入 telethon 成功")
    except ImportError:
        print("错误: 请安装 telethon: pip install telethon")
        return

    # 获取凭证
    api_id, api_hash, session = db.get_tg_credentials("parser")
    print(f"API ID: {api_id}")
    print(f"API Hash: {api_hash[:10]}...")
    print(f"Session: {session}")

    # 初始化客户端
    client = TelegramClient(session, api_id, api_hash)

    try:
        await client.start()
        print("Telegram 客户端启动成功")

        # 测试获取自己的信息
        me = await client.get_me()
        print(f"当前用户: {me.first_name} (@{me.username})")

        # 测试获取几个用户
        test_usernames = ["telegram", "durov"]  # 已知存在的用户

        for username in test_usernames:
            try:
                user = await client.get_entity(username)
                print(f"\n用户: @{username}")
                print(f"  ID: {user.id}")
                print(f"  姓名: {user.first_name or ''} {user.last_name or ''}")

                if hasattr(user, 'status'):
                    status = user.status
                    print(f"  状态类型: {type(status).__name__}")

                    # 检查具体状态
                    from telethon.tl.types import (
                        UserStatusLastMonth, UserStatusLastWeek, UserStatusRecently,
                        UserStatusOnline, UserStatusOffline, UserStatusEmpty
                    )

                    if isinstance(status, UserStatusOffline):
                        if hasattr(status, 'was_online'):
                            print(f"  最后在线: {status.was_online}")
                    elif isinstance(status, UserStatusOnline):
                        print(f"  在线: {status.expires}")
                    else:
                        print(f"  状态: {status}")
                else:
                    print("  无状态信息")

            except Exception as e:
                print(f"  获取用户 @{username} 失败: {e}")

            await asyncio.sleep(2)  # 延迟

        # 测试检查函数
        print("\n" + "="*50)
        print("测试检查函数...")

        from telethon.tl.types import UserStatusLastMonth

        # 创建一个模拟的 UserStatusLastMonth 对象
        class MockStatus:
            pass

        mock_status = MockStatus()
        mock_status.__class__ = UserStatusLastMonth

        # 模拟用户对象
        class MockUser:
            def __init__(self, username, status):
                self.username = username
                self.status = status

        mock_user = MockUser("testuser", mock_status)

        print(f"测试 UserStatusLastMonth 检测: 应返回 True")
        print(f"类型检查: {isinstance(mock_status, UserStatusLastMonth)}")

    except Exception as e:
        print(f"客户端错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()
        print("\n客户端已断开连接")

def main():
    asyncio.run(test_telegram_client())

if __name__ == "__main__":
    main()