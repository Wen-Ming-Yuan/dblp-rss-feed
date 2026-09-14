from pathlib import Path
from feedgen.feed import FeedGenerator
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape


def _fmt_authors(authors):
    return xml_escape(", ".join(authors[:8]))


def _fmt_abstract(text):
    """转义 + 换行转 <br/>，保证 CDATA 内渲染正常。"""
    if not text:
        return ""
    return xml_escape(text).replace("\n", "<br/>").replace("\r", "")


def build_rss(papers, out_dir="output",
              site_url="https://wen-ming-yuan.github.io/dblp-rss-feed/"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    by_venue = {}
    for p in papers:
        by_venue.setdefault(p.venue_short, []).append(p)

    for venue, items in by_venue.items():
        fg = FeedGenerator()
        fg.id(f"{site_url}{venue}.xml")
        fg.title(f"CCF-A: {venue}")
        fg.link(href=site_url, rel="alternate")
        fg.description(f"{items[0].venue_full} (CCF-A) 最新论文")
        fg.language("zh-CN")

        sorted_items = sorted(
            items,
            key=lambda x: x.pub_date or datetime(1970, 1, 1).date(),
            reverse=True,
        )
        for p in sorted_items:
            fe = fg.add_entry()
            fe.id(p.url or p.doi or p.title)
            fe.title(p.title)
            link = p.url or (f"https://doi.org/{p.doi}" if p.doi else site_url)
            fe.link(href=link)

            parts = [
                f"<b>会议:</b> {xml_escape(p.venue_full)} ({xml_escape(p.venue_short)})",
                f"<b>CCF:</b> {xml_escape(p.ccf_level)} / {xml_escape(p.ccf_category)}",
                f"<b>作者:</b> {_fmt_authors(p.authors)}",
            ]
            if p.doi:
                parts.append(
                    f'<b>DOI:</b> <a href="https://doi.org/{xml_escape(p.doi)}">'
                    f'{xml_escape(p.doi)}</a>'
                )
            if p.pdf_url:
                parts.append(
                    f'<b>PDF:</b> <a href="{xml_escape(p.pdf_url)}">直达</a>'
                )
            if p.abstract:
                parts.append(f"<p>{_fmt_abstract(p.abstract)}</p>")

            fe.description("<br/>".join(parts), cdata=True)

            if p.pub_date:
                fe.pubDate(datetime.combine(
                    p.pub_date, datetime.min.time()
                ).replace(tzinfo=timezone.utc))

        fg.rss_file(str(out / f"{venue}.xml"), pretty=True)
        print(f"[RSS] {venue}.xml ({len(items)} entries)")

    # 汇总 all.xml —— 修复换行
    fg = FeedGenerator()
    fg.id(site_url)
    fg.title("CCF-A 全部会议汇总")
    fg.link(href=site_url, rel="alternate")
    fg.description("所有追踪的 CCF-A 会议新论文")
    for p in sorted(papers,
                    key=lambda x: x.pub_date or datetime(1970, 1, 1).date(),
                    reverse=True)[:500]:
        fe = fg.add_entry()
        fe.id(p.url or p.doi or p.title)
        fe.title(f"[{p.venue_short}] {p.title}")
        fe.link(href=p.url or (f"https://doi.org/{p.doi}" if p.doi else site_url))
        fe.description(_fmt_abstract(p.abstract or ""), cdata=True)
    fg.rss_file(str(out / "all.xml"), pretty=True)
