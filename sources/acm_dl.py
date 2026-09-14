import re
import threading
import traceback
from datetime import datetime
from bs4 import BeautifulSoup
from sources.base import BaseSource
from core.http import get_session
from dateutil import parser as dateutil_parser   

# 全局锁：保证同一时间只有一个 Playwright 实例
_PW_LOCK = threading.Lock()
# 屏蔽图片/字体/媒体，加速页面加载
_BLOCK_RESOURCES = {"image", "font", "media"}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/151.0.0.0 Safari/537.36")


class AcmDlSource(BaseSource):
    name = "acm_dl"
    BASE = "https://dl.acm.org/doi/proceedings/"

    def fetch(self, conf, state):
        doi = conf.get("proceedings_doi")
        if not doi:
            print(f"[ACM] {conf['short']} 缺少 proceedings_doi")
            return []
        year = self._conf_year(conf)
        url = self.BASE + doi
        html = self._get_html(url)
        if not html:
            print(f"[ACM] {conf['short']} 未拿到 HTML")
            return []
        soup = BeautifulSoup(html, "lxml")
        papers = self._parse(soup, conf, year)
        print(f"[ACM] {conf['short']} ({year}): {len(papers)} papers")
        return papers

    def _get_html(self, url):
        resp = get_session().get(url, timeout=30)
        if resp.status_code == 200 and "issue-item" in resp.text:
            return resp.text
        # Playwright 兜底：加锁串行，避免并发 OOM
        with _PW_LOCK:
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(headless=True,args=["--no-sandbox", "--disable-dev-shm-usage"],)
                    ctx = browser.new_context(
                        user_agent=UA,
                        locale="en-US",
                        viewport={"width": 1366, "height": 900},
                    )
                    # 阻断图片/字体，加速
                    def _route(route):
                        if route.request.resource_type in _BLOCK_RESOURCES:
                            route.abort()
                        else:
                            route.continue_()

                    page.route("**/*", _route)

                    # 关键：不用 networkidle
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(3000)

                    # 等待正文出现，最多再等 10 秒
                    try:
                        page.wait_for_selector("div.issue-item", timeout=10000)
                    except Exception:
                        pass

                    html = page.content()
                    browser.close()
                return html
            except Exception as e:
                print(f"[ACM] Playwright 兜底失败: {e}")
                print(traceback.format_exc())
                return None
                    
    def _parse_acm_date(txt: str):
          """不依赖 locale 的日期解析。优先 dateutil，兜底年-only。"""
          if not txt:
                return None
          txt = txt.strip()
    # dateutil 能处理 "15 August 2026" / "August 2026" / "2026" 等多种格式
          try:
                dt = dateutil_parser.parse(txt, fuzzy=False, default=datetime(1970, 1, 1))
                return dt.date()
          except Exception:
                pass
    # 兜底：从字符串里抠出 4 位年份
          m = re.search(r"(19|20)\d{2}", txt)
          if m:
                return datetime(int(m.group(0)), 1, 1).date()
          return None

    def _parse(self, soup, conf, year):
        papers = []
        for item in soup.select("div.issue-item"):
            title_el = (item.select_one("h5.issue-item__title a")
                        or item.select_one("a.issue-item__title"))
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            paper_url = href if href.startswith("http") else "https://dl.acm.org" + href

            doi = None
            m = re.search(r"10\.\d{4,}/[^\s?#]+", href)
            if m:
                doi = m.group(0)
            else:
                doi_el = item.select_one("span.issue-item__doi, .doi")
                if doi_el:
                    m = re.search(r"10\.\d{4,}/[^\s]+", doi_el.get_text())
                    if m:
                        doi = m.group(0)

            authors = [
                a.get_text(strip=True)
                for a in item.select("ul.rlist--inline li a, span.issue-item__authors a")
            ]

            pub_date = None
            date_el = item.select_one("span.issue-item__date, .issue-item__date")
            if date_el:
                txt = date_el.get_text(strip=True)
                pub_date = _parse_acm_date(txt)
               
            # 关键修复：用 conf_year 过滤，不是系统年份
            # 允许 conf_year 和 conf_year-1（前一年底上线的论文）
            if pub_date and pub_date.year not in (year, year - 1):
                continue

            p = self._base_paper(conf)
            p.title = title
            p.doi = doi
            p.authors = authors
            p.url = paper_url
            p.pub_date = pub_date
            papers.append(p)
        return papers

