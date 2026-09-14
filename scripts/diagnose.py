#!/usr/bin/env python3
"""
逐源诊断：只测一个会议，判断是 headers 问题、IP 问题还是选择器问题。
用法：
    python scripts/diagnose.py acm     # 测 SIGCOMM
    python scripts/diagnose.py usenix  # 测 OSDI
    python scripts/diagnose.py ieee    # 测 HPCA
    python scripts/diagnose.py all
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from sources.acm_dl import AcmDlSource
from sources.usenix import UsenixSource
from sources.ieee_api import IeeeApiSource

CONF_FILE = Path(__file__).resolve().parent.parent / "config" / "conferences.yaml"


def load_conf(short):
    confs = yaml.safe_load(CONF_FILE.read_text(encoding="utf-8"))
    for c in confs:
        if c["short"] == short:
            return c
    return None


def test_acm():
    conf = load_conf("SIGCOMM")
    print(f"=== ACM 诊断：{conf['short']} DOI={conf.get('proceedings_doi')} ===")
    try:
        src = AcmDlSource()
        papers = src.fetch(conf, {})
        print(f"结果：{len(papers)} 篇")
        if papers:
            print(f"  样例：{papers[0].title[:80]}")
            print(f"  日期样例：{papers[0].pub_date}")
    except Exception as e:
        import traceback
        print(f"异常：{e}")
        print(traceback.format_exc())


def test_usenix():
    conf = load_conf("OSDI")
    print(f"=== USENIX 诊断：{conf['short']} path={conf.get('usenix_path')} ===")
    try:
        src = UsenixSource()
        papers = src.fetch(conf, {})
        print(f"结果：{len(papers)} 篇")
        if papers:
            print(f"  样例：{papers[0].title[:80]}")
    except Exception as e:
        import traceback
        print(f"异常：{e}")
        print(traceback.format_exc())

def test_ieee():
    conf = load_conf("HPCA")
    print(f"=== IEEE 诊断：{conf['short']} ===")
    try:
        src = IeeeApiSource()
        papers = src.fetch(conf, {})
        print(f"结果：{len(papers)} 篇")
        if papers:
            print(f"  样例：{papers[0].title[:80]}")
    except RuntimeError as e:
        print(f"初始化失败：{e}")
        print("→ 检查 GitHub Secrets 里 IEEE_API_KEY 是否存在")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("acm", "all"):
        test_acm()
    if what in ("usenix", "all"):
        test_usenix()
    if what in ("ieee", "all"):
        test_ieee()
