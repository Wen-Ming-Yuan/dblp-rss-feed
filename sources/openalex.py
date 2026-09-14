import time
from core.http import get_session

OPENALEX = "https://api.openalex.org/works"


def enrich_abstracts(papers, mailto, batch_size=20):
    targets = [p for p in papers if not p.abstract and p.doi]
    if not targets:
        return papers
    session = get_session()
    for i in range(0, len(targets), batch_size):
        batch = targets[i:i + batch_size]
        doi_filter = "|".join(f"https://doi.org/{p.doi}" for p in batch if p.doi)
        if not doi_filter:
            continue
        params = {"filter": f"doi:{doi_filter}", "per-page": len(batch), "mailto": mailto}
        try:
            resp = session.get(OPENALEX, params=params, timeout=30)
            if resp.status_code != 200:
                print(f"[OpenAlex] HTTP {resp.status_code}")
                continue
            doi_map = {}
            for work in resp.json().get("results", []):
                doi = (work.get("doi") or "").lower().replace("https://doi.org/", "")
                inv = work.get("abstract_inverted_index")
                if inv:
                    doi_map[doi] = _reconstruct(inv)
            for p in batch:
                if p.doi and p.doi.lower() in doi_map:
                    p.abstract = doi_map[p.doi.lower()]
        except Exception as e:
            print(f"[OpenAlex] error: {e}")
        time.sleep(0.2)
    print(f"[OpenAlex] 摘要覆盖 {sum(1 for p in papers if p.abstract)}/{len(papers)}")
    return papers


def _reconstruct(inv):
    if not inv:
        return ""
    pos = []
    for w, idxs in inv.items():
        for i in idxs:
            pos.append((i, w))
    pos.sort()
    return " ".join(w for _, w in pos)
