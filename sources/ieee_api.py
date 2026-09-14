import os
from datetime import datetime
from sources.base import BaseSource
from core.http import throttled_get
from core.quota import Quota


class IeeeApiSource(BaseSource):
    name = "ieee"
    BASE = "https://ieeexploreapi.ieee.org/api/v1/search/articles"

    def __init__(self):
        self.api_key = os.environ.get("IEEE_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("IEEE_API_KEY not set")

    def fetch(self, conf, state):
        if not Quota.can_use():
            print(f"[IEEE] 配额用尽，跳过 {conf['short']}")
            return []
        year = self._conf_year(conf)
        conf_state = state.setdefault("ieee", {}).setdefault(
            conf["short"], {"start_record": 1, "year": year})
        # 年份变了就重置游标
        if conf_state.get("year") != year:
            conf_state["start_record"] = 1
            conf_state["year"] = year

        papers = []
        MAX_RECORDS = 100

        while True:
            params = {
                "apikey": self.api_key,
                "querytext": conf["ieee_query"],
                "start_record": conf_state["start_record"],
                "max_records": MAX_RECORDS,
                "sort_order": "desc",
                "sort_field": "publication_date",
            }
            resp = throttled_get(self.BASE, params=params)
            Quota.consume()
            if resp.status_code != 200:
                print(f"[IEEE] {conf['short']} HTTP {resp.status_code}")
                break
            data = resp.json()
            articles = data.get("articles", [])
            total = data.get("total_records", 0)
            if not articles:
                break
            for a in articles:
                pub = a.get("publication_date", "")
                pub_date = None
                if pub:
                    try:
                        pub_date = datetime.strptime(pub, "%d %B %Y").date()
                    except Exception:
                        pass
                if pub_date and pub_date.year not in (year, year - 1):
                    continue
                p = self._base_paper(conf)
                p.title = a.get("title", "")
                p.doi = a.get("doi", "")
                p.abstract = a.get("abstract", "")
                p.url = a.get("html_url", "") or a.get("pdf_url", "")
                p.pdf_url = a.get("pdf_url", "")
                p.pub_date = pub_date
                authors = a.get("authors", {}).get("authors", [])
                p.authors = [x.get("full_name", "") for x in authors]
                papers.append(p)
            conf_state["start_record"] += len(articles)
            if conf_state["start_record"] > total:
                # 抓完就停在末尾，不再重置为 1
                break
            if not Quota.can_use():
                print(f"[IEEE] {conf['short']} 配额用尽，游标 {conf_state['start_record']}")
                break
        print(f"[IEEE] {conf['short']} ({year}): {len(papers)} papers")
        return papers
