import os
import uuid
from pathlib import Path
from typing import List

from src.config import ROOT
from src.knowledge.materialize import materialize_urls_for_kb
from src.ingestion.arxiv_ingest import arxiv_queries_to_urls
from src.ingestion.rss_ingest import rss_to_urls
from src.ingestion.linkedin import read_linkedin_csv


def ingest_sources(cfg: dict, url_kb):
    all_urls: List[str] = []

    # 1) ArXiv
    arxiv_cfg = cfg.get("arxiv", {})
    queries = arxiv_cfg.get("queries", [])
    if queries:
        print("[Ingest] ArXiv search → URLs …")
        max_results = int(arxiv_cfg.get("max_results", 15))
        all_urls.extend(arxiv_queries_to_urls(queries, max_results=max_results))

    # 2) RSS
    rss_list = cfg.get("rss", [])
    if rss_list:
        print("[Ingest] RSS → URLs …")
        all_urls.extend(rss_to_urls(rss_list, limit_per_feed=10))

    # 3) Web explicites
    web_urls = cfg.get("web", [])
    if web_urls:
        all_urls.extend(web_urls)

    # 4) LinkedIn CSV → fichiers .md locaux servis en HTTP
    li_csv = cfg.get("linkedin", {}).get("csv_path")
    li_items = read_linkedin_csv(li_csv)
    if li_items:
        tmp_dir = ROOT.joinpath("tmp"); tmp_dir.mkdir(parents=True, exist_ok=True)
        for row in li_items:
            fname = tmp_dir.joinpath(f"li_{uuid.uuid4().hex[:8]}.md")
            fname.write_text(
                "# LinkedIn Post\n\n" +
                f"URL: {row.get('url','')}\n\n" +
                f"Auteur: {row.get('author','')}\n\n" +
                f"Date: {row.get('date','')}\n\n" +
                (row.get("text", "") or ""),
                encoding="utf-8"
            )
            # converti en URL via serveur HTTP local (fait par materialize si nécessaire)
            all_urls.append(str(fname))

    # 5) Matérialisation HTML → .md servi en HTTP
    final_urls = materialize_urls_for_kb(list(dict.fromkeys(all_urls)))

    if final_urls:
        print(f"[Ingest] Loading {len(final_urls)} URLs → KB …")
        url_kb.urls.extend(final_urls)
        recreate = os.getenv("KB_RECREATE", "0") == "1"
        url_kb.load(recreate=recreate, upsert=True)