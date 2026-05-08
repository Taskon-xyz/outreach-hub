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
from typing import Set, Tuple, List, Optional
import time

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


def delete_bot_handles() -> Tuple[int, int, int]:
    """删除所有以 bot 结尾的 handle，返回删除统计"""
    total_deleted, tg_deleted, left_deleted = db.delete_bot_handles()
    logger.info(f"删除 bot 用户: tg_handles={tg_deleted}, tg_left_users={left_deleted}, 总计={total_deleted}")
    return total_deleted, tg_deleted, left_deleted


def get_remaining_handles() -> Tuple[Set[str], Set[str]]:
    """获取删除 bot 后剩余的所有用户名"""
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

    logger.info(f"剩余用户名: tg_handles={len(tg_handles)}, tg_left_users={len(tg_left_handles)}")
    return tg_handles, tg_left_handles


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
                was_online = status.was_online
                if isinstance(was_online, datetime):
                    # 处理时区
                    now = datetime.now(was_online.tzinfo) if was_online.tzinfo else datetime.now()
                    offline_days = (now - was_online).days
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


async def process_handles(client, handles_list: List[str], total_count: int) -> Tuple[int, int, int]:
    """
    处理用户列表，检查不活跃状态并删除
    返回: (删除的tg_handles数, 删除的tg_left_users数, 错误数)
    """
    deleted_tg = 0
    deleted_left = 0
    errors = 0

    for i, username in enumerate(handles_list):
        try:
            # 检查是否不活跃
            is_inactive, reason = await check_user_inactive(client, username)

            if is_inactive:
                # 从两个表中删除
                tg_deleted = db.delete_tg_handle(username)
                left_deleted = db.delete_tg_left_user(username)

                deleted_tg += tg_deleted
                deleted_left += left_deleted

                logger.info(f"[{i+1}/{total_count}] 删除 {username}: {reason} (tg:{tg_deleted}, left:{left_deleted})")
            else:
                # 记录活跃用户
                logger.debug(f"[{i+1}/{total_count}] 保留 {username}: {reason}")

            # 添加延迟以避免洪水限制（每秒1个查询）
            if i < total_count - 1:  # 不是最后一个
                await asyncio.sleep(1.5)  # 1.5秒延迟

        except Exception as e:
            errors += 1
            logger.error(f"处理用户 {username} 时出错: {e}")
            # 继续处理下一个用户

    return deleted_tg, deleted_left, errors


async def clean_handles():
    """主清理函数"""
    try:
        from telethon import TelegramClient, errors
    except ImportError:
        logger.error("请安装 telethon: pip install telethon")
        return

    logger.info("=" * 60)
    logger.info("开始清洗 Telegram handles")
    logger.info("=" * 60)

    # 1. 删除所有 bot 用户
    logger.info("步骤 1: 删除所有以 'bot' 结尾的 handle...")
    bot_total, bot_tg, bot_left = delete_bot_handles()

    # 2. 获取剩余用户名
    logger.info("步骤 2: 获取剩余用户名...")
    tg_handles, tg_left_handles = get_remaining_handles()

    # 合并去重
    all_handles = tg_handles.union(tg_left_handles)
    total_handles = len(all_handles)

    if total_handles == 0:
        logger.info("没有需要检查的用户名，清理完成。")
        return

    logger.info(f"步骤 3: 需要检查 {total_handles} 个用户名的活跃状态")

    # 3. 初始化 Telegram 客户端
    api_id, api_hash, session = db.get_tg_credentials("parser")
    logger.info(f"使用 Telegram API (parser): API_ID={api_id}")

    client = TelegramClient(session, api_id, api_hash)
    await client.start()
    logger.info("Telegram 客户端已启动")

    # 4. 分批处理
    batch_size = 50  # 较小的批次，便于控制
    handles_list = list(all_handles)
    total_batches = (total_handles + batch_size - 1) // batch_size

    total_deleted_tg = 0
    total_deleted_left = 0
    total_errors = 0

    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, total_handles)
        batch = handles_list[start_idx:end_idx]

        logger.info(f"处理批次 {batch_num+1}/{total_batches}: 用户 {start_idx+1}-{end_idx}")

        try:
            deleted_tg, deleted_left, errors = await process_handles(client, batch, total_handles)

            total_deleted_tg += deleted_tg
            total_deleted_left += deleted_left
            total_errors += errors

            # 批次之间的延迟
            if batch_num < total_batches - 1:
                wait_seconds = 30  # 批次之间等待30秒
                logger.info(f"批次之间冷却 {wait_seconds} 秒...")
                await asyncio.sleep(wait_seconds)

        except errors.FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"触发洪水限制，等待 {wait_time} 秒")
            await asyncio.sleep(wait_time)
            # 重试当前批次
            batch_num -= 1
            continue

    # 5. 关闭客户端
    await client.disconnect()
    logger.info("Telegram 客户端已断开连接")

    # 6. 最终统计
    logger.info("=" * 60)
    logger.info("清洗完成！")
    logger.info("=" * 60)
    logger.info(f"删除的 bot 用户: {bot_total} (tg_handles: {bot_tg}, tg_left_users: {bot_left})")
    logger.info(f"删除的不活跃用户: tg_handles={total_deleted_tg}, tg_left_users={total_deleted_left}")
    logger.info(f"总共检查用户数: {total_handles}")
    logger.info(f"错误数: {total_errors}")

    # 7. 最终统计剩余数据
    final_tg, final_left = get_remaining_handles()
    logger.info(f"剩余用户名总数: {len(final_tg) + len(final_left)} (tg_handles: {len(final_tg)}, tg_left_users: {len(final_left)})")


def main():
    """同步入口点"""
    try:
        asyncio.run(clean_handles())
    except KeyboardInterrupt:
        logger.info("用户中断清理过程")
    except Exception as e:
        logger.error(f"清理过程发生错误: {e}", exc_info=True)


if __name__ == "__main__":
    main()