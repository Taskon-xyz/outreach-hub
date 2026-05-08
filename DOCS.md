# Web3 Outreach Hub — 项目文档

> 面向开发者和未来需求扩展的完整技术文档。

---

## 目录

1. [项目背景](#1-项目背景)
2. [安装与启动](#2-安装与启动)
3. [项目结构](#3-项目结构)
4. [数据流转全链路](#4-数据流转全链路)
5. [模块详解](#5-模块详解)
   - 5.1 config.py
   - 5.2 db.py
   - 5.3 workers/
   - 5.4 gui/
6. [数据库设计](#6-数据库设计)
7. [GUI 标签页说明](#7-gui-标签页说明)
8. [冷却机制详解](#8-冷却机制详解)
9. [如何新增功能](#9-如何新增功能)
10. [常见问题](#10-常见问题)

---

## 1. 项目背景

### 整合了哪些原始脚本？

| 原始脚本 | 位置 | 功能 | 对应 Worker |
|---------|------|------|-------------|
| `crunchbase_extractor_cloudflare_v2.py` | `crunchbase converter/` | 从 Crunchbase Excel 提取官网 URL | `crunchbase_worker.py` |
| `tg_links.py` | `tg_group_link/` | 访问官网爬 TG + X 链接 | `scraper_worker.py` |
| `tg_contacts.py` | `tg_group_link/` | 进 TG 群提取管理员 | `parser_worker.py` |
| `tgleft.py` | `tgleft/` | 扫描小群中已离群用户 | `tgleft_worker.py` |
| `TG_AUTO_DM.py` | `auto-dm/` | 通过 WinRT OCR 发送 Telegram DM | `tg_sender_worker.py` |
| `xdm/app.py` | `xdm/` | 通过坐标点击发送 Twitter DM | `x_sender_worker.py` |
| — | — | 直接导入官网 Excel | `website_import_worker.py` |
| — | — | Crunchbase Discover 逐页爬官网 | `crunchbase_discover_worker.py` |
| — | — | RootData Fundraising 抓项目 | `rootdata_worker.py` |
| — | — | Old汤-链上抓项目官网+Twitter | `chainscope_worker.py` |
| — | — | Old汤-低交易量抓 Twitter | `token_finder_worker.py` |
| — | — | 活动项目 Twitter/KOL 账号导入 | `campaign_worker.py` |

### 与原始脚本的差异

原始脚本把进度/结果写回 **Google Sheets**；本项目改为写入本地 **SQLite**，优点：
- 无网络依赖，无 Google API 配额限制
- GUI 可以直接查询数据库展示进度
- 支持多步骤去重、发送历史追踪

---

## 2. 安装与启动

### 2.1 环境要求

- Python 3.9+
- Windows（`pyautogui` / OCR 操作需要桌面环境）
- Chrome 浏览器（已安装）

### 2.2 安装依赖

```bash
cd Desktop/auto/outreach-hub
pip install -r requirements.txt
playwright install chromium
```

### 2.3 首次配置

1. **放入 credentials.json**（仅使用 Google Sheet 写回时需要）
   将 Google Service Account 的 JSON 密钥文件复制到 `data/credentials.json`

2. **TG 账号登录**
   首次触发任何 TG 操作（解析/发送）时，Telethon 会在终端提示输入手机号和验证码，
   登录成功后在 `data/` 生成 `tg_session_{purpose}.session`，之后不再需要重新登录。

3. **TG 搜索栏坐标校准**
   在「⚙️ 设置」标签页，点击「🎯 校准搜索栏」，5秒内将鼠标移到 Telegram 搜索栏上。

4. **X 坐标校准**
   在「⚙️ 设置」标签页，点击「🎯 开始校准」，按步骤引导记录 DM 按钮和输入框坐标。

### 2.4 启动

```bash
python main.py
```

---

## 3. 项目结构

```
outreach-hub/
│
├── main.py                   # 入口：初始化 DB → 启动 GUI
├── config.py                 # 所有常量、路径、凭证（在此处统一修改）
├── db.py                     # SQLite 所有读写函数（9 张表）
├── requirements.txt
│
├── workers/                  # 后台任务逻辑（与 GUI 解耦）
│   ├── base_worker.py            # BaseWorker 基类
│   ├── crunchbase_worker.py     # Crunchbase Excel → 官网（undetected-chromedriver）
│   ├── crunchbase_discover_worker.py  # Crunchbase Discover 逐页爬官网
│   ├── website_import_worker.py  # 官网 Excel 直接导入
│   ├── scraper_worker.py        # 官网 → TG/X 链接（支持 DeepSeek 筛选）
│   ├── parser_worker.py         # TG 群 → 管理员（Telethon 进退群）
│   ├── tgleft_worker.py         # 小群 → 离群用户
│   ├── tg_sender_worker.py      # TG DM 发送（WinRT OCR + PyAutoGUI）
│   ├── x_sender_worker.py       # X DM 发送（PyAutoGUI 坐标点击）
│   ├── rootdata_worker.py       # RootData Fundraising 抓项目
│   ├── chainscope_worker.py      # Old汤-链上抓官网+Twitter
│   ├── token_finder_worker.py    # Old汤-低交易量抓 Twitter
│   └── campaign_worker.py       # 活动项目 Twitter/KOL 导入
│
├── gui/
│   ├── app.py                # 主窗口，懒加载 8 个标签页
│   ├── tab_dashboard.py      # 📊 仪表盘
│   ├── tab_import.py         # 📥 导入（Crunchbase 模式 + 官网直接导入）
│   ├── tab_scraper.py        # 🔍 爬虫（6个数据源子面板）
│   ├── tab_parser.py         # 🔬 解析
│   ├── tab_messages.py       # ✉️ 文案
│   ├── tab_sender.py         # 📤 发送
│   ├── tab_history.py        # 📋 记录
│   └── tab_settings.py       # ⚙️ 设置
│
└── data/                     # 运行时数据（首次运行自动创建）
    ├── outreach.db            # SQLite 数据库
    ├── credentials.json       # Google SA 密钥（用户手动放入）
    ├── tg_session_parser.session   # Telethon 会话（群管理员解析）
    ├── tg_session_left.session     # Telethon 会话（离群用户扫描）
    ├── tg_session_sender.session  # Telethon 会话（DM 发送，备用）
    ├── dm_button_position.txt     # X DM 按钮坐标
    └── chat_box_position.txt     # X 输入框坐标
```

---

## 4. 数据流转全链路

```
[导入阶段 — 任选数据源]

Crunchbase Excel ─────────────────────────────────────────────┐
Crunchbase Discover ──────────────────────────────────────────┤
官网 Excel 直接导入 ───────────────────────────────────────────┤
RootData Fundraising ─────────────────────────────────────────┤
Old汤-链上 ───────────────────────────────────────────────────┤
活动项目（Twitter/KOL） ──────────────────────────────────────┘
        │
        ▼
  projects 表（company_name, website）
        │
        ├─→ [官网直接导入来的 X 账号] → x_links 表（source=campaign 等）
        │
        │  ScraperWorker（Playwright headless）
        ▼
  tg_links 表（TG 群链接）      x_links 表（X 账号）
        │                              │
        │ ParserWorker（Telethon）      │
        ▼                              │
  tg_handles 表                       │
  （管理员 username）                  │
  source_link 区分来源：              │
  google_sheet_import = 仓库导入       │
  其他 = 群解析                       │
        │                              │
        │ TGLeftWorker（Telethon）     │
        ▼                              │
  tg_left_users 表                    │
  （离群用户 username）               │
        │                              │
        └────────┬────────────────────┘
                 │  tab_sender
                 ▼
           send_log 表
     (handle/channel/来源/文案/时间)
                 │
                 ▼
           tab_history
```

每一步都写入 SQLite，断点可续（重启后跳过已处理项）。

---

## 5. 模块详解

### 5.1 config.py

所有硬编码的常量。**需要修改配置时只改这一个文件。**

| 变量 | 含义 | 默认值 |
|------|------|--------|
| `CREDENTIALS_FILE` | Google SA 密钥路径 | `data/credentials.json` |
| `SPREADSHEET_ID` | Google Sheet ID（tg_links/scraper 写回用） | 项目默认值 |
| `TG_API_ID` / `TG_API_HASH` | Telegram API 凭证（默认 fallback，三个账号可在设置页独立配置） | 项目默认值 |
| `TG_SESSION` | Telethon 默认 session 路径 | `data/tg_session` |
| `TGLEFT_MAX_MEMBERS` | 小群人数上限（超过不扫描） | `20` |
| `TGLEFT_MAX_MESSAGES` | 每群最多扫描消息数 | `500` |
| `TG_MAX_PER_HOUR` | Telegram DM 每小时发送上限（可在发送页覆盖） | `30` |
| `TG_SEARCH_BAR_POS` | Telegram 搜索栏屏幕坐标（OCR 模式） | `(148, 63)` |
| `DM_POS_FILE` / `CHAT_POS_FILE` | X 坐标文件路径 | `data/*.txt` |

---

### 5.2 db.py

封装了所有 SQLite 操作，GUI 和 Worker 都通过这里读写数据，**不直接操作数据库**。

#### 数据库 9 张表

```
projects          tg_links        x_links
─────────         ────────        ───────
id (PK)           id (PK)         id (PK)
company_name      project_id →    project_id →
website (UNIQUE)  link (UNIQUE)   handle (UNIQUE)
crunchbase_url    parse_status   source
imported_at       parse_error     extracted_at
scrape_status     extracted_at

tg_handles                tg_left_users
──────────                ─────────────
id (PK)                   id (PK)
project_id →              username (UNIQUE)
username (UNIQUE)         display_name
role (Owner/Admin)        bio
group_name                group_name
source_link               found_at
parsed_at                 skip_reason / skipped_at
skip_reason / skipped_at

send_log                  message_templates
────────                  ─────────────────
id (PK)                   id (PK)
handle                    channel (telegram/twitter)
channel                   name
source                    content
message_name              is_active (0/1，同渠道最多1个)
sent_at                   updated_at

settings
────────
key (PK)   value
```

#### 关键函数速查

**初始化**
```python
db.init_db()          # 建表（幂等，多次调用安全）
```

**项目（官网）**
```python
db.upsert_project(company_name, website, crunchbase_url)   # 新增或忽略
db.upsert_project_return_id(company_name, website)         # 新增或返回已有 id
db.get_all_websites()     # 返回未扫描的 [(id, website), ...]
db.mark_project_scraped(project_id)
db.count_projects()
```

**链接**
```python
db.insert_tg_link(project_id, link)          # INSERT OR IGNORE
db.insert_x_link(project_id, handle, source)  # source: 'cb_excel'|'rootdata'|'chainscope'|'tokenfinder'|'campaign'|None
db.get_all_tg_links()    # 返回未成功解析的 [(id, link), ...]
db.update_tg_link_status(link_id, status, error)
# status: 'ok' | 'failed'
```

**TG Handles（区分来源）**
```python
db.insert_tg_handle(username, role, group_name, source_link, project_id=None)
# source_link='google_sheet_import' 时自动过滤以 bot 结尾的 handle

db.get_unsent_tg_admin_handles()       # 全部（imported + parsed），排除已发/已跳过
db.get_unsent_tg_imported_handles()     # 仅仓库导入
db.get_unsent_tg_parsed_handles()       # 仅群解析
```

**TG Left Users**
```python
db.insert_tg_left_user(username, display_name, bio, group_name)
db.get_unsent_tg_left_handles()
```

**跳过 / 恢复 / 删除**
```python
db.skip_handle(username, reason)     # 标记跳过，不从队列删除
db.unskip_handle(username)          # 恢复
db.delete_tg_handle(username)        # 彻底删除
db.delete_tg_left_user(username)
db.delete_bot_handles()             # 删除所有以 bot 结尾的 handle，返回 (total, tg, left)
db.get_skipped_handles()            # 查询所有被跳过的 handle
```

**X Links**
```python
db.get_unsent_x_handles(source=None)
# source: None=全部 | 'cb_excel' | 'cb_discover' | 'rootdata' | 'chainscope' | 'tokenfinder' | 'campaign'
```

**发送记录**
```python
db.log_send(handle, channel, source, message_name)
# channel: 'telegram' / 'twitter'
# source:  'tg_admin' / 'tg_left' / 'x_link' 等
db.get_send_log(channel=None, limit=300)
db.count_send_log()
```

**文案模板**
```python
db.save_template(channel, name, content)
db.set_active_template(channel, name)   # 同渠道只有一条激活
db.get_active_template(channel)        # 返回 {'name': ..., 'content': ...}
db.get_templates(channel)              # 返回所有版本
db.delete_template(template_id)
```

**TG 账号凭证（多账号支持）**
```python
db.get_tg_credentials(purpose)   # purpose: 'parser'|'left'|'sender'
db.save_tg_credentials(purpose, api_id, api_hash)
```

**TG 搜索栏坐标**
```python
db.get_tg_search_pos()    # 返回 (x, y)
db.save_tg_search_pos(x, y)
```

**OCR / 发送检测截图区域**
```python
db.get_ocr_region()        # dict(top/left/width/height)
db.save_ocr_region(top, left, width, height)
db.get_send_check_region()  # 未配置时返回屏幕中间 1/2 区域
db.save_send_check_region(top, left, width, height)
```

**冷却**
```python
db.get_cooldown_hours()    # cooldown_days*24 + cooldown_hours
db.get_setting(key, default=None)
db.save_setting(key, value)
```

**仪表盘汇总**
```python
db.get_stats()
# 返回: {projects, tg_links, x_links, tg_handles,
#         tg_left_users, sent_total, tg_pending, x_pending}
```

---

### 5.3 workers/

#### BaseWorker 接口

```python
class BaseWorker:
    def __init__(self, log_callback, progress_callback=None):
        self.log = log_callback        # 函数(str)，向 GUI 日志框输出
        self.progress = progress_callback  # 函数(cur:int, total:int)，更新进度条
        self._stop = False

    def stop(self):    # GUI 停止按钮调用
        self._stop = True

    def run(self):     # 在 threading.Thread 中调用
        raise NotImplementedError
```

**GUI 启动任务的标准写法：**
```python
self.worker = SomeWorker(self._log, self._update_progress, ...)
threading.Thread(target=self.worker.run, daemon=True).start()
```

#### 各 Worker 说明

**CrunchbaseWorker**
- 输入：Excel 文件路径（列名需有 `Organization Name` 和 `Organization Name URL`）
- 输出：向 `projects` 表写入 `(company_name, website, crunchbase_url)`
- 关键参数：`delay`（默认 4 秒，防止 Cloudflare 封禁）
- 特殊：使用 `undetected-chromedriver` 绕过 Cloudflare，浏览器窗口会弹出

**CrunchbaseDiscoverWorker**
- 输入：Crunchbase Discover 页面 URL（如保存的列表页）
- 输出：向 `projects` 表写入官网（source=`cb_discover` 标签由后续 ScraperWorker 补充）
- 流程：浏览器打开 → 用户登录 → 用户翻到目标页 → 点"已就位" → 逐页抓取
- 特殊：需要手动登录，支持翻页直到目标位置后开始抓取

**WebsiteImportWorker**
- 输入：Excel 文件，A 列=官网 URL（必填），B 列=公司名（选填）
- 输出：向 `projects` 表写入，跳过无效/非 http 行
- 特性：自动跳过表头行（首行不含 http 则跳过），支持无表头格式

**ScraperWorker**
- 输入：从 `projects` 表读取所有未扫描官网
- 输出：向 `tg_links` / `x_links` 表写入
- 使用 Playwright headless 模式，页面滚到底部后解析 HTML
- **DeepSeek 筛选**（可选）：在「🔍 爬虫」页勾选后，发现多个候选 TG/X 时调用 DeepSeek API
  判断哪个是官方社群（非频道）和官方 X 账号
- `source` 标签：官网解析得到的 X 账号标记为 `cb_excel`

**ParserWorker（Telethon）**
- 输入：从 `tg_links` 表读取所有群链接
- 输出：向 `tg_handles` 表写入管理员
- 每群操作：进群 → 抓 Admin/Owner → 退群，每次间隔 30 秒（保护账号）
- `source_link` 记录原始群链接（用于区分"群解析"来源）

**TGLeftWorker（Telethon）**
- 输入：Telegram 账号当前所在的所有群（≤ max_members）
- 输出：向 `tg_left_users` 表写入
- 参数：`max_members`（默认 20）、`max_messages`（默认 500）
- 逻辑：遍历所有群 → 获取当前成员 → 扫描历史消息 → 发现发言但不在群中的用户 → 同时拉取 bio

**TGSenderWorker（WinRT OCR + PyAutoGUI）**
- 输入：`get_unsent_tg_admin_handles()` 或 `get_unsent_tg_left_handles()` 的结果
- 输出：向 `send_log` 写入记录
- 工作方式：
  1. OCR 截取 TG 搜索栏区域
  2. WinRT OCR 识别搜索结果中 `@username` 的位置
  3. 点击匹配的用户
  4. 粘贴消息并发送
  5. 再次 OCR 检测是否弹出"账号受限"对话框（关键词：`sorry`/`mutual contact`/等）
  6. 若检测到受限，脚本自动停止
- OCR 引擎：**Windows 原生 WinRT OCR**（`winocr` 库，`zh-Hans-CN` 语言，速度快、准确率高）
- 限速：每小时最多 `max_per_hour` 条，达到上限后等到整点重置

**XSenderWorker（PyAutoGUI）**
- 输入：`get_unsent_x_handles(source=...)` 的结果
- 输出：向 `send_log` 写入记录
- 工作方式：导航到 `x.com/{handle}` → 点击 DM 按钮 → 点击输入框 → 粘贴发送
- **前提**：Chrome 已打开并登录 Twitter，坐标已校准

**RootDataWorker（Playwright）**
- 输入：RootData Fundraising 起始 URL
- 输出：直接写入 `projects` + `tg_links` + `x_links`（无需经过 ScraperWorker）
- 行为：Playwright 有头模式 → 用户登录后点"已就绪" → 逐页翻页抓取 → 进入每个项目页提取官网/TG/X
- `source` 标签：`x_links` 标记为 `rootdata`

**ChainScopeWorker**
- 输入：`chainscope.taskon.xyz/api/leads` API
- 输出：`projects` 表（官网）+ `x_links` 表（Twitter，source=`chainscope`）
- 翻页逻辑：比较相邻两页 JSON，数据完全一致则停止

**TokenFinderWorker**
- 输入：`token-finder.taskon.xyz/api/projects` API
- 输出：`x_links` 表（Twitter，source=`tokenfinder`），无 `project_id`
- 翻页逻辑：`offset += 50` 直到 `offset >= total`

**CampaignWorker**
- 输入：`xkeyword-monitor.taskon.xyz` API
- 两个端点：`/api/projects`（字段 `twitter_handle`，带 `@`）和 `/api/kol-projects`（字段 `project_handle`，无 `@`）
- 输出：`x_links` 表（source=`campaign`）
- 翻页逻辑：`page += 1` 直到返回条数 < page_size

---

### 5.4 gui/

#### app.py — 主窗口（懒加载）

```python
class App(ctk.CTk):
    # Tab 注册（懒加载：仅在首次切换时初始化）
    self._tab_registry = {
        "📊 仪表盘": ("gui.tab_dashboard", "DashboardTab"),
        "📥 导入":   ("gui.tab_import",    "ImportTab"),
        "🔍 爬虫":   ("gui.tab_scraper",   "ScraperTab"),
        "🔬 解析":   ("gui.tab_parser",    "ParserTab"),
        "✉️ 文案":   ("gui.tab_messages",  "MessagesTab"),
        "📤 发送":   ("gui.tab_sender",    "SenderTab"),
        "📋 记录":   ("gui.tab_history",   "HistoryTab"),
        "⚙️ 设置":   ("gui.tab_settings",  "SettingsTab"),
    }
```

#### 标签页类的统一结构

```python
class SomeTab:
    def __init__(self, parent):
        self.parent = parent
        self.worker = None
        self._build()

    def _build(self):       # 创建所有控件
    def _log(self, msg):    # 向日志框追加一行（state=normal → insert → state=disabled）
    def _update_progress(self, cur, total):   # 更新进度条
    def _start(self):       # 开始按钮：验证 → 创建 Worker → 后台线程
    def _run_worker(self):  # 在后台线程里 worker.run()，结束后恢复按钮状态
    def _stop(self):        # 停止按钮：worker.stop()
```

---

## 6. 数据库设计

### 去重机制

- `projects.website` / `tg_links.link` / `x_links.handle` / `tg_handles.username` / `tg_left_users.username` 均为 `UNIQUE`，重复插入时 `INSERT OR IGNORE` 静默跳过。
- 发送前通过 `NOT IN (SELECT handle FROM send_log WHERE ...)` 过滤已发过的用户。

### x_links 的 source 标签

用于区分 X 账号的数据来源，发送时可按来源筛选：

| source 值 | 来源 | 说明 |
|-----------|------|------|
| `cb_excel` | Crunchbase Excel + 官网爬虫 | 从 CB 导出项目官网后 ScraperWorker 解析 |
| `cb_discover` | Crunchbase Discover | 通过 ScraperTab 导入 |
| `rootdata` | RootData Fundraising | RootDataWorker 直接抓取 |
| `chainscope` | Old汤-链上变化 | ChainScopeWorker |
| `tokenfinder` | Old汤-低交易量 | TokenFinderWorker |
| `campaign` | 活动项目列表 | CampaignWorker |
| `None`（存量） | 仓库导入 | 历史存量数据，source 字段为 NULL |

### tg_handles 的来源区分

| source_link 值 | 来源 | 含义 |
|---------------|------|------|
| `google_sheet_import` | 仓库导入 | 手动从 Google Sheet 导入 |
| 其他（如 `t.me/xxx`） | 群解析 | ParserWorker 从 TG 群解析出的管理员 |

设置页可配置 `tg_import_filter_suffix`（默认 `bot`），自动过滤仓库导入中以该后缀结尾的 handle。

---

## 7. GUI 标签页说明

### 📊 仪表盘
- 6 个数字卡片实时展示各表记录数
- 待发队列：TG pending = tg_handles 未发 + tg_left_users 未发；X pending = x_links 未发
- 最近 10 条发送记录
- 点「刷新」重新查询数据库

### 📥 导入
两种模式，SegementedButton 切换：

**Crunchbase → 官网提取**
- 选 Excel 文件（需含 `Organization Name` 和 `Organization Name URL` 列）
- 设置请求间隔（默认 4 秒）
- 后台运行，浏览器窗口会弹出（Cloudflare bypass）

**官网直接导入**
- 选 Excel 文件（A 列官网 URL，B 列公司名可选）
- 自动跳过表头行（首行不含 http 则跳过）
- 支持无表头格式，重复 URL 静默跳过

### 🔍 爬虫（6 个数据源子面板）

| 子面板 | Worker | 输出 | 特点 |
|--------|--------|------|------|
| Crunchbase → 官网 | CrunchbaseDiscoverWorker | projects | 浏览器打开，用户登录后逐页抓 |
| RootData → 官网+TG+X | RootDataWorker | projects+tg_links+x_links | 有头模式，用户就绪后开始 |
| Old汤-链上 | ChainScopeWorker | projects+x_links | 纯 API，数据重复停止 |
| Old汤-低交易量 | TokenFinderWorker | x_links | 纯 API，offset 翻页 |
| 活动项目-Twitter | CampaignWorker | x_links | `/api/projects` |
| 活动项目-KOL | CampaignWorker | x_links | `/api/kol-projects` |

**官网 → TG + X 链接（右侧固定面板）**
- 读取数据库中未扫描的官网，Playwright headless 扫描
- 提取 `t.me/*` 和 `twitter.com/x.com/*` 链接
- 可选：勾选「DeepSeek 筛选」，多个候选时调用 API 判断官方账号

### 🔬 解析
- **左侧：TG 管理员解析**。读取 `tg_links`，Telethon 进群抓 Admin/Owner → 退群 → 间隔 30 秒
- **右侧：离群用户扫描**。参数 `最大成员数` / `最大消息数` 可在界面调整
- 两个任务独立，可以同时运行（建议分开跑避免 Telethon session 冲突）

### ✉️ 文案
- TG / X 各自独立管理
- 支持多版本（如"冷启动v1""追访v2"），每次发送记录使用哪个版本
- 同一渠道同时只有一条「激活」文案，发送时使用激活版本
- 操作：保存 / 新建 / 加载 / 激活 / 删除

### 📤 发送
- **TG 发送**：选数据源（imported/parsed/left/admin/all）× 设置每小时限额 → 开始
  - 前提：Telegram 桌面客户端在前台，`TG_SEARCH_BAR_POS` 坐标准确
- **X 发送**：选数据源（all/cb_excel/cb_discover/rootdata/chainscope/tokenfinder/campaign）× 开始
  - 前提：Chrome 在前台打开 Twitter，已登录，坐标已校准
- 坐标校准已移至「⚙️ 设置」页

### 📋 记录
- 展示 `send_log` 表，默认显示最近 300 条
- 支持按渠道（all / telegram / twitter）筛选
- 使用 `ttk.Treeview` 高性能表格，蓝色=Telegram，橙色=Twitter

### ⚙️ 设置（可滚动页面）

| 区块 | 功能 |
|------|------|
| DM 冷却时间 | 天数 + 小时数，支持预览各队列待发数量 |
| TG 搜索栏位置校准 | 5 秒倒计时，鼠标移到搜索栏自动记录；可重置默认 / 移动光标测试 |
| TG OCR 截图区域 | top/left/width/height，支持逐字段校准和截图预览 |
| TG 发送检测截图区域 | 发送后检测"账号受限"对话框的区域，未配置时默认屏幕中间 1/2 |
| X (Twitter) DM 坐标校准 | 两步校准：DM 按钮 → 输入框 |
| TG 账号 A — 群管理员解析 | API ID / Hash 保存，独立 session |
| TG 账号 B — 离群用户扫描 | API ID / Hash 保存，独立 session |
| TG 账号 C — DM 发送 | API ID / Hash 存档（实际使用桌面 TG 操作） |
| DeepSeek API | 官网多链接时 LLM 筛选，需填写 API Key |
| 待发数量预览 | 当前冷却设置下各队列的实际待发数量 |

---

## 8. 冷却机制详解

### 工作原理

冷却设置决定：**已发送过的联系人，多久后可以再次出现在待发队列**。

| 冷却设置 | 行为 |
|---------|------|
| 0 天 0 小时（关闭） | send_log 中有记录的联系人永远不再发送 |
| N > 0 小时 | 发送后 N 小时内同一联系人不出现；N 小时后可进行第二轮触达 |

### SQL 逻辑

```python
# db._cooldown_clause() 生成的 SQL：
if cooldown == 0:
    # 排除所有历史发送（永不重发）
    f"{col} NOT IN (SELECT handle FROM send_log WHERE channel=?)"
else:
    # 只排除冷却期内发送过的
    f"{col} NOT IN ("
    f"  SELECT handle FROM send_log"
    f"  WHERE channel=?"
    f"  AND sent_at > datetime('now', '-{cooldown} hours')"
    f")"
```

### 来源分离

TG 和 X **各自独立冷却**（`send_log.channel` 区分）：
- Telegram 冷却 → 只影响 TG 待发队列
- Twitter 冷却 → 只影响 X 待发队列

### 预览功能

在「⚙️ 设置」页点「预览待发数量」，实时显示当前冷却设置下各队列有多少待发用户。

---

## 9. 如何新增功能

### 9.1 新增一个数据来源（如从 CSV 导入联系人）

1. **在 `db.py` 确认目标表**（已有 `tg_handles`、`tg_left_users`、`x_links`，若数据形态相同直接复用）

2. **新建 Worker**（复制 `base_worker.py`，继承它）：
   ```python
   # workers/csv_import_worker.py
   from workers.base_worker import BaseWorker
   import db

   class CSVImportWorker(BaseWorker):
       def __init__(self, csv_path, log_callback, progress_callback=None):
           super().__init__(log_callback, progress_callback)
           self.csv_path = csv_path

       def run(self):
           import csv
           with open(self.csv_path) as f:
               rows = list(csv.DictReader(f))
           for i, row in enumerate(rows):
               if self._stop: break
               db.insert_x_link(None, row['handle'], source="my_source")
               self.log(f"导入：{row['handle']}")
               self.progress(i + 1, len(rows))
           self.log("完成！")
   ```

3. **在 `gui/tab_scraper.py` 新增子面板**（参考 `_build_cs_panel` 等），在 `_build_left()` 的 TabView 中注册

4. **在 GUI 启动 Worker**：
   ```python
   self.my_worker = MyWorker(path, self._log, self._progress_cb)
   threading.Thread(target=self._run, daemon=True).start()
   ```

---

### 9.2 新增一个发送渠道（如 Discord DM）

1. **`db.py`**：`send_log` 的 `channel` 字段是自由文本，无需改表结构。
   新增一个查询函数：
   ```python
   def get_unsent_discord_handles():
       # 从某张表里取出未发送过 discord DM 的 handle
   ```

2. **新建 Worker**：`workers/discord_sender_worker.py`

3. **扩展 `tab_sender.py`**：在 `SenderTab._build()` 里加第三列，或单独新建 `tab_discord.py`

---

### 9.3 修改发送限速

在 `config.py` 改 `TG_MAX_PER_HOUR`，或在 GUI「📤 发送」页的「每小时限额」输入框直接修改（优先级更高）。

---

### 9.4 修改 TG 搜索栏坐标

在 `config.py` 修改：
```python
TG_SEARCH_BAR_POS = (148, 63)   # (x, y) 屏幕像素坐标
```
或在「⚙️ 设置」页重新校准（永久保存到数据库）。

---

### 9.5 新增数据库表

在 `db.py` 的 `init_db()` 函数里，在 `executescript` 的 SQL 末尾追加建表语句：
```python
CREATE TABLE IF NOT EXISTS new_table (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    field1  TEXT,
    ...
);
```
`init_db()` 是幂等的，加完直接重启应用即生效。

---

### 9.6 新增文案变量（动态替换）

目前文案是纯文本。如需支持变量（如 `{project_name}`），在 Worker 的发送前处理：
```python
# tg_sender_worker.py 的发送部分
msg = self.message_content.replace("{username}", username)
pyperclip.copy(msg)
```

---

### 9.7 新增 x_links 的 source 标签

只需在 `db.insert_x_link(project_id, handle, source="新标签")` 调用处传入新标签值，发送页的下拉菜单需同步更新 `tab_sender.py` 中的 `values` 列表。

---

## 10. 常见问题

### Q: 启动后报 `ModuleNotFoundError`
**A:** 运行 `pip install -r requirements.txt`，然后 `playwright install chromium`。

### Q: TG 操作时提示要输入手机号
**A:** 正常，首次使用 Telethon 需要登录。在终端按提示输入手机号和验证码，之后对应 `data/tg_session_{purpose}.session` 会保存登录状态（三个功能有三个独立 session）。

### Q: Crunchbase 页面一直停在 Cloudflare 检测
**A:** 正常等待，或适当增大延迟。确保本机网络可访问 Crunchbase（必要时开 VPN）。CrunchbaseDiscoverWorker 和 CrunchbaseWorker 都使用 `undetected-chromedriver` 绕过。

### Q: TG DM 发送时 OCR 找不到用户名
**A:** 按以下顺序排查：
1. Telegram 桌面客户端是否在前台？
2. 搜索栏坐标是否准确？→ 在「⚙️ 设置」页重新校准
3. OCR 截图区域是否覆盖了搜索结果？→ 调整 OCR 截图区域
4. 用户名拼写是否正确？

### Q: X DM 发送点了没有反应
**A:** 重新校准坐标：「⚙️ 设置」页 → 「🎯 开始校准」。每次 Chrome 窗口移动或屏幕分辨率变化后都需要重新校准。

### Q: 想查看/修改数据库内容
**A:** 用免费工具 [DB Browser for SQLite](https://sqlitebrowser.org/) 打开 `data/outreach.db`，可直接查看和编辑所有表。

### Q: 程序关闭后重新打开，进度会丢失吗？
**A:** 不会。所有数据都存在 SQLite，重启后发送函数会自动跳过已在 `send_log` 中的用户（通过 `NOT IN` 查询实现去重）。

### Q: 如何彻底重置某个阶段的数据？
**A:** 用 DB Browser 清空对应的表，或在终端执行：
```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/outreach.db')
conn.execute('DELETE FROM tg_handles')  # 举例：重置管理员解析结果
conn.commit()
conn.close()
print('done')
"
```

### Q: 如何完全重置 TG 账号登录？
**A:** 删除 `data/tg_session_{purpose}.session` 文件，下次使用对应功能时 Telethon 会重新提示登录。

### Q: OCR 识别率低怎么办？
**A:** 在「⚙️ 设置」页调小 OCR 截图区域的 width/height，确保只截取搜索结果列表，减少干扰文字。也可以调整 top/left 使搜索结果居中。

---

## 11. 局域网多电脑协作（发送端独立部署）

### 架构

```
电脑A（服务器）                      电脑B / 电脑C
┌──────────────────┐              ┌──────────────────┐
│ SQLite 本地数据库  │              │ outreach-hub      │
│ + Flask API      │ ←──HTTP──→  │ （只执行发送）    │
│ IP: 192.168.x.x  │              │ config.API_BASE  │
└──────────────────┘              └──────────────────┘
```

- SQLite 只在电脑A（服务器）上操作，其他电脑零冲突
- 所有发送记录统一写入服务器数据库，各电脑互知发送状态
- 导入/爬虫/解析仍在服务器电脑执行，客户端电脑只跑发送

### 服务器电脑（电脑A）

**第一步：安装依赖**
```bash
pip install flask flask-cors requests
```

**第二步：启动 API 服务器**
```bash
# 双击运行（或命令行）：
python server/api_server.py 5000

# 或用提供的脚本（自动放行防火墙）：
run_server.bat
```

日志显示：
```
[OutreachHub API] 数据库: C:\Users\...\outreach-hub\data\outreach.db
[OutreachHub API] 监听: 0.0.0.0:5000
[OutreachHub API] 局域网访问: http://<本机IP>:5000/api/ping
```

**确认防火墙放行（run_server.bat 会自动处理）：**
```powershell
# 管理员 PowerShell
netsh advfirewall firewall add rule name="OutreachHub API" dir=in action=allow protocol=TCP localport=5000
```

### 客户端电脑（电脑B / 电脑C）

**第一步：复制项目文件**
将整个 `outreach-hub` 文件夹复制到客户端电脑。

**第二步：安装依赖**
```bash
pip install -r requirements.txt
pip install flask flask-cors requests
playwright install chromium
```

**第三步：修改 config.py**
```python
# config.py 第48行
API_BASE = "http://192.168.x.x:5000"   # 填写服务器电脑的内网 IP
```

**第四步：启动**
```bash
python main.py
```

### 工作原理

客户端电脑在发送时，`db.py` 中的以下函数自动走 HTTP 调用服务器 API：

| 客户端调用 | API 端点 | 作用 |
|-----------|---------|------|
| `log_send()` | POST `/api/log_send` | 记录发送（必须） |
| `get_unsent_tg_*_handles()` | GET `/api/queue/tg_*` | 获取待发 TG 用户 |
| `get_unsent_x_handles()` | GET `/api/queue/x` | 获取待发 X 用户 |
| `skip_handle()` | POST `/api/skip` | 标记跳过 |
| `get_active_template()` | GET `/api/template/active/{channel}` | 获取激活文案 |
| `get_stats()` | GET `/api/stats` | 仪表盘数据 |

本机模式（`API_BASE=""`）时所有函数走原生 SQLite，无任何变化。

### 查找服务器电脑 IP

在服务器电脑上运行：
```cmd
ipconfig
# 找 IPv4 地址，例如 192.168.1.100
```
