#!/usr/bin/env python3
"""
清洗 tg_handles 和 tg_left_users 表：
1. 删除所有以 "bot" 结尾的 handle（不区分大小写）
2. 通过 Telegram API 查询最后在线时间，删除超过一个月不活跃的 handle
"""
import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Set, Tuple, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clean_tg_handles.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_all_handles() -> Tuple[Set[str], Set[str]]:
    """从两个表中获取所有唯一的用户名"""
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row

    tg_handles = set()
    tg_left_handles = set()

    try:
        # 从 tg_handles 获取
        cursor = conn.execute("SELECT username FROM tg_handles")
        for row in cursor:
            if row['username']:
                tg_handles.add(row['username'].strip())

        # 从 tg_left_users 获取
        cursor = conn.execute("SELECT username FROM tg_left_users")
        for row in cursor:
            if row['username']:
                tg_left_handles.add(row['username'].strip())

    finally:
        conn.close()

    logger.info(f"从 tg_handles 获取 {len(tg_handles)} 个唯一用户名")
    logger.info(f"从 tg_left_users 获取 {len(tg_left_handles)} 个唯一用户名")

    return tg_handles, tg_left_handles


def filter_bot_handles(handles: Set[str]) -> Set[str]:
    """过滤掉以 'bot' 结尾的 handle（不区分大小写）"""
    filtered = {h for h in handles if not h.lower().endswith('bot')}
    removed = len(handles) - len(filtered)
    logger.info(f"过滤掉 {removed} 个以 'bot' 结尾的 handle")
    return filtered


async def check_user_inactive(client, username: str) -> Tuple[bool, str]:
    """
    检查用户是否不活跃
    返回: (是否不活跃, 原因)
    """
    try:
        # 获取用户实体
        user = await client.get_entity(username)

        # 检查用户状态
        if not hasattr(user, 'status'):
            return False, "无状态信息（可能是机器人或频道）"

        status = user.status

        # 导入状态类型
        from telethon.tl.types import (
            UserStatusLastMonth, UserStatusLastWeek, UserStatusRecently,
            UserStatusOnline, UserStatusOffline, UserStatusEmpty
        )

        # 检查状态类型
        if isinstance(status, UserStatusLastMonth):
            return True, "最后在线时间 > 1个月前"

        elif isinstance(status, UserStatusOffline):
            if hasattr(status, 'was_online'):
                # 计算离线时间
                was_online = status.was_online
                if isinstance(was_online, datetime):
                    offline_days = (datetime.now(was_online.tzinfo) - was_online).days
                    if offline_days > 30:
                        return True, f"最后在线时间 {offline_days} 天前"
                    else:
                        return False, f"最后在线时间 {offline_days} 天前（小于30天）"

        elif isinstance(status, UserStatusEmpty):
            return True, "状态为空（可能很久未登录）"

        # 其他状态视为活跃
        return False, f"状态: {type(status).__name__}"

    except Exception as e:
        # 处理各种异常
        error_msg = str(e)
        if "Could not find the input entity" in error_msg:
            return True, "用户不存在"
        elif "The requested user does not exist" in error_msg:
            return True, "用户不存在"
        elif "A wait of" in error_msg:  # 洪水限制
            raise  # 重新抛出，让外层处理
        else:
            # 其他错误（如隐私设置）视为无法判断，保留用户
            logger.warning(f"查询用户 {username} 时出错: {error_msg}")
            return False, f"查询错误: {error_msg[:50]}"


async def clean_handles():
    """主清理函数"""
    try:
        from telethon import TelegramClient, errors
    except ImportError:
        logger.error("请安装 telethon: pip install telethon")
        return

    # 1. 获取所有 handle
    tg_handles, tg_left_handles = get_all_handles()
    all_handles = tg_handles.union(tg_left_handles)
    logger.info(f"总共 {len(all_handles)} 个唯一用户名需要检查")

    # 2. 过滤 bot
    filtered_handles = filter_bot_handles(all_handles)

    # 3. 初始化 Telegram 客户端
    api_id, api_hash, session = db.get_tg_credentials("parser")
    logger.info(f"使用 Telegram API (parser): API_ID={api_id}")

    client = TelegramClient(session, api_id, api_hash)
    await client.start()

    logger.info("Telegram 客户端已启动")

    # 4. 分批处理
    batch_size = 100
    handles_list = list(filtered_handles)
    total = len(handles_list)

    deleted_from_tg = 0
    deleted_from_left = 0
    bot_removed = 0
    inactive_removed = 0
    errors = 0

    for i in range(0, total, batch_size):
        batch = handles_list[i:i+batch_size]
        logger.info(f"处理批次 {i//batch_size + 1}/{(total+batch_size-1)//batch_size}: {len(batch)} 个用户")

        for j, username in enumerate(batch):
            try:
                # 检查是否不活跃
                is_inactive, reason = await check_user_inactive(client, username)

                if is_inactive:
                    # 从两个表中删除
                    db.delete_tg_handle(username)
                    db.delete_tg_left_user(username)
                    inactive_removed += 1
                    logger.info(f"[{i+j+1}/{total}] 删除 {username}: {reason}")
                else:
                    # 记录活跃用户
                    logger.debug(f"[{i+j+1}/{total}] 保留 {username}: {reason}")

                # 添加延迟以避免洪水限制（每秒1个查询）
                if j < len(batch) - 1:  # 不是批次中的最后一个
                    await asyncio.sleep(1)

            except errors.FloodWaitError as e:
                wait_time = e.seconds
                logger.warning(f"触发洪水限制，等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                # 重试当前用户
                j -= 1
                continue

            except Exception as e:
                errors += 1
                logger.error(f"处理用户 {username} 时出错: {e}")
                # 继续处理下一个用户

        # 批次之间的延迟
        if i + batch_size < total:
            logger.info("批次之间冷却 10 秒...")
            await asyncio.sleep(10)

    # 5. 统计结果
    logger.info("=" * 50)
    logger.info("清理完成！")
    logger.info(f"总共处理: {total} 个用户")
    logger.info(f"删除不活跃用户: {inactive_removed}")
    logger.info(f"删除 bot 用户: {len(all_handles) - len(filtered_handles)}")
    logger.info(f"从 tg_handles 删除: {deleted_from_tg}")
    logger.info(f"从 tg_left_users 删除: {deleted_from_left}")
    logger.info(f"错误数: {errors}")

    # 6. 关闭客户端
    await client.disconnect()
    logger.info("Telegram 客户端已断开连接")


def main():
    """同步入口点"""
    asyncio.run(clean_handles())


if __name__ == "__main__":
    main()