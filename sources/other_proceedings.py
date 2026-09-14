from datetime import date
from bs4 import BeautifulSoup
from sources.base import BaseSource
from core.http import get_session


class OtherProceedingsSource(BaseSource):
    name = "other"

    def fetch(self, conf, state):
        kind = conf.get("other_kind", "generic")
        url = conf.get("toc_url", "")
        if kind == "openreview":
            return self._openreview(conf)
        if not url:
            print(f"[Other] {conf['short']} 缺少 toc_url")
            return []
        resp = get_session().get(url, timeout=30)
        if resp.status_code != 200:
            print(f"[Other] {conf['short']} HTTP {resp.status_code}")
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        dispatch = {
            "acl": self._acl,
            "pmlr": self._pmlr,
            "nips": self._nips,
            "aaai": self._aaai,
            "siam": self._siam,
        }
        handler = dispatch.get(kind, self._generic)
        papers = handler(conf, soup, url)
        print(f"[Other/{kind}] {conf['short']}: {len(papers)} papers")
        return papers

    def _stamp(self, conf, p):
        p.pub_date = date(self._conf_year(conf), 1, 1)
        return p

    def _acl(self, conf, soup, base):
        papers = []
        for item in soup.select("p.d-sm-flex"):
            a = item.select_one("strong a")
            if not a:
                continue
            href = a.get("href", "")
            if href.startswith("/"):
                href = "https://aclanthology.org" + href
            p = self._base_paper(conf)
            p.title = a.get_text(strip=True)
            p.url = href
            papers.append(self._stamp(conf, p))
        return papers

    def _pmlr(self, conf, soup, base):
        papers = []
        for item in soup.select("div.paper"):
            a = item.select_one("p.title a")
            if not a:
                continue
            p = self._base_paper(conf)
            p.title = a.get_text(strip=True)
            p.url = a.get("href", "")
            papers.append(self._stamp(conf, p))
        return papers

    def _nips(self, conf, soup, base):
        papers = []
        for a in soup.select("a[href$='-Abstract.html'], a[href$='-Abstract-Conference.html']"):
            p = self._base_paper(conf)
            p.title = a.get_text(strip=True)
            href = a.get("href", "")
            if href.startswith("/"):
                href = "https://papers.nips.cc" + href
            p.url = href
            papers.append(self._stamp(conf, p))
        return papers

    def _aaai(self, conf, soup, base):
        papers = []
        for a in soup.select("h3.title a, a.obj_galley_link"):
            title = a.get_text(strip=True)
            if len(title) < 10:
                continue
            p = self._base_paper(conf)
            p.title = title
            p.url = a.get("href", "")
            papers.append(self._stamp(conf, p))
        return papers

    def _siam(self, conf, soup, base):
        papers = []
        for a in soup.select("h5.card-title a, a.article-title, a[href*='/doi/']"):
            title = a.get_text(strip=True)
            if len(title) < 10:
                continue
            href = a.get("href", "")
            if href.startswith("/"):
                href = "https://epubs.siam.org" + href
            p = self._base_paper(conf)
            p.title = title
            p.url = href
            papers.append(self._stamp(conf, p))
        return papers

    def _generic(self, conf, soup, base):
        papers = []
        for a in soup.select("a"):
            href = a.get("href", "")
            if "/doi/" not in href and "/article/" not in href and "openaccess" not in href:
                continue
            title = a.get_text(strip=True)
            if len(title) < 10:
                continue
            p = self._base_paper(conf)
            p.title = title
            p.url = href if href.startswith("http") else base + href
            papers.append(self._stamp(conf, p))
        return papers

    def _openreview(self, conf):
        api = "https://api2.openreview.net/notes"
        venue_id = conf.get("openreview_venue", "")
        if not venue_id:
            print(f"[OpenReview] {conf['short']} 缺少 openreview_venue")
            return []
        params = {"content.venueid": venue_id, "limit": 1000}
        resp = get_session().get(api, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"[OpenReview] {conf['short']} HTTP {resp.status_code}")
            return []
        papers = []
        for note in resp.json().get("notes", []):
            c = note.get("content", {})

            def _v(key):
                x = c.get(key)
                return x.get("value") if isinstance(x, dict) else x

            title = _v("title")
            if not title:
                continue
            p = self._base_paper(conf)
            p.title = title
            p.url = f"https://openreview.net/forum?id={note.get('id', '')}"
            p.doi = _v("doi")
            p.abstract = _v("abstract") or ""
            papers.append(self._stamp(conf, p))
        print(f"[OpenReview] {conf['short']}: {len(papers)} papers")
        return papers
