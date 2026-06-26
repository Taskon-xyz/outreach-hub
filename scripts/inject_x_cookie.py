#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把日常 Chrome 的 X auth_token（明文）注入到 CDP Chrome —— 绕过 Windows App-Bound 加密。

背景：Windows Chrome 127+ 的 App-Bound 加密让「拷贝 cookies 文件」失效——拷过来 Chrome
解不开就当损坏删掉（已实测：完整 robocopy 后 CDP profile 里 auth_token 仍为 0）。
改用 CDP 协议直接 setCookie 注入 auth_token 明文：Chrome 会用它自己的方式重新加密存储
（新 profile 自己的 key，合法），X 收到合法 auth_token 即视为登录态。一次注入，永久复用。

前置：
  1. CDP Chrome 已启动：scripts\\start_chrome_cdp.bat --no-system
  2. 从日常 Chrome 复制 auth_token 明文值：
     日常 Chrome 打开 https://x.com → F12 → Application（应用程序）→ Cookies → https://x.com
     → 找到 auth_token → 双击 Value 列复制（一串约 40 字符的明文）

用法（项目根目录）：
  uv run python scripts/inject_x_cookie.py <auth_token值>
  # 若只注 auth_token 后发 DM 报 CSRF/403，再补 ct0（同样从 F12 Cookies 复制）：
  uv run python scripts/inject_x_cookie.py <auth_token值> <ct0值>
"""
import os
import sys
from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
USER_DATA = os.path.join(os.getcwd(), "data", "chrome_cdp_session")
INIT_FLAG = os.path.join(USER_DATA, ".initialized")


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print(__doc__)
        sys.exit(1)

    auth_token = sys.argv[1].strip()
    ct0 = sys.argv[2].strip() if len(sys.argv) > 2 else ""

    print(f"auth_token: {auth_token[:6]}...{auth_token[-4:]}  (长度 {len(auth_token)})")
    if ct0:
        print(f"ct0:        {ct0[:6]}...{ct0[-4:]}  (长度 {len(ct0)})")

    cookies = [{
        "name": "auth_token",
        "value": auth_token,
        "domain": ".x.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "sameSite": "Lax",
    }]
    if ct0:
        cookies.append({
            "name": "ct0",
            "value": ct0,
            "domain": ".x.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "sameSite": "Lax",
        })

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"\n✗ 连不上 CDP Chrome（{CDP_URL}）：{e}")
            print("  请先启动 CDP Chrome：scripts\\start_chrome_cdp.bat --no-system")
            sys.exit(1)

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        context.add_cookies(cookies)
        print("\n已注入，打开 x.com 验证...")

        page = context.new_page()
        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(6000)
        except Exception as e:
            print(f"  导航提示：{e}")

        names = [c["name"] for c in context.cookies("https://x.com")]
        has_auth = "auth_token" in names
        print(f"\nx.com cookies {len(names)} 条 | auth_token 在: {has_auth}")
        print(f"  URL: {page.url}")
        print(f"  标题: {page.title()}")

        if has_auth:
            os.makedirs(USER_DATA, exist_ok=True)
            with open(INIT_FLAG, "w") as f:
                f.write("injected\n")
            print("\n✓ auth_token 已写入 CDP profile。")
            print("  👉 看弹出的 x.com 标签：")
            print("     - 出现信息流/头像 → 登录态生效！关掉本脚本窗口，CDP Chrome 保留，")
            print("       回程序点「▶ 开始发送」→「已登录就绪」即可。")
            print("     - 仍是登录页 → 把上面输出贴给开发者，可能要补 ct0 或别的 cookie。")
            print("  已写 .initialized 标志，下次直接双击启动即可复用（不要再 --refresh，会覆盖）。")
        else:
            print("\n✗ auth_token 没注入成功，把上面输出贴给开发者。")

        try:
            input("\n按回车退出脚本（CDP Chrome 保持运行）...")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
