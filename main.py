import os
import yaml
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from sources import (
    AcmDlSource, UsenixSource, IeeeApiSource,
    SpringerSource, OtherProceedingsSource,
)
from sources.openalex import enrich_abstracts
from core.state import load_state, save_state
from core.dedup import dedup_by_doi
from core.rss_builder import build_rss

MAILTO = os.environ.get("OPENALEX_MAILTO", "")
if not MAILTO:
    print("[WARN] OPENALEX_MAILTO 未设置，OpenAlex 摘要补全会降速")
    MAILTO = "anonymous@example.com"

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "4"))


def main():
    # 支持 python main.py --source acm_dl 单源调试
    only_source = None
    if "--source" in sys.argv:
        idx = sys.argv.index("--source")
        if idx + 1 < len(sys.argv):
            only_source = sys.argv[idx + 1]
    confs = yaml.safe_load(open("config/conferences.yaml", encoding="utf-8"))
    if only_source:
        confs = [c for c in confs if c["source"] == only_source]
        print(f"[Filter] 只跑 source={only_source}，共 {len(confs)} 个会议")
    state = load_state("data/state.json")

    sources = {
        "acm_dl":   AcmDlSource(),
        "usenix":   UsenixSource(),
        "ieee":     IeeeApiSource(),
        "springer": SpringerSource(),
        "other":    OtherProceedingsSource(),
    }

    parallel = [c for c in confs if c["source"] != "ieee"]
    ieee_confs = [c for c in confs if c["source"] == "ieee"]

    all_papers = []
    # 约定：并行任务的 source 只能【只读】state，禁止修改 state。
    # 当前只有 IEEE 会写 state，而 IEEE 是串行跑的（见下方 for 循环）。
    # 若未来给某个并行 source 加写 state 逻辑，必须改为「返回 partial_state，
    # 主线程合并」的写法，否则会出现并发写覆盖。

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(sources[c["source"]].fetch, c, state): c
            for c in parallel
        }
        for fut in as_completed(futures):
            c = futures[fut]
            try:
                all_papers.extend(fut.result())
            except Exception as e:
                print(f"[ERROR] {c['short']}: {e}")

    # IEEE 串行（配额敏感 + 需要写 state）
    for c in ieee_confs:
        try:
            all_papers.extend(sources["ieee"].fetch(c, state))
        except Exception as e:
            print(f"[ERROR] {c['short']}: {e}")

    all_papers = dedup_by_doi(all_papers)
    all_papers = enrich_abstracts(all_papers, mailto=MAILTO)
    build_rss(all_papers, out_dir="output")
    save_state(state, "data/state.json")
    print(f"[DONE] 共 {len(all_papers)} 篇")


if __name__ == "__main__":
    main()
