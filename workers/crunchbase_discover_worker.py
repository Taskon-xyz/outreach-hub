"""
Crunchbase Discover Worker — 从 Crunchbase Discover 列表抓取公司官网，写入 projects 表
改造自 crunchbase_discover_scraper.py，集成到 outreach-hub
"""
import re
import time
import random
import threading

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
from workers.base_worker import BaseWorker

SOCIAL_EXCLUDE = [
    'crunchbase.com', 'twitter.com', 'x.com', 'facebook.com', 'fb.com',
    'linkedin.com', 'instagram.com', 'youtube.com', 'github.com',
    'medium.com', 't.me', 'telegram', 'discord.gg', 'discord.com',
    'google.com', 'apple.com', 'cloudflare', 'gstatic.com',
    'googleapis.com', 'doubleclick.net', 'googletagmanager.com',
    'google-analytics.com', 'cdn.jsdelivr.net', 'cdnjs.cloudflare.com',
    'unpkg.com', 'w3.org', 'schema.org',
]


class CrunchbaseDiscoverWorker(BaseWorker):
    def __init__(self, start_url, source_tag, log_callback, progress_callback=None,
                 login_event: threading.Event = None):
        super().__init__(log_callback, progress_callback)
        if not source_tag or source_tag == "tg_left":
            raise ValueError("source_tag 必填，且不能为保留值 'tg_left'")
        self.start_url   = start_url
        self.source_tag  = source_tag
        self.login_event = login_event  # UI 通知「已登录」的 Event

    def run(self):
        try:
            import undetected_chromedriver as uc
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except ImportError as e:
            self.log(f"缺少依赖：{e}，请运行 pip install undetected-chromedriver selenium")
            return

        if not self.start_url.strip():
            self.log("请填写 Crunchbase Discover 列表 URL")
            return

        self.log("启动浏览器...")
        try:
            options = uc.ChromeOptions()
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--no-sandbox')
            options.add_argument('--start-maximized')
            driver = uc.Chrome(options=options, use_subprocess=True, version_main=145)
        except Exception as e:
            self.log(f"浏览器启动失败：{e}")
            return

        try:
            driver.get(self.start_url)
            self._wait_load(driver)
            self._handle_cf(driver)

            self.log("浏览器已打开，请在浏览器中登录 Crunchbase 账号。")
            self.log("登录后，手动翻到目标起始页，再点击「已就位，开始抓取」按钮。")

            # 等待 UI 通知登录完成
            if self.login_event:
                self.login_event.wait()
                self.login_event.clear()

            if self._stop:
                return

            self.log("开始抓取...")
            inserted = 0
            skipped  = 0
            page_num = 0

            while not self._stop:
                page_num += 1
                self.log(f"\n── 第 {page_num} 页 ──")

                companies = self._get_company_links(driver, By, WebDriverWait, EC)
                if not companies:
                    self.log("当前页无数据，停止。")
                    break

                self.log(f"本页找到 {len(companies)} 家公司")

                for idx, (name, cb_url) in enumerate(companies):
                    if self._stop:
                        break

                    self.log(f"  [{inserted + skipped + 1}] {name}")
                    driver.get(cb_url)
                    self._wait_load(driver)
                    self._handle_cf(driver)
                    time.sleep(random.uniform(2, 4))

                    website = self._extract_website(driver)
                    self.log(f"       官网：{website or '未找到'}")

                    if website:
                        _, is_new = db.upsert_project_return_id(name, website, source=self.source_tag)
                        if is_new:
                            inserted += 1
                        else:
                            skipped += 1
                    else:
                        skipped += 1

                    self.progress(inserted + skipped, None)

                    driver.back()
                    self._wait_load(driver)
                    time.sleep(random.uniform(1, 2))

                    if idx < len(companies) - 1:
                        time.sleep(4 + random.uniform(1, 3))

                if self._stop:
                    break

                if not self._click_next(driver):
                    self.log("已到最后一页，抓取完成。")
                    break

            self.log(f"\n完成！新增 {inserted} 条，跳过/无官网 {skipped} 条")
            self.log(f"数据库 projects 表总数：{db.count_projects()}")

        finally:
            try:
                driver.quit()
            except Exception:
                pass

    # ── 内部工具方法 ─────────────────────────────────────────

    def _wait_load(self, driver, timeout=15):
        time.sleep(3)
        start = time.time()
        while time.time() - start < timeout:
            try:
                if driver.execute_script("return document.readyState") == "complete":
                    time.sleep(2)
                    return
            except Exception:
                pass
            time.sleep(0.5)

    def _handle_cf(self, driver):
        src = driver.page_source.lower()
        if "just a moment" in src or "checking your browser" in src:
            self.log("  [CF] 等待 Cloudflare 验证...")
            time.sleep(10)
            self._wait_load(driver)

    def _is_valid_website(self, url):
        if not url or not url.startswith('http'):
            return False
        return not any(ex in url.lower() for ex in SOCIAL_EXCLUDE)

    def _extract_website(self, driver):
        src = driver.page_source
        try:
            m = re.search(r'"website":\{"value":"(https?://[^"]+)"', src)
            if m and self._is_valid_website(m.group(1)):
                return m.group(1)
        except Exception:
            pass
        try:
            from selenium.webdriver.common.by import By
            links = driver.find_elements(By.TAG_NAME, 'a')
            for link in links:
                try:
                    href = link.get_attribute('href') or ''
                    if not self._is_valid_website(href):
                        continue
                    text = link.text.strip().lower()
                    aria = (link.get_attribute('aria-label') or '').lower()
                    if 'website' in text or 'website' in aria:
                        return href
                except Exception:
                    continue
        except Exception:
            pass
        try:
            lines = src.split('\n')
            for i, line in enumerate(lines):
                if '"website"' in line.lower():
                    ctx = '\n'.join(lines[max(0, i-2):i+3])
                    for url in re.findall(r'https?://[^\s\'"<>]+', ctx):
                        url = url.rstrip('.,;:"\')>')
                        if self._is_valid_website(url):
                            return url
        except Exception:
            pass
        return None

    def _get_company_links(self, driver, By, WebDriverWait, EC):
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, 'grid-row'))
            )
            time.sleep(2)
        except Exception:
            self.log("  [警告] 页面可能未正确加载")

        results = []
        try:
            elements = driver.find_elements(
                By.CSS_SELECTOR, 'grid-row identifier-formatter a'
            )
            for el in elements:
                href = el.get_attribute('href') or ''
                name = el.text.strip()
                if href and '/organization/' in href and name:
                    results.append((name, href))
        except Exception as e:
            self.log(f"  [错误] 提取公司链接失败：{e}")

        seen = set()
        unique = []
        for item in results:
            if item[1] not in seen:
                seen.add(item[1])
                unique.append(item)
        return unique

    def _click_next(self, driver):
        try:
            from selenium.webdriver.common.by import By
            next_btn = driver.find_element(By.CSS_SELECTOR, 'a.page-button-next')
            href = next_btn.get_attribute('href')
            if not href:
                return False
            driver.get(href)
            time.sleep(5 + random.uniform(1, 3))
            self._wait_load(driver)
            self._handle_cf(driver)
            return True
        except Exception:
            return False
