"""
RootData Fundraising Worker
从 RootData Fundraising 页逐页爬取项目，提取官网 + TG + X，直接入库。
- 官网 → projects 表（scrape_status 标记为 done）
- TG 群链接 → tg_links 表
- X 账号 → x_links 表
"""
import asyncio
import re
import time
import random

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
from workers.base_worker import BaseWorker

ROOTDATA_BASE   = "https://www.rootdata.com"
FUNDRAISING_URL = "https://www.rootdata.com/Fundraising"

# 排除 RootData 自己的账号
EXCLUDE_X  = {"rootdatacrypto"}
EXCLUDE_TG = {"rootdatalabs"}

TG_PATTERN = r't\.me/(?:joinchat/[\w\d_-]+|(?!(?:share|s|addstickers|setlanguage)/)[\w\d_]{5,})'
X_PATTERN  = r'(?:twitter\.com|x\.com)/([\w\d_]{1,15})'

SOCIAL_DOMAINS = [
    'twitter.com', 'x.com', 't.me', 'telegram', 'discord',
    'github.com', 'medium.com', 'linkedin.com', 'facebook.com',
    'youtube.com', 'instagram.com', 'rootdata.com',
    'defillama.com', 'prnewswire.com', 'cointelegraph.com',
    'notion.so', 'gitbook', 'docs.',
]


class RootDataWorker(BaseWorker):
    def __init__(self, source_tag, log_callback, progress_callback=None,
                 start_url=FUNDRAISING_URL, max_pages=999, start_page=1):
        super().__init__(log_callback, progress_callback)
        if not source_tag or source_tag == "tg_left":
            raise ValueError("source_tag 必填，且不能为保留值 'tg_left'")
        self.source_tag = source_tag
        self.start_url = start_url
        self.max_pages = max_pages
        self.start_page = max(1, int(start_page))

    def run(self):
        try:
            asyncio.run(self._async_run())
        except Exception as e:
            self.log(f"[错误] {e}")

    async def _async_run(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.log("请安装 playwright：pip install playwright && playwright install chromium")
            return

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)   # 有头模式方便登录
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
            )
            page = await context.new_page()

            self.log(f"打开：{self.start_url}")
            await page.goto(self.start_url, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            self.log("浏览器已打开，如需登录请先完成，然后点击「已就绪，开始抓取」按钮。")

            # 等待 UI 通知就绪（由 login_event 控制，通过 _ready 标志）
            while not getattr(self, '_ready', False):
                if self._stop:
                    await browser.close()
                    return
                await asyncio.sleep(0.5)

            self.log("开始抓取...")

            # 跳转到起始页
            if self.start_page > 1:
                self.log(f"跳转到第 {self.start_page} 页...")
                jumped = await self._jump_to_page(page, self.start_page)
                if not jumped:
                    self.log(f"⚠ 无法跳转到第 {self.start_page} 页，从当前页开始")

            total_inserted = 0
            total_skipped  = 0
            page_num = self.start_page - 1

            while not self._stop and page_num < (self.start_page - 1 + self.max_pages):
                page_num += 1
                self.log(f"\n── 第 {page_num} 页 ──")

                # 等待项目列表加载
                try:
                    await page.wait_for_selector('a[href*="/Projects/detail/"]', timeout=15000)
                except Exception:
                    self.log("  列表未加载，停止")
                    break

                # 提取本页所有项目链接
                project_links = await self._get_project_links(page)
                if not project_links:
                    self.log("  本页无项目，停止")
                    break

                self.log(f"  本页 {len(project_links)} 个项目")

                for name, proj_url in project_links:
                    if self._stop:
                        break
                    ins, skp = await self._process_project(context, name, proj_url)
                    total_inserted += ins
                    total_skipped  += skp
                    self.progress(total_inserted + total_skipped, None)
                    await asyncio.sleep(random.uniform(2, 4))

                if self._stop:
                    break

                # 翻页
                has_next = await self._click_next(page)
                if not has_next:
                    self.log("已到最后一页")
                    break
                await asyncio.sleep(random.uniform(2, 3))

            self.log(f"\n完成！新增 {total_inserted} 条，跳过 {total_skipped} 条")
            self.log(f"数据库 projects 表总数：{db.count_projects()}")
            await browser.close()

    def set_ready(self):
        """由 UI 调用，通知 worker 可以开始抓取"""
        self._ready = True

    async def _get_project_links(self, page):
        """提取当前页所有唯一项目链接"""
        links = await page.eval_on_selector_all(
            'a[href*="/Projects/detail/"]',
            """els => els.map(el => ({
                href: el.href,
                text: el.innerText.trim()
            }))"""
        )
        seen = set()
        result = []
        for item in links:
            href = item['href']
            if href not in seen:
                seen.add(href)
                # 取有意义的名字（过滤空文本和代币符号）
                name = item['text'].split('\n')[0].strip()
                result.append((name, href))
        return result

    async def _process_project(self, context, name, proj_url):
        """访问项目页，提取官网/TG/X，写入 DB。返回 (inserted, skipped)"""
        proj_page = await context.new_page()
        inserted = skipped = 0
        try:
            self.log(f"  → {name}")
            await proj_page.goto(proj_url, timeout=45000, wait_until="domcontentloaded")
            await asyncio.sleep(2)

            content = await proj_page.content()
            website, tg_links, x_handles = self._extract_from_html(content)

            self.log(f"    官网:{website or '无'}  TG:{len(tg_links)}  X:{len(x_handles)}")

            if website:
                project_id = db.upsert_project(name, website, "", source=self.source_tag)
                if project_id:
                    db.mark_project_scraped(project_id)
                    for tg in tg_links:
                        db.insert_tg_link(project_id, tg, source=self.source_tag)
                    for x in x_handles:
                        db.insert_x_link(project_id, x, source=self.source_tag)
                    inserted = 1
                else:
                    skipped = 1
            else:
                # 无官网但有社交账号：尝试用项目 URL 作占位写入
                skipped = 1

        except Exception as e:
            self.log(f"    ⚠ 出错：{str(e)[:60]}")
            skipped = 1
        finally:
            await proj_page.close()
        return inserted, skipped

    def _extract_from_html(self, html):
        """从 project page HTML 提取官网、TG 群链接、X 账号"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        website   = None
        tg_links  = set()
        x_handles = set()

        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text(strip=True)

            # ── 官网：文本像域名（含点、无斜杠），且不是社交平台 ──
            if (website is None
                    and '.' in text
                    and '/' not in text
                    and text.lower() != text.lower().startswith('http')
                    and not any(s in text.lower() for s in SOCIAL_DOMAINS)
                    and href.startswith('http')
                    and not any(s in href.lower() for s in SOCIAL_DOMAINS)):
                website = href

            # ── X / Twitter ──
            if re.search(r'(?:twitter\.com|x\.com)/', href):
                m = re.search(X_PATTERN, href)
                if m:
                    handle = m.group(1).lower()
                    if handle not in EXCLUDE_X and text in ('X', '@' + handle, handle):
                        x_handles.add(f"https://x.com/{m.group(1)}")

            # ── Telegram ──
            if 't.me/' in href:
                m = re.search(TG_PATTERN, href)
                if m:
                    slug = href.rstrip('/').split('/')[-1].lower()
                    if slug not in EXCLUDE_TG and text == 'Telegram':
                        full = 'https://' + m.group(0) if not href.startswith('http') else href
                        tg_links.add(full)

        return website, tg_links, x_handles

    async def _jump_to_page(self, page, target_page):
        """通过分页器输入框跳转到指定页码"""
        try:
            # RootData 使用 el-pagination，找到页码输入框
            input_el = page.locator('input.el-pagination__editor-input, .el-pagination .el-input__inner').last
            if await input_el.count() == 0:
                # 备选：逐页点击 next（慢但可靠）
                self.log(f"  未找到页码输入框，逐页跳转...")
                for i in range(1, target_page):
                    if self._stop:
                        return False
                    if i % 10 == 0:
                        self.log(f"  已翻到第 {i} 页...")
                    has_next = await self._click_next(page)
                    if not has_next:
                        self.log(f"  ⚠ 翻到第 {i} 页后没有下一页了")
                        return False
                    await asyncio.sleep(random.uniform(0.5, 1))
                return True

            # 清空并输入页码
            await input_el.click()
            await input_el.fill(str(target_page))
            await input_el.press('Enter')
            await asyncio.sleep(3)
            # 等待列表刷新
            await page.wait_for_selector('a[href*="/Projects/detail/"]', timeout=15000)
            self.log(f"  已跳转到第 {target_page} 页")
            return True
        except Exception as e:
            self.log(f"  跳页失败：{str(e)[:60]}")
            return False

    async def _click_next(self, page):
        """点击 Next 按钮，返回 True 表示成功翻页"""
        try:
            next_btn = page.locator('button.btn-next:not([disabled])')
            if await next_btn.count() == 0:
                return False
            await next_btn.click()
            await asyncio.sleep(1)
            await page.wait_for_selector('a[href*="/Projects/detail/"]', timeout=10000)
            return True
        except Exception:
            return False
