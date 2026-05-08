"""
重新登录 TG 账号 B（离群用户扫描用）
先写到新文件，再替换旧的，避免权限冲突
"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

async def login():
    api_id, api_hash, session = db.get_tg_credentials("left")
    print(f"API_ID: {api_id}")
    print(f"Session: {session}.session")
    print()

    from telethon import TelegramClient

    # 先写到临时文件，避免直接操作旧 session 文件的权限问题
    tmp_session = session + "_tmp"
    client = TelegramClient(tmp_session, api_id, api_hash)

    print("请输入手机号（带国际区号，如 +8613800138000）:")
    phone = input("> ").strip()

    await client.start(phone=lambda: phone)
    me = await client.get_me()
    print(f"\n登录成功！{me.first_name} {me.last_name or ''} (ID: {me.id})")
    await client.disconnect()

    # 用临时文件替换旧文件
    old_file = session + ".session"
    new_file = tmp_session + ".session"
    if os.path.exists(old_file):
        os.remove(old_file)
    os.rename(new_file, old_file)
    print("Session 更新完成！")

asyncio.run(login())
