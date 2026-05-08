"""
OCR 识别测试 — 在 Telegram 搜索栏输入一个用户名后运行此脚本
使用 WinRT OCR (zh-Hans-CN) 引擎
"""
import sys, io, os, time, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

print("3秒后截图，请切换到 Telegram 窗口...\n")
for i in range(3, 0, -1):
    print(f"  {i}...")
    time.sleep(1)

import mss
from PIL import Image
import winocr

region = db.get_ocr_region()
print(f"截图区域：{region}\n")

with mss.mss() as sct:
    sct_img = sct.grab(region)
    img = Image.frombytes("RGB", (sct_img.width, sct_img.height),
                          sct_img.bgra, "raw", "BGRX")

t0 = time.time()

async def run_ocr():
    return await winocr.recognize_pil(img, lang='zh-Hans-CN')

result = asyncio.run(run_ocr())
elapsed = time.time() - t0

print(f"识别耗时：{elapsed:.3f}s")
print(f"识别到 {len(result.lines)} 行：\n")
print(f"{'序号':<5} {'文本':<40} {'坐标 (x,y,w,h)'}")
print("-" * 80)
for i, line in enumerate(result.lines, 1):
    for w in line.words:
        r = w.bounding_rect
        print(f"{i:<5} {w.text:<40} ({r.x:.0f}, {r.y:.0f}, {r.width:.0f}, {r.height:.0f})")

# 保存截图
img.save(os.path.join(os.path.dirname(__file__), "ocr_test_screenshot.png"))
print("\n截图已保存：ocr_test_screenshot.png")

# 模拟匹配
target = input("\n输入要测试的 handle（不含@）：").strip().lower()
target_at = f"@{target}"
print(f"\n查找：{target_at}")
print("匹配结果：")
found = False
for line in result.lines:
    for w in line.words:
        if w.text.lower() == target_at:
            r = w.bounding_rect
            click_x = region["left"] + r.x + r.width / 2
            click_y = region["top"] + r.y + r.height / 2
            print(f"  精确匹配：{w.text} -> 点击坐标 ({click_x:.0f}, {click_y:.0f})")
            found = True
        elif target_at in w.text.lower():
            r = w.bounding_rect
            click_x = region["left"] + r.x + r.width / 2
            click_y = region["top"] + r.y + r.height / 2
            print(f"  包含匹配：{w.text} -> 点击坐标 ({click_x:.0f}, {click_y:.0f})")
            found = True
if not found:
    print("  未找到任何匹配")
