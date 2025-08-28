import os
import sys
import csv
import json
import uuid
import io
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict

from dotenv import load_dotenv
from pydantic import BaseModel

# Agno core
from agno.agent import Agent, RunResponse
from agno.team import Team
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.newspaper4k import Newspaper4kTools
from agno.tools.reasoning import ReasoningTools

# Knowledge & Vector DBs
from agno.embedder.openai import OpenAIEmbedder
from agno.knowledge.url import UrlKnowledge
from agno.vectordb.qdrant import Qdrant
from agno.vectordb.lancedb import LanceDb, SearchType

# Utilities
import feedparser
from bs4 import BeautifulSoup
import base64
from openai import OpenAI
import requests
from PIL import Image
from urllib.parse import urljoin

# ---------- Config ----------
load_dotenv()
ROOT = Path(__file__).parent
OUT_DIR = Path(os.getenv("NEWSLETTER_OUT_DIR", "output"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_LANG = os.getenv("DEFAULT_LANGUAGE", "fr")

# ---------- Local HTTP server to serve materialized files ----------
_LOCAL_HTTPD = None
_LOCAL_HTTP_BASE = None

class _RootedHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence HTTP server logs
        pass

def start_local_http(root_dir: Path, port: Optional[int] = None) -> str:
    """Start a tiny HTTP server to serve files from root_dir."""
    global _LOCAL_HTTPD, _LOCAL_HTTP_BASE
    if _LOCAL_HTTPD is not None:
        return _LOCAL_HTTP_BASE
    port = port or int(os.getenv("LOCAL_HTTP_PORT", "8765"))
    handler = lambda *args, **kwargs: _RootedHandler(*args, directory=str(root_dir), **kwargs)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    _LOCAL_HTTPD = httpd
    _LOCAL_HTTP_BASE = f"http://127.0.0.1:{port}"
    print(f"[HTTP] Serving {root_dir} at {_LOCAL_HTTP_BASE}")
    return _LOCAL_HTTP_BASE

def path_to_http_url(path: Path) -> str:
    base = start_local_http(ROOT)
    rel = path.resolve().relative_to(ROOT.resolve())
    return f"{base}/{str(rel).replace(os.sep, '/')}"

# ---------- HTML → text/Markdown materialization ----------

def strip_html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


def url_to_markdown_file(url: str, dest_dir: Path) -> Optional[str]:
    """Download article, extract main text, save as .md and return HTTP URL."""
    try:
        title = ""
        text = ""
        # Try newspaper4k first
        try:
            from newspaper import Article
            art = Article(url)
            art.download(); art.parse()
            title = (art.title or "").strip()
            text = (art.text or "").strip()
        except Exception:
            pass
        # Fallback: raw HTML + BS4
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
    """If PRE_CLEAN_HTML=1, convert each HTTP URL to a local .md served over HTTP."""
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

# ---------- Vector DB ----------

def get_vector_db():
    qdrant_url = os.getenv("QDRANT_URL")
    if qdrant_url:
        return Qdrant(
            collection="newsletter_kb",
            url=qdrant_url,
            api_key=os.getenv("QDRANT_API_KEY"),
            embedder=OpenAIEmbedder(id="text-embedding-3-small"),
        )
    # Fallback to LanceDB on disk
    lancedb_dir = os.getenv("LANCEDB_DIR", ".lancedb")
    return LanceDb(
        uri=str(ROOT.joinpath(lancedb_dir)),
        table_name="newsletter_kb",
        search_type=SearchType.hybrid,
        embedder=OpenAIEmbedder(id="text-embedding-3-small"),
    )

# ---------- Knowledge base ----------

def build_knowledge_bases(sources_yaml: Path):
    import yaml
    with open(sources_yaml, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    vector_db = get_vector_db()
    url_kb = UrlKnowledge(urls=[], vector_db=vector_db)
    return cfg, vector_db, url_kb

# ---------- ArXiv & RSS ----------

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


def rss_to_urls(rss_urls: List[str], limit_per_feed: int = 10) -> List[str]:
    urls = []
    for feed_url in rss_urls:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:limit_per_feed]:
                link = getattr(entry, "link", None)
                if link:
                    urls.append(link)
        except Exception:
            continue
    return list(dict.fromkeys(urls))

# ---------- LinkedIn CSV ----------

def read_linkedin_csv(csv_path: Optional[str]) -> List[Dict[str, str]]:
    items = []
    if not csv_path:
        return items
    p = Path(csv_path)
    if not p.exists():
        return items
    with p.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append({k: (v or "").strip() for k, v in row.items()})
    return items

# ---------- Image detection from sources ----------
DEFAULT_IMG_KEYWORDS = [
    "ia", "intelligence artificielle", "artificial intelligence", "ai",
    "machine learning", "apprentissage", "neuronal", "neurone", "neural",
    "llm", "agents", "genai", "transformer",
]


def _download_and_probe_image(img_url: str, dest_dir: Path):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (image-detector)"}
        r = requests.get(img_url, timeout=12, stream=True, headers=headers)
        r.raise_for_status()
        content = r.content
        im = Image.open(io.BytesIO(content)).convert("RGB")
        width, height = im.size
        fname = f"det_{uuid.uuid4().hex[:8]}.png"
        path = dest_dir.joinpath(fname)
        im.save(path, format="PNG")
        return str(path), width, height
    except Exception:
        return None


def _score_candidate(width: int, height: int, alt: str, keywords: List[str]) -> float:
    area = width * height
    ar = width / max(1, height)
    score = min(area / 1_000_000.0, 4.0)
    if ar >= 1.5:
        score += 0.6
    alt_l = (alt or "").lower()
    if any(k.lower() in alt_l for k in keywords):
        score += 1.0
    if width >= 1400:
        score += 0.4
    if height >= 700:
        score += 0.3
    return round(score, 3)


def _is_image_safe(local_path: str) -> bool:
    if os.getenv("ENABLE_VISION_SAFETY", "0") != "1":
        return True
    try:
        client = OpenAI()
        with open(local_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        data_url = f"data:image/png;base64,{b64}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Dis 'OK' si l'image est adaptée à une newsletter tech (pas de nudité explicite, violence graphique, haine). Sinon 'REFUSER'."},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ]
        resp = client.chat.completions.create(model="gpt-4o-mini", messages=messages, max_tokens=10)
        txt = (resp.choices[0].message.content or "").lower()
        return ("ok" in txt) and ("refuser" not in txt)
    except Exception as e:
        print(f"[Warn] Vision safety failed: {e}")
        return True


def _fetch_page_images(source_url: str, dest_dir: Path, keywords: List[str], min_w: int, min_h: int, max_imgs: int = 3):
    headers = {"User-Agent": "Mozilla/5.0 (image-detector)"}
    out = []
    try:
        r = requests.get(source_url, timeout=12, headers=headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        imgs = soup.find_all("img")
        count = 0
        for tag in imgs:
            src = tag.get("src") or tag.get("data-src") or tag.get("data-original")
            if not src:
                continue
            abs_url = urljoin(source_url, src)
            alt = tag.get("alt", "")
            probed = _download_and_probe_image(abs_url, dest_dir)
            if not probed:
                continue
            local_path, w, h = probed
            if w < min_w or h < min_h:
                try:
                    os.remove(local_path)
                except Exception:
                    pass
                continue
            if not _is_image_safe(local_path):
                try:
                    os.remove(local_path)
                except Exception:
                    pass
                continue
            score = _score_candidate(w, h, alt, keywords)
            out.append({
                "local_path": local_path,
                "source_page": source_url,
                "width": w,
                "height": h,
                "alt": alt,
                "score": score,
            })
            count += 1
            if count >= max_imgs:
                break
    except Exception as e:
        print(f"[Img] {source_url}: {e}")
    return out


def detect_best_header_image(url_kb: UrlKnowledge, cfg: dict, out_dir: Path, date: str) -> Optional[Path]:
    max_pages = int(os.getenv("IMAGE_DETECT_MAX_PAGES", "20"))
    min_w = int(os.getenv("IMAGE_MIN_WIDTH", "900"))
    min_h = int(os.getenv("IMAGE_MIN_HEIGHT", "500"))
    keywords = cfg.get("keywords", DEFAULT_IMG_KEYWORDS)

    dest = out_dir.joinpath("assets", date)
    dest.mkdir(parents=True, exist_ok=True)

    urls = url_kb.urls[:max_pages]
    all_cands = []
    for u in urls:
        all_cands.extend(_fetch_page_images(u, dest, keywords, min_w, min_h, max_imgs=3))

    if not all_cands:
        return None
    best = max(all_cands, key=lambda c: c["score"])
    return Path(best["local_path"])

# ---------- Schemas ----------
class RawItem(BaseModel):
    id: str
    url: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    source: Optional[str] = None  # arxiv|rss|web|linkedin
    authors: Optional[List[str]] = None
    published_at: Optional[str] = None
    content_hint: Optional[str] = None

class CuratedItem(RawItem):
    topic: str
    quality_score: float = 0.0
    rationale: str = ""

class Cluster(BaseModel):
    topic: str
    summary: str
    items: List[CuratedItem]

class Newsletter(BaseModel):
    title: str
    date: str
    editor_note: str
    highlights: List[str]
    sections: List[Dict[str, str]]  # {heading, body}
    references: List[str]

# ---------- Agents ----------

def collector_agent(url_kb: UrlKnowledge) -> Agent:
    return Agent(
        name="Collector",
        role=(
            "Récupère des sources (arXiv, RSS, web explicite). "
            "Pour chaque lien, extrait titre/auteurs/date et ajoute au KB."
        ),
        model=OpenAIChat(id="gpt-4o-mini"),
        tools=[DuckDuckGoTools(), Newspaper4kTools()],
        knowledge=url_kb,
        show_tool_calls=True,
        markdown=True,
        instructions=[
            "Toujours retourner des JSON linéarisés si demandé.",
            "Citer les URL trouvées.",
        ],
    )


def curator_agent(url_kb: UrlKnowledge) -> Agent:
    return Agent(
        name="Curator",
        role=(
            "Clusterise les items par sujet et évalue leur qualité selon: "
            "nouveauté, crédibilité (citations/sources), clarté, impact potentiel."
        ),
        model=OpenAIChat(id="gpt-4o"),
        tools=[ReasoningTools(add_instructions=True)],
        knowledge=url_kb,
        show_tool_calls=True,
        markdown=True,
        instructions=[
            "Toujours produire des topics concis (2–5 mots).",
            "Expliquer la priorisation en 1–2 phrases par cluster.",
        ],
    )


def writer_agent(url_kb: UrlKnowledge, language: str = "fr") -> Agent:
    return Agent(
        name="Writer",
        role=(
            "Rédige une newsletter structurée, claire, sourcée, dans la langue cible. "
            "Inclut: Highlights, À la une, Papiers, Outils/Librairies, Réseaux."
        ),
        model=OpenAIChat(id="gpt-4o"),
        knowledge=url_kb,
        show_tool_calls=True,
        markdown=True,
        instructions=[
            f"Langue: {language}.",
            "Chaque affirmation importante est sourcée (liens).",
            "Tonalité: concise, professionnelle, accessible.",
        ],
    )

# ---------- RAG Agent & search helpers ----------

def rag_agent(url_kb: UrlKnowledge, language: str = "fr") -> Agent:
    return Agent(
        name="RAG-QA",
        role=(
            "Répondre aux questions en s'appuyant UNIQUEMENT sur la base de connaissances. "
            "Toujours citer les sources avec leurs URL. Si l'info manque, le dire."
        ),
        model=OpenAIChat(id="gpt-4o"),
        knowledge=url_kb,
        show_tool_calls=True,
        markdown=False,
        instructions=[
            f"Langue: {language}.",
            "Si le contexte contient du HTML, ignore les balises et ne conserve que le texte.",
            "Toujours renvoyer un JSON strict avec 'answer' (4–10 phrases) et 'citations' (url, title).",
            "Ne pas inventer d'URL.",
        ],
    )


def kb_search_urls(query: str, url_kb: UrlKnowledge, k: int = 5) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
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

# ---------- Team orchestrator ----------

def build_team(collector: Agent, curator: Agent, writer: Agent) -> Team:
    return Team(
        name="Newsletter Team",
        mode="coordinate",
        model=OpenAIChat(id="gpt-4o-mini"),
        members=[collector, curator, writer],
        success_criteria=(
            "Une newsletter cohérente avec 4–6 sections, 6–12 liens, "
            "citations claires et un ton homogène."
        ),
        show_members_responses=True,
        show_tool_calls=True,
        markdown=True,
    )

# ---------- Image prompt crafting & generation ----------

def prompt_crafter_agent() -> Agent:
    return Agent(
        name="ArtDirector",
        role=(
            "Conçoit un prompt d'image original inspiré du contenu de la newsletter : "
            "métaphores, éléments visuels, ambiance. Pas de texte dans l'image."
        ),
        model=OpenAIChat(id="gpt-4o-mini"),
        markdown=False,
        instructions=[
            "Le prompt doit tenir en 1–2 phrases (max 60 mots).",
            "Décrire le sujet, le cadrage/angle, l'ambiance/couleurs, le style (illustration/3D/flat).",
            "Aucune info sensible ni logos de marques. Pas de texte dans l'image.",
        ],
    )


def craft_image_prompt_from_newsletter(news_md: str) -> str:
    art = prompt_crafter_agent()
    resp = art.run(
        """
À partir de la newsletter ci-dessous, écris un UNIQUE prompt d'image qui symbolise l'actualité IA de la semaine.
Contraintes :
- Pas de texte dans l'image.
- Style cohérent avec une newsletter tech professionnelle.
- Mentionner cadrage (ex: wide banner), ambiance et 1–2 éléments clés (ex: neurones, circuits, globe, ville, personnes au travail).
Retourne UNIQUEMENT le prompt, sans commentaire.
---
"""
        + news_md
    )
    return (resp.content or "")[:500].strip()


def generate_header_image(prompt: str, out_dir: Path, date: str, size: str = "1024x1024") -> Path:
    client = OpenAI()
    res = client.images.generate(model="gpt-image-1", prompt=prompt, size=size)
    b64 = res.data[0].b64_json
    img_bytes = base64.b64decode(b64)
    out_path = out_dir.joinpath(f"banner_{date}.png")
    with open(out_path, "wb") as f:
        f.write(img_bytes)
    (out_dir / f"banner_prompt_{date}.txt").write_text(prompt, encoding="utf-8")
    return out_path

# ---------- Ingestion pipeline ----------

def ingest_sources(cfg: dict, url_kb: UrlKnowledge):
    all_urls: List[str] = []

    # 1) ArXiv
    arxiv_cfg = cfg.get("arxiv", {})
    queries: List[str] = arxiv_cfg.get("queries", [])
    if queries:
        print("[Ingest] Fetching ArXiv search results -> URLs ...")
        max_results = int(arxiv_cfg.get("max_results", 15))
        all_urls.extend(arxiv_queries_to_urls(queries, max_results=max_results))

    # 2) RSS
    rss_list = cfg.get("rss", [])
    if rss_list:
        print("[Ingest] Fetching RSS feeds -> URLs ...")
        all_urls.extend(rss_to_urls(rss_list, limit_per_feed=10))

    # 3) Explicit web
    web_urls = cfg.get("web", [])
    if web_urls:
        all_urls.extend(web_urls)

    # 4) LinkedIn CSV → local .md served over HTTP
    li_csv = cfg.get("linkedin", {}).get("csv_path")
    li_items = read_linkedin_csv(li_csv)
    if li_items:
        tmp_dir = ROOT.joinpath("tmp"); tmp_dir.mkdir(parents=True, exist_ok=True)
        md_files = []
        for row in li_items:
            fname = tmp_dir.joinpath(f"li_{uuid.uuid4().hex[:8]}.md")
            with fname.open("w", encoding="utf-8") as f:
                f.write(f"# LinkedIn Post\n\n")
                f.write(f"URL: {row.get('url','')}\n\n")
                f.write(f"Auteur: {row.get('author','')}\n\n")
                f.write(f"Date: {row.get('date','')}\n\n")
                f.write(row.get("text", ""))
            md_files.append(fname)
        all_urls.extend([path_to_http_url(p) for p in md_files])

    # 5) Materialize HTTP pages to local .md (optional)
    all_urls = list(dict.fromkeys(all_urls))  # de-dup preserve order
    final_urls = materialize_urls_for_kb(all_urls)

    if final_urls:
        print(f"[Ingest] Loading {len(final_urls)} URLs -> KB ...")
        url_kb.urls.extend(final_urls)
        recreate = os.getenv("KB_RECREATE", "0") == "1"
        url_kb.load(recreate=recreate, upsert=True)

# ---------- End-to-end run ----------

def run_once(sources_file: str = "sources.yaml") -> Path:
    cfg, vector_db, url_kb = build_knowledge_bases(Path(sources_file))
    ingest_sources(cfg, url_kb)

    collector = collector_agent(url_kb)
    curator = curator_agent(url_kb)
    writer = writer_agent(url_kb, language=DEFAULT_LANG)
    team = build_team(collector, curator, writer)

    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""
Objectif: produire une newsletter hebdomadaire sur l'IA (date {today}).

Étapes:
1) Collector: consolide ~30+ items depuis KB (arXiv, RSS, web explicite, LinkedIn CSV).
   Retour: JSON avec 'items' [title, url, authors?, published_at?, short_summary].
2) Curator: regroupe par sujets (3–6 clusters) et calcule un quality_score (0–3).
   Retour: clusters structurés avec rationale.
3) Writer: rédige une newsletter compacte (900–1400 mots) avec:
   - Titre, Note d'éditeur (3–4 lignes), Highlights (5 puces),
   - 4–6 sections thématiques (chacune: 2–3 paragraphes + 2–3 liens),
   - Références (liste de tous les liens cités).
   - Style: clair, synthétique, sourcé, en français.
Contraintes:
   - Ne jamais inventer de liens; utiliser ceux présents en KB ou fournis par Collector.
   - Citer les sources avec URL entre parenthèses.
   - Aucun jargon inutile; expliquer brièvement les termes spécialisés.
"""

    print("[Team] Running end-to-end ...")
    run: RunResponse = team.run(prompt)

    md = run.content if isinstance(run.content, str) else str(run.content)

    header_mode = os.getenv("HEADER_IMAGE_MODE", "auto").lower().strip()
    selected_banner: Optional[Path] = None
    try:
        if header_mode in ("detect", "auto"):
            selected_banner = detect_best_header_image(url_kb, cfg, OUT_DIR, today)
    except Exception as e:
        print(f"[Warn] Image detection failed: {e}")

    if selected_banner is not None and selected_banner.exists():
        md = f"![Illustration IA]({selected_banner.name})\n\n" + md
    else:
        image_prompt = os.getenv("NEWSLETTER_IMAGE_PROMPT", "").strip()
        try:
            if not image_prompt:
                image_prompt = craft_image_prompt_from_newsletter(md)
            banner_path = generate_header_image(image_prompt, OUT_DIR, today, size="1024x1024")
            md = f"![Illustration IA]({banner_path.name})\n\n" + md
        except Exception as e:
            print(f"[Warn] Image generation skipped: {e}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR.joinpath(f"newsletter_{today}.md")
    out_path.write_text(md, encoding="utf-8")
    print(f"[OK] Wrote {out_path}")
    return out_path

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: Set OPENAI_API_KEY in your environment or .env", file=sys.stderr)
        sys.exit(1)
    out = run_once()
    print(out)