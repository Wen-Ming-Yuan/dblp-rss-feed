import re
from datetime import date
from bs4 import BeautifulSoup
from sources.base import BaseSource
from core.http import get_session


class SpringerSource(BaseSource):
    name = "springer"

    def fetch(self, conf, state):
        url = conf.get("springer_url")
        if not url:
            print(f"[Springer] {conf['short']} 缺少 springer_url")
            return []
        resp = get_session().get(url, timeout=30)
        if resp.status_code != 200:
            print(f"[Springer] {conf['short']} HTTP {resp.status_code}")
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        year = self._conf_year(conf)
        papers = []
        for item in soup.select(
            "li.app-card-open__item, li.chapter-item, div.book-toc__chapter"
        ):
            title_el = item.select_one(
                "a.app-card-open__heading, a.chapter-item__title, h3 a"
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if href.startswith("/"):
                href = "https://link.springer.com" + href
            doi = None
            m = re.search(r"10\.\d{4,}/[^\s?#]+", href)
            if m:
                doi = m.group(0)
            authors = [
                a.get_text(strip=True)
                for a in item.select("span.app-card-open__author, span.chapter-item__author")
            ]
            p = self._base_paper(conf)
            p.title = title
            p.doi = doi
            p.authors = authors
            p.url = href
            p.pub_date = date(year, 1, 1)
            papers.append(p)
        print(f"[Springer] {conf['short']} ({year}): {len(papers)} papers")
        return papers
