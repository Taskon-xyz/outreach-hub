#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""X 登录态诊断：定位 auth_token 在哪个 Chrome profile，以及拷到 CDP 隔离 profile 后还在不在。

用法（Windows，项目根目录）：
  1. 先【完全退出所有 Chrome】——日常 Chrome + 脚本启动的 CDP Chrome 都要退
     （任务管理器里 chrome.exe 清零）。否则 cookies 没落盘，会误报「没有 auth_token」。
  2. uv run python scripts/diag_x_profile.py
  3. 把输出贴给开发者。

判读见脚本末尾打印。
"""
import glob
import json
import os
import shutil
import sqlite3
import sys
import tempfile


def chrome_user_data():
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Google/Chrome")
    la = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(la, "Google", "Chrome", "User Data")


def load_profile_info(base):
    """从 Local State 读各 profile 的账号名，方便辨认。"""
    ls = os.path.join(base, "Local State")
    if not os.path.exists(ls):
        return {}
    try:
        with open(ls, encoding="utf-8") as f:
            return json.load(f).get("profile", {}).get("info_cache", {})
    except Exception as e:
        print(f"  (读 Local State 失败: {e})")
        return {}


def count_auth_token(cookie_path):
    """复制一份再查，避免读写锁；返回 (count, status)。"""
    if not os.path.exists(cookie_path):
        return None, "无 cookies 文件"
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        shutil.copy2(cookie_path, tmp)
    except Exception as e:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        return None, f"复制失败({type(e).__name__})——Chrome 可能还在运行"
    try:
        con = sqlite3.connect(tmp)
        n = con.execute(
            "SELECT COUNT(*) FROM cookies WHERE name='auth_token'"
        ).fetchone()[0]
        con.close()
        return n, "ok"
    except Exception as e:
        return None, f"sqlite 错误: {e}"
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


def scan(label, base):
    print(f"\n══ {label} ══")
    print(f"路径: {base}")
    if not os.path.isdir(base):
        print("  → 目录不存在")
        return
    info = load_profile_info(base) if "日常" in label else {}
    profs = [os.path.join(base, "Default")] + sorted(
        glob.glob(os.path.join(base, "Profile *"))
    )
    any_prof = False
    for p in profs:
        if not os.path.isdir(p):
            continue
        any_prof = True
        name = os.path.basename(p)
        meta = info.get(name, {})
        who = meta.get("user_name") or meta.get("gaia_name") or meta.get("name") or ""
        ck = None
        for rel in ("Network/Cookies", "Cookies"):
            cand = os.path.join(p, rel)
            if os.path.exists(cand):
                ck = cand
                break
        if not ck:
            print(f"  [{name:<12}] {who:<28} 无 cookies 文件")
            continue
        n, st = count_auth_token(ck)
        mark = "  ◀◀◀ auth_token 在这里" if n else ""
        print(f"  [{name:<12}] {who:<28} auth_token={n}  ({st}){mark}")
    if not any_prof:
        print("  → 没找到任何 profile")


def main():
    print("X 登录态诊断（auth_token 探测）")
    print("当前目录:", os.getcwd())
    print("⚠️  必须先完全退出所有 Chrome（日常 + CDP），否则 cookies 没落盘会误报。")
    scan("日常 Chrome", chrome_user_data())
    scan("CDP 隔离 profile", os.path.join(os.getcwd(), "data", "chrome_cdp_session"))
    print("\n判读：")
    print("  • 日常 Chrome 里标 ◀◀◀ 的就是 auth_token 所在 profile。")
    print("    若不是 Default → bat 默认拷错了，改用 --profile \"Profile 1\" 之类指定。")
    print("  • 日常有 auth_token、CDP 没有 → 拷过来了但 Windows App-Bound 加密解不开，")
    print("    Chrome 启动时把它当损坏删掉了。（实锤加密坑，拷文件这条路 Windows 走不通）")
    print("  • CDP 也有 auth_token → 文件层面 OK，问题在别处（把结果贴给开发者）。")


if __name__ == "__main__":
    main()
