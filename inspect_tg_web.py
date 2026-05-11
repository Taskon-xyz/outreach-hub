"""
临时脚本：交互式探查 Telegram Web DOM
"""
import asyncio
from playwright.async_api import async_playwright

TG_WEB_URL = "https://web.telegram.org/k/"
SESSION_DIR = "data/tg_web_session"

async def dump(label, locator, limit=2000):
    count = await locator.count()
    print(f"\n====== {label} (count={count}) ======")
    for i in range(min(count, 8)):
        el = locator.nth(i)
        try:
            html = await el.evaluate("e => e.outerHTML")
            print(f"  [{i}] {html[:400]}")
        except Exception as e:
            print(f"  [{i}] error: {e}")

async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            SESSION_DIR,
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(TG_WEB_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # ── 1. 在搜索框输入测试用户名 ──────────────────────────────
        test_handle = input("请输入一个测试用的 TG 用户名（不带@）：").strip()

        search = page.locator("input.input-search-input").first
        await search.click()
        await asyncio.sleep(0.5)
        await search.fill(test_handle)
        print(f"[已输入] {test_handle}，等待搜索结果...")
        await asyncio.sleep(3)

        await page.screenshot(path="data/tg_search_results.png")
        print("[截图] data/tg_search_results.png")

        # ── 2. 打印搜索结果列表 ────────────────────────────────────
        await dump("搜索结果候选", page.locator(".search-result, [class*='search-result'], .chatlist-chat, .list-item"))
        await dump("搜索结果 li/div 含@", page.locator(f"[class*='result'], [class*='item']"))

        # ── 3. 点击第一个结果，进入对话 ───────────────────────────
        input("\n按 Enter 点击第一个搜索结果...")
        first = page.locator(".search-result, .chatlist-chat, [class*='search-result']").first
        if await first.count() > 0:
            await first.click()
            print("[已点击] 等待对话页加载...")
            await asyncio.sleep(3)
        else:
            print("未找到结果元素，请手动点击后按 Enter")
            input()

        await page.screenshot(path="data/tg_chat_page.png")
        print("[截图] data/tg_chat_page.png")

        # ── 4. 打印消息输入框 ──────────────────────────────────────
        await dump("消息输入框 contenteditable", page.locator("[contenteditable='true']"))
        await dump("消息输入框 textarea", page.locator("textarea"))
        await dump("发送按钮", page.locator("button[class*='send'], .btn-send, [class*='send-button'], button.tgico-send"))

        # ── 5. 打印聊天区域整体结构（class 名）───────────────────
        print("\n====== 聊天区域顶层元素 class ======")
        els = await page.query_selector_all("#column-center > *, .chat-input *, .composer *")
        seen = set()
        for el in els[:40]:
            cls = await el.get_attribute("class") or ""
            tag = await el.evaluate("e => e.tagName.toLowerCase()")
            key = f"{tag}.{cls[:60]}"
            if key not in seen:
                seen.add(key)
                print(f"  {tag}  class='{cls[:80]}'")

        print("\n[完成] 按 Enter 关闭")
        input()
        await context.close()

asyncio.run(main())
