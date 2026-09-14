def dedup_by_doi(papers):
    seen = {}
    for p in papers:
        k = p.dedup_key()
        if k not in seen:
            seen[k] = p
        else:
            prev = seen[k]
            # 字段合并：只覆盖空字段，不整对象替换
            if not prev.abstract and p.abstract:
                prev.abstract = p.abstract
            if not prev.pdf_url and p.pdf_url:
                prev.pdf_url = p.pdf_url
            if not prev.doi and p.doi:
                prev.doi = p.doi
            if not prev.pub_date and p.pub_date:
                prev.pub_date = p.pub_date
            if not prev.authors and p.authors:
                prev.authors = p.authors
    return list(seen.values())
