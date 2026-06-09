"""
Parser Worker — 进入 TG 群提取管理员，存入 SQLite
基于 tg_contacts.py
"""
import asyncio
import time

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import config
from workers.base_worker import BaseWorker

# FloodWait 最大等待时间（秒），超过则跳过当前任务并暂停整批
FLOOD_WAIT_CAP = 300
# 正常请求间隔（秒）
NORMAL_COOLDOWN = 10


class ParserWorker(BaseWorker):
    def __init__(self, log_callback, progress_callback=None):
        super().__init__(log_callback, progress_callback)

    def run(self):
        try:
            asyncio.run(self._async_run())
        except Exception as e:
            self.log(f"[错误] {e}")

    async def _async_run(self):
        try:
            from telethon import TelegramClient, errors
            from telethon.tl.functions.channels import JoinChannelRequest, GetParticipantsRequest, LeaveChannelRequest
            from telethon.tl.types import ChannelParticipantsAdmins, ChannelParticipantCreator
        except ImportError:
            self.log("请安装 telethon：pip install telethon")
            return

        links = db.get_all_tg_links()
        total = len(links)
        if total == 0:
            self.log("数据库中没有待解析的 TG 群链接")
            return

        self.log(f"共 {total} 个 TG 群待解析")

        api_id, api_hash, session = db.get_tg_credentials("parser")
        if not api_id or not api_hash:
            self.log("❌ 未配置 Telegram API（parser）。请到「⚙️ 设置」→「TG 账号凭证」填入 api_id / api_hash")
            self.log("   申请地址：https://my.telegram.org → API development tools")
            return
        self.log(f"使用账号 API_ID={api_id}，session={session}")
        client = TelegramClient(session, api_id, api_hash)
        from workers.telethon_auth import async_start_client
        if not await async_start_client(client, log_callback=self.log):
            self.log("登录失败或已取消")
            return

        for idx, (link_id, url, project_id, link_source) in enumerate(links):
            if self._stop:
                self.log("已停止")
                break

            self.log(f"[{idx+1}/{total}] {url}")
            entity = None
            linked_entity = None
            flood_waited = False
            try:
                entity = await client.get_entity(url)
                try:
                    await client(JoinChannelRequest(entity))
                    self.log(f"  已进入：{entity.title}")
                    await asyncio.sleep(2)
                except errors.InviteRequestSentError:
                    self.log(f"  需审核，跳过")
                    db.update_tg_link_status(link_id, "failed", "需要审核才能加入")
                    continue
                except Exception:
                    pass

                # 广播频道：尝试找关联讨论群
                target = entity
                if getattr(entity, 'broadcast', False) and not getattr(entity, 'megagroup', False):
                    linked_id = getattr(entity, 'linked_chat_id', None)
                    if linked_id:
                        try:
                            linked_entity = await client.get_entity(linked_id)
                            self.log(f"  广播频道 → 关联讨论群：{linked_entity.title}")
                            try:
                                await client(JoinChannelRequest(linked_entity))
                                await asyncio.sleep(2)
                            except Exception:
                                pass
                            target = linked_entity
                        except Exception as e:
                            self.log(f"  关联讨论群获取失败：{str(e)[:100]}")
                            db.update_tg_link_status(link_id, "failed", "广播频道，关联讨论群获取失败")
                            continue
                    else:
                        self.log(f"  广播频道，无关联讨论群，跳过")
                        db.update_tg_link_status(link_id, "failed", "广播频道，无关联讨论群")
                        continue

                participants = await client(GetParticipantsRequest(
                    channel=target,
                    filter=ChannelParticipantsAdmins(),
                    offset=0, limit=100, hash=0
                ))

                count = 0
                for p in participants.participants:
                    user = next((u for u in participants.users if u.id == p.user_id), None)
                    if user and user.username:
                        role = "Owner" if isinstance(p, ChannelParticipantCreator) else "Admin"
                        db.insert_tg_handle(
                            username=user.username,
                            role=role,
                            group_name=target.title,
                            source_link=url,
                            project_id=project_id,
                            source=link_source
                        )
                        count += 1
                self.log(f"  提取 {count} 位管理员")

                if count > 0:
                    db.update_tg_link_status(link_id, "ok")
                else:
                    db.update_tg_link_status(link_id, "failed", "无管理员用户名（可能是频道或全匿名群）")

            except errors.FloodWaitError as e:
                wait_secs = e.seconds
                flood_waited = True
                if wait_secs > FLOOD_WAIT_CAP:
                    self.log(f"  ⚠ FloodWait {wait_secs}s，超过上限 {FLOOD_WAIT_CAP}s，标记待重试并暂停解析")
                    db.update_tg_link_status(link_id, "pending", f"FloodWait {wait_secs}s")
                    # 暂停到 FloodWait 过期（带上限）
                    pause = min(wait_secs, FLOOD_WAIT_CAP)
                    self.log(f"  等待 {pause}s 后继续...")
                    for _ in range(pause):
                        if self._stop:
                            break
                        await asyncio.sleep(1)
                else:
                    self.log(f"  ⚠ FloodWait {wait_secs}s，等待后重试...")
                    db.update_tg_link_status(link_id, "pending", f"FloodWait {wait_secs}s")
                    for _ in range(wait_secs):
                        if self._stop:
                            break
                        await asyncio.sleep(1)

            except Exception as e:
                err_msg = str(e)[:200]
                self.log(f"  ⚠ {err_msg}")
                db.update_tg_link_status(link_id, "failed", err_msg)
            finally:
                for e in filter(None, [linked_entity, entity]):
                    try:
                        await client(LeaveChannelRequest(e))
                    except Exception:
                        pass

            self.progress(idx + 1, total)

            # 正常请求冷却（被 FloodWait 时已在上方等待过，跳过）
            if not flood_waited:
                for _ in range(NORMAL_COOLDOWN):
                    if self._stop:
                        break
                    await asyncio.sleep(1)

        await client.disconnect()
        self.log("解析完成！")
