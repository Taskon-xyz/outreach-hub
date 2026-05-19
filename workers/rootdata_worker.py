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
import traceback

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
from workers.base_worker import BaseWorker
from workers.browser_stealth import (
    STEALTH_ARGS, IGNORE_DEFAULT_ARGS, STEALTH_INIT_SCRIPT,
    CONTEXT_KWARGS, EXTRA_HTTP_HEADERS,
)

ROOTDATA_BASE   = "https://www.rootdata.com"
FUNDRAISING_URL = "https://www.rootdata.com/fundraising"

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
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._async_run())
            finally:
                loop.close()
        except Exception as e:
            self.log(f"[错误] {e}")
            self.log(traceback.format_exc())

    async def _async_run(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.log("请安装 playwright：pip install playwright && playwright install chromium")
            return

        try:
            from bs4 import BeautifulSoup  # noqa: F401
        except ImportError:
            self.log("请安装 beautifulsoup4：uv add beautifulsoup4 或 pip install beautifulsoup4")
            return

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=STEALTH_ARGS,
                ignore_default_args=IGNORE_DEFAULT_ARGS,
            )
            context = await browser.new_context(**CONTEXT_KWARGS)
            await context.add_init_script(STEALTH_INIT_SCRIPT)
            await context.set_extra_http_headers(EXTRA_HTTP_HEADERS)
            page = await context.new_page()

            try:
                self.log(f"打开：{self.start_url}")
                await page.goto(self.start_url, timeout=60000, wait_until="domcontentloaded")
                await asyncio.sleep(3)

                self.log("浏览器已打开，如需登录请先完成，然后点击「已就绪，开始抓取」按钮。")

                # 等待 UI 通知就绪
                while not getattr(self, '_ready', False):
                    if self._stop:
                        return
                    await asyncio.sleep(0.5)

                self.log("开始抓取...")
                self.log(f"当前页面 URL：{page.url}")
                try:
                    title = await page.title()
                    self.log(f"当前页面标题：{title}")
                except Exception:
                    pass

                # 诊断：检查页面上有多少个 /Projects/detail/ 链接
                try:
                    detail_count = await page.locator('a[href*="/projects/detail/" i]').count()
                    self.log(f"诊断：页面上 /Projects/detail/ 链接数量 = {detail_count}")
                except Exception as e:
                    self.log(f"诊断：链接检查失败 {e}")

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
                        await page.wait_for_selector('a[href*="/projects/detail/" i]', timeout=15000)
                    except Exception:
                        self.log(f"  ⚠ 列表未加载（URL={page.url}）")
                        # 输出 body 前 300 字符，帮助诊断
                        try:
                            body_text = (await page.inner_text("body"))[:300]
                            self.log(f"  页面内容片段：{body_text}")
                        except Exception:
                            pass
                        self.log("  浏览器保持打开，请检查页面状态。点击「⏹ 停止」关闭浏览器。")
                        # 等待用户停止
                        while not self._stop:
                            await asyncio.sleep(1)
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
            except Exception as e:
                self.log(f"[运行异常] {e}")
                self.log(traceback.format_exc())
                self.log("浏览器保持打开，请检查页面。点击「⏹ 停止」关闭。")
                while not self._stop:
                    await asyncio.sleep(1)
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass

    def set_ready(self):
        """由 UI 调用，通知 worker 可以开始抓取"""
        self._ready = True

    async def _get_project_links(self, page):
        """提取当前页所有唯一项目链接"""
        links = await page.eval_on_selector_all(
            'a[href*="/projects/detail/" i]',
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
            await page.wait_for_selector('a[href*="/projects/detail/" i]', timeout=15000)
            self.log(f"  已跳转到第 {target_page} 页")
            return True
        except Exception as e:
            self.log(f"  跳页失败：{str(e)[:60]}")
            return False

    async def _click_next(self, page):
        """点击 Next 按钮，返回 True 表示成功翻页"""
        # 记录跳转前第一个项目链接，用于判断翻页是否真的发生
        try:
            first_href_before = await page.locator('a[href*="/projects/detail/" i]').first.get_attribute("href")
        except Exception:
            first_href_before = None

        # 候选的「下一页」按钮选择器（兼容多种 UI 库）
        candidates = [
            'button.btn-next:not([disabled])',                          # Element UI 旧版
            'button.el-pager__btn-next:not([disabled])',
            'button[aria-label="Next"]:not([disabled])',                # 通用 ARIA
            'button[aria-label="next page"]:not([disabled])',
            'button[aria-label*="next" i]:not([disabled])',
            'a[aria-label*="next" i]:not([aria-disabled="true"])',
            'li.ant-pagination-next:not(.ant-pagination-disabled) a',   # Ant Design
            'li.ant-pagination-next:not(.ant-pagination-disabled) button',
            '.pagination-next:not(.disabled)',
            'button:has-text("Next"):not([disabled])',                  # 文本匹配
            'a:has-text("Next")',
            'button:has(svg) >> nth=-1',                                # 兜底：最后一个图标按钮
        ]

        clicked = False
        for sel in candidates:
            try:
                btn = page.locator(sel).first
                if await btn.count() == 0:
                    continue
                if not await btn.is_visible():
                    continue
                await btn.scroll_into_view_if_needed(timeout=2000)
                await btn.click(timeout=3000)
                clicked = True
                self.log(f"  使用翻页选择器：{sel}")
                break
            except Exception:
                continue

        if not clicked:
            # 诊断：dump 翻页区域 HTML，帮助下一步定位
            try:
                pagination_html = await page.evaluate("""
                    () => {
                        const candidates = document.querySelectorAll('[class*="pag" i], [class*="page" i], nav, ul');
                        const out = [];
                        for (const el of candidates) {
                            const t = el.innerText || '';
                            if (/next|prev|\\d/i.test(t) && t.length < 200) {
                                out.push(el.outerHTML.slice(0, 500));
                            }
                        }
                        return out.slice(0, 3).join('\\n---\\n');
                    }
                """)
                self.log(f"  翻页区域 HTML 片段：\n{pagination_html[:1500]}")
            except Exception:
                pass
            return False

        # 等待新页面项目链接加载（且与上一页不同）
        try:
            for _ in range(20):
                await asyncio.sleep(0.5)
                try:
                    first_href_after = await page.locator('a[href*="/projects/detail/" i]').first.get_attribute("href")
                except Exception:
                    first_href_after = None
                if first_href_after and first_href_after != first_href_before:
                    return True
            self.log("  翻页后内容未变化")
            return False
        except Exception:
            return False
