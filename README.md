# Web3 Outreach Hub

> [English version](README.en.md)

Web3 项目自动化触达工具。从多种数据源导入项目信息，自动爬取官网提取 Telegram / X 链接，解析群管理员，然后通过 TG / X DM 批量发送消息。

## 功能

- **数据导入**：从 CrunchBase、RootData、CryptoRank、ChainScope 等来源批量导入项目
- **网站爬取**：Playwright 自动爬取项目官网，提取 TG 群链接和 X 链接
- **TG 解析**：Telethon 解析群管理员、小群离群用户
- **DM 发送**：
  - **X (Twitter)**：Playwright 控制浏览器，自动搜索用户并发送 DM（macOS）
  - **Telegram**：Telethon API 或 OCR 坐标点击（Windows）
- **Web UI**：浏览器访问，局域网多电脑协作

## 安装

### 1. 安装 Google Chrome

X DM 发送需要通过 Chrome 浏览器完成，请先安装：

[下载 Google Chrome](https://www.google.com/chrome/)

### 2. 一键安装

复制以下命令到终端运行：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/lukezhao-tech/outreach-hub/main/scripts/install.sh)"
```

这个脚本会自动完成以下所有步骤：

| 步骤 | 说明 |
|------|------|
| 克隆代码 | 从 GitHub 拉取最新代码 |
| 检查 Chrome | 确认已安装 Google Chrome |
| 安装 uv | 如果没有 uv，自动下载安装 |
| 安装 Python | 通过 uv 下载 Python 3.11（不需要系统自带 Python） |
| 安装依赖 | `uv sync` 安装所有 pip 包 |
| 安装浏览器引擎 | `playwright install chromium` 用于网站爬取 |
| 环境验证 | 检查 tkinter、customtkinter、playwright 是否可用 |

整个过程大约 2-3 分钟，取决于网速。**只需运行一次。**

### 安装完成后

安装脚本结束时会自动进入 `outreach-hub` 目录。日常启动（每次新开终端后）：

```bash
cd outreach-hub    # 安装时 clone 的目录（通常在 home 目录下）
./scripts/start_chrome_cdp.sh
```

或者使用 Web UI：

```bash
cd outreach-hub
uv run python web_server.py
```

## 使用

### 桌面 GUI

```bash
./scripts/start_chrome_cdp.sh
```

这个脚本会：
1. 启动 Chrome CDP 模式（后台运行）
2. 启动桌面 GUI 应用

**X DM 发送流程**：
1. 在弹出的 Chrome 中登录 Twitter（`x.com`）
2. 回到应用界面，点击「开始发送」
3. 等待浏览器打开 DM 页面后，点击「已登录就绪」
4. 自动逐个发送 DM

**首次登录 X 卡循环？** X 把脚本启动的 Chrome 视作新设备，可能直接打回登录页。
解决方法：完全退出日常 Chrome（⌘Q，不只是关窗口），然后用 `--system` 启动：

```bash
./scripts/start_chrome_cdp.sh --system
```

这会复用日常 Chrome 的 profile（登录态、历史、cookies 都在），X 看到的是同一台老设备，不会风控。注意整个 outreach-hub 运行期间不能再启动日常 Chrome。

### Web UI

```bash
uv run python web_server.py
```

浏览器打开 `http://localhost:5000`，功能和桌面 GUI 一致。

## 数据流

```
数据源导入 -> projects 表
    |
    v  爬取官网
tg_links 表 + x_links 表
    |
    v  解析群信息
tg_handles 表 + tg_left_users 表
    |
    v  发送 DM
send_log 表
```

每一步都写入本地 SQLite，重启后自动跳过已处理项。

## 目录结构

```
outreach-hub/
  main.py              # 桌面 GUI 入口
  web_server.py        # Web UI 入口
  config.py            # 配置（凭证、路径、API）
  db.py                # 数据层（SQLite）
  workers/             # 后台任务（爬取、解析、发送）
  gui/                 # 桌面 GUI 标签页
  web/                 # Web UI 前端
  scripts/
    install.sh             # 一键安装（给新同事用）
    install_browsers.sh    # 环境准备（install.sh 内部调用）
    start_chrome_cdp.sh    # 日常启动（Chrome + GUI）
  data/                # 数据库、session（自动创建，不入版本控制）
```
