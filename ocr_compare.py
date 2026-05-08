"""
OCR 对比测试 — EasyOCR vs WinRT OCR vs RapidOCR
在 TG 搜索栏输入用户名后运行
"""
import sys, io, os, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db, mss, numpy as np
from PIL import Image

region = db.get_ocr_region()
print(f"截图区域: {region}")
print("3秒后截图，请确保 TG 搜索结果可见...")
for i in range(3, 0, -1):
    print(f"  {i}...")
    time.sleep(1)

with mss.mss() as sct:
    sct_img = sct.grab(region)
    img = Image.frombytes("RGB", (sct_img.width, sct_img.height),
                          sct_img.bgra, "raw", "BGRX")
img.save("ocr_compare_screenshot.png")
print(f"截图: {img.size}\n")

# ========== 1. WinRT OCR ==========
print("=" * 60)
print("[1] WinRT OCR")
try:
    import winocr, asyncio
    async def run_winocr():
        t0 = time.time()
        result = await winocr.recognize_pil(img, lang='en')
        elapsed = time.time() - t0
        print(f"  耗时: {elapsed:.2f}s, {len(result.lines)} 行:")
        for i, line in enumerate(result.lines, 1):
            print(f"    {i}: {line.text}")
    asyncio.run(run_winocr())
except Exception as e:
    print(f"  失败: {e}")

# ========== 2. RapidOCR ==========
print()
print("=" * 60)
print("[2] RapidOCR (PaddleOCR ONNX)")
try:
    from rapidocr_onnxruntime import RapidOCR
    engine = RapidOCR()
    t0 = time.time()
    result, elapse = engine(np.array(img))
    elapsed = time.time() - t0
    if result:
        print(f"  耗时: {elapsed:.2f}s, {len(result)} 个文本块:")
        for i, (bbox, text, prob) in enumerate(result, 1):
            print(f"    {i}: [{prob:.3f}] {text}")
    else:
        print(f"  未识别到文本 (耗时 {elapsed:.2f}s)")
except Exception as e:
    print(f"  失败: {e}")

# ========== 3. EasyOCR ==========
print()
print("=" * 60)
print("[3] EasyOCR")
try:
    import easyocr
    t0 = time.time()
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    easy_results = reader.readtext(np.array(img))
    elapsed = time.time() - t0
    print(f"  耗时: {elapsed:.2f}s, {len(easy_results)} 个文本块:")
    for i, (bbox, text, prob) in enumerate(easy_results, 1):
        print(f"    {i}: [{prob:.3f}] {text}")
except Exception as e:
    print(f"  失败: {e}")

print("\n对比完成!")
