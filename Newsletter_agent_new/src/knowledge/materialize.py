import uuid
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from typing import List, Optional

from src.knowledge.http_server import path_to_http_url
from src.config import ROOT


def strip_html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def url_to_markdown_file(url: str, dest_dir: Path) -> Optional[str]:
    try:
        title = ""; text = ""
        try:
            from newspaper import Article
            art = Article(url)
            art.download(); art.parse()
            title = (art.title or "").strip(); text = (art.text or "").strip()
        except Exception:
            pass
        if not text:
            headers = {"User-Agent": "Mozilla/5.0 (kb-materializer)"}
            r = requests.get(url, timeout=15, headers=headers)
            r.raise_for_status()
            text = strip_html_to_text(r.text)
        if not text:
            return None
        dest_dir.mkdir(parents=True, exist_ok=True)
        fname = f"mat_{uuid.uuid4().hex[:8]}.md"
        path = dest_dir / fname
        header = f"# {title or url}\n\n> Source: {url}\n\n"
        path.write_text(header + text, encoding="utf-8")
        return path_to_http_url(path)
    except Exception:
        return None


def materialize_urls_for_kb(urls: List[str]) -> List[str]:
    import os
    if os.getenv("PRE_CLEAN_HTML", "1") != "1":
        return urls
    out = []
    md_dir = ROOT / "materialized"
    for u in urls:
        if u.startswith("http://") or u.startswith("https://"):
            m = url_to_markdown_file(u, md_dir)
            out.append(m or u)
        else:
            out.append(u)
    return out