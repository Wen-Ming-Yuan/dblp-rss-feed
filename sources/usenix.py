import re
from datetime import date
from bs4 import BeautifulSoup
from sources.base import BaseSource
from core.http import get_session


class UsenixSource(BaseSource):
    name = "usenix"
    BASE = "https://www.usenix.org/conference/{path}/technical-sessions"

    def fetch(self, conf, state):
        path = conf.get("usenix_path")
        if not path:
            print(f"[USENIX] {conf['short']} 缺少 usenix_path")
            return []
        url = self.BASE.format(path=path)
        resp = get_session().get(url, timeout=30)
        if resp.status_code != 200:
            print(f"[USENIX] {conf['short']} HTTP {resp.status_code}")
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        year = self._year_from_path(path) or self._conf_year(conf)

        papers = []
        for node in soup.select("article.node-paper, div.node-paper"):
            title_el = node.select_one("h2.node-title a") or node.select_one("a.node-title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            paper_url = href if href.startswith("http") else "https://www.usenix.org" + href

            authors = [
                a.get_text(strip=True)
                for a in node.select("div.field-name-field-paper-people-text a, .paper-authors a")
            ]

            pdf_url = ""
            pdf_el = node.select_one("a[href$='.pdf']")
            if pdf_el:
                pdf_url = pdf_el.get("href", "")
                if pdf_url.startswith("/"):
                    pdf_url = "https://www.usenix.org" + pdf_url

            p = self._base_paper(conf)
            p.title = title
            p.authors = authors
            p.url = paper_url
            p.pdf_url = pdf_url
            p.pub_date = date(year, 1, 1)
            papers.append(p)

        print(f"[USENIX] {conf['short']} ({year}): {len(papers)} papers")
        return papers

    def _year_from_path(self, path):
        m = re.search(r"(\d{2})$", path)
        if m:
            return 2000 + int(m.group(1))
        return None
