from typing import List

def arxiv_queries_to_urls(queries: List[str], max_results: int = 15) -> List[str]:
    import arxiv as arx
    urls: List[str] = []
    for q in queries:
        search = arx.Search(query=q, max_results=max_results, sort_by=arx.SortCriterion.SubmittedDate)
        for r in search.results():
            if r.entry_id:
                urls.append(r.entry_id)
    # de-dup preserve order
    seen = set(); ordered = []
    for u in urls:
        if u not in seen:
            ordered.append(u); seen.add(u)
    return ordered
