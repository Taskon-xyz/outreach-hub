"""
探测 Telegram 桌面客户端的 UI 控件树
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import uiautomation as auto

# TG 桌面版 ClassName = 'class MainWindow'
desktop = auto.GetRootControl()
tg = None
for win in desktop.GetChildren():
    cls = win.ClassName or ""
    if cls == "class MainWindow":
        tg = win
        break

if not tg:
    print("Telegram window not found (ClassName='class MainWindow')")
    exit(1)

print(f"Found: Name={tg.Name!r}, ClassName={tg.ClassName!r}")
print(f"Rect: {tg.BoundingRectangle}")
print()

def dump_tree(ctrl, depth=0, max_depth=6):
    if depth > max_depth:
        return
    indent = "  " * depth
    name = ctrl.Name or ""
    ct = ctrl.ControlTypeName
    cls = ctrl.ClassName or ""
    auto_id = ctrl.AutomationId or ""
    rect = ""
    try:
        r = ctrl.BoundingRectangle
        rect = f" Rect=({r.left},{r.top},{r.right},{r.bottom})"
    except:
        pass
    info = f"{indent}[{ct}] Name={name!r}"
    if cls:
        info += f" Class={cls!r}"
    if auto_id:
        info += f" AutoId={auto_id!r}"
    info += rect
    print(info)
    try:
        for child in ctrl.GetChildren():
            dump_tree(child, depth + 1, max_depth)
    except Exception as e:
        print(f"{indent}  (error: {e})")

print("=== Control Tree (depth=6) ===")
dump_tree(tg, max_depth=6)
