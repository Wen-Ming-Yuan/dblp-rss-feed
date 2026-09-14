import re
import threading
from datetime import datetime
from bs4 import BeautifulSoup
from sources.base import BaseSource
from core.http import get_session

# 全局锁：保证同一时间只有一个 Playwright 实例
_PW_LOCK = threading.Lock()


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
                    browser = pw.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    html = page.content()
                    browser.close()
                return html
            except Exception as e:
                print(f"[ACM] Playwright 兜底失败: {e}")
                print(traceback.format_exc())   # ← 修复：完整堆栈
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
                for fmt in ("%d %B %Y", "%B %Y", "%Y"):
                    try:
                        pub_date = datetime.strptime(txt, fmt).date()
                        break
                    except Exception:
                        continue

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
