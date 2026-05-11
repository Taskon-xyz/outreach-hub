"""
所有凭证和固定配置
"""
import os, sys

# ── exe 内/外路径兼容 ──────────────────────────────────────────────────────────
# PyInstaller 打包后：sys._MEIPASS = 临时解压目录（只读）
# data/ 目录中的资源文件（read-only）从这里取
_MEIPASS = getattr(sys, "_MEIPASS", "")
if _MEIPASS:
    # exe 运行时：BASE_DIR 指向 exe 所在目录，data/ 在其旁边（可写）
    _EXE_DIR = os.path.dirname(sys.executable)
    BASE_DIR = _EXE_DIR
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")

# Telegram API
TG_API_ID   = 33174525
TG_API_HASH = "014f07ac24479b27f4ede2645067effe"
TG_SESSION  = os.path.join(DATA_DIR, "tg_session")

# tgleft 默认参数
TGLEFT_MAX_MEMBERS  = 20
TGLEFT_MAX_MESSAGES = 500

# 发送配置
TG_MAX_PER_HOUR = 30

# TG 搜索栏坐标（TG_AUTO_DM 中固定的坐标）
TG_SEARCH_BAR_POS = (148, 63)

# 坐标文件
DM_POS_FILE   = os.path.join(DATA_DIR, "dm_button_position.txt")
CHAT_POS_FILE = os.path.join(DATA_DIR, "chat_box_position.txt")

# ── Twitter Playwright session（macOS）──────────────────────────────────────
TWITTER_PW_DIR = os.path.join(DATA_DIR, "twitter_pw_session")
TWITTER_BROWSER = "chrome"

