import argparse
from datetime import datetime
from pathlib import Path

from src.config import DEFAULT_LANG, OUT_DIR
from src.knowledge.kb import build_knowledge_bases
from src.ingestion.ingest import ingest_sources
from src.agents.collector import collector_agent
from src.agents.curator import curator_agent
from src.agents.writer import writer_agent
from src.agents.team import build_team
from src.images.detect import detect_best_header_image
from src.images.generate import craft_image_prompt_from_newsletter, generate_header_image


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
Étapes: Collector → Curator → Writer. Contraintes: pas d'invention de liens; style clair; sources citées.
"""
    run = team.run(prompt)
    md = run.content if isinstance(run.content, str) else str(run.content)

    banner = None
    try:
        from os import getenv
        if getenv("HEADER_IMAGE_MODE", "auto").lower().strip() in ("detect", "auto"):
            banner = detect_best_header_image(url_kb, {}, OUT_DIR, today)
    except Exception:
        pass
    if not banner:
        img_prompt = ""
        try:
            img_prompt = craft_image_prompt_from_newsletter(md)
            banner = generate_header_image(img_prompt, OUT_DIR, today, size="1024x1024")
        except Exception:
            banner = None
    if banner and banner.exists():
        md = f"![Illustration IA]({banner.name})\n\n" + md

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR.joinpath(f"newsletter_{today}.md")
    out_path.write_text(md, encoding="utf-8")
    print(f"[OK] Wrote {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="sources.yaml")
    args = ap.parse_args()
    run_once(args.sources)

if __name__ == "__main__":
    main()
