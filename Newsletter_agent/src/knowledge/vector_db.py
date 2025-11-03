import os
from agno.embedder.openai import OpenAIEmbedder
from agno.vectordb.qdrant import Qdrant
from agno.vectordb.lancedb import LanceDb, SearchType

from src.config import ROOT

def get_vector_db():
    qdrant_url = os.getenv("QDRANT_URL")
    if qdrant_url:
        return Qdrant(
            collection="newsletter_kb",
            url=qdrant_url,
            api_key=os.getenv("QDRANT_API_KEY"),
            embedder=OpenAIEmbedder(id="text-embedding-3-small"),
        )
    lancedb_dir = os.getenv("LANCEDB_DIR", ".lancedb")
    return LanceDb(
        uri=str(ROOT.joinpath(lancedb_dir)),
        table_name="newsletter_kb",
        search_type=SearchType.hybrid,
        embedder=OpenAIEmbedder(id="text-embedding-3-small"),
    )


def kb_search_urls(query: str, url_kb, k: int = 5):
    out = []
    try:
        vdb = getattr(url_kb, "vector_db", None)
        if vdb is None:
            return out
        results = vdb.search(text=query, limit=k)
        for r in results:
            meta = getattr(r, "metadata", {}) or {}
            url = meta.get("url") or meta.get("source") or meta.get("path") or ""
            out.append({
                "url": url,
                "score": getattr(r, "score", None),
                "text": (getattr(r, "text", "") or "")[:400],
            })
    except Exception:
        pass
    return out