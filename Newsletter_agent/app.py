import os
import json
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from Newsletter_agent.newsletter_system import (
    build_knowledge_bases,
    ingest_sources,
    collector_agent,
    curator_agent,
    writer_agent,
    build_team,
    craft_image_prompt_from_newsletter,
    generate_header_image,
    detect_best_header_image,
    OUT_DIR,
    rag_agent,
    kb_search_urls,
)

load_dotenv()

st.set_page_config(
    page_title="Newsletter IA — Agno Agents",
    page_icon="📰",
    layout="wide",
)

# ---------- Helpers ----------
def _parse_rag_json(raw: str):
    import re, json
    if not raw:
        return {"answer": "", "citations": []}
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{[\s\S]*\}$", raw.strip())
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"answer": raw, "citations": []}


def _render_rag_answer(data: dict):
    ans = (data or {}).get("answer", "")
    cites = (data or {}).get("citations", []) or []

    st.markdown("### 🧠 Réponse")
    st.markdown(ans)

    if cites:
        st.markdown("### 🔗 Sources")
        for i, c in enumerate(cites, 1):
            url = c.get("url") or ""
            title = c.get("title") or url or f"Source {i}"
            st.markdown(f"{i}. [{title}]({url})" if url else f"{i}. {title}")
        with st.expander("Aperçu JSON (debug)"):
            st.json(data)

# ---------- Sidebar ----------
st.sidebar.header("Configuration")
mode = st.sidebar.radio("Mode", ["Newsletter", "RAG Q&A"], index=0)

openai_key_input = st.sidebar.text_input(
    "OpenAI API Key",
    type="password",
    value=os.getenv("OPENAI_API_KEY", ""),
    help="Utilisée en local uniquement. Peut aussi être définie via .env.",
)
if openai_key_input:
    os.environ["OPENAI_API_KEY"] = openai_key_input

lang = st.sidebar.selectbox("Langue", ["fr", "en"], index=0)
os.environ["DEFAULT_LANGUAGE"] = lang

st.sidebar.markdown("---")
use_qdrant = st.sidebar.checkbox(
    "Utiliser Qdrant (sinon LanceDB local)", value=bool(os.getenv("QDRANT_URL"))
)
if use_qdrant:
    qdrant_url = st.sidebar.text_input(
        "QDRANT_URL",
        value=os.getenv("QDRANT_URL", "http://localhost:6333"),
    )
    qdrant_key = st.sidebar.text_input(
        "QDRANT_API_KEY (optionnel)", type="password", value=os.getenv("QDRANT_API_KEY", "")
    )
    os.environ["QDRANT_URL"] = qdrant_url
    if qdrant_key:
        os.environ["QDRANT_API_KEY"] = qdrant_key
else:
    os.environ.pop("QDRANT_URL", None)
    os.environ.pop("QDRANT_API_KEY", None)

st.sidebar.markdown("---")
src_file = st.sidebar.file_uploader(
    "sources.yaml (sinon exemple interne)", type=["yaml", "yml"], accept_multiple_files=False
)
li_csv = st.sidebar.file_uploader(
    "LinkedIn CSV (optionnel) — colonnes: url,text,author,date",
    type=["csv"],
    accept_multiple_files=False,
)

st.sidebar.markdown("---")
img_prompt = st.sidebar.text_area(
    "Prompt image (optionnel, pour l'illustration d'en-tête)",
    value=os.getenv("NEWSLETTER_IMAGE_PROMPT", ""),
    help="Laisse vide pour générer automatiquement un prompt à partir de la newsletter.",
)

# ---------- Body ----------
st.title("📰 Newsletter IA — Multi‑agents (Agno + OpenAI)")
st.caption("Collecte → Tri → Rédaction — et RAG sur la base vectorielle.")

# Load sources.yaml (uploaded or bundled example)
if src_file is not None:
    sources_path = Path(tempfile.gettempdir()) / f"sources_{datetime.now().timestamp()}.yaml"
    sources_path.write_bytes(src_file.read())
    st.success("sources.yaml chargé depuis l'upload.")
else:
    default_sources = (Path(__file__).parent / "sources.yaml").read_text(encoding="utf-8")
    sources_path = Path(tempfile.gettempdir()) / "sources_example.yaml"
    sources_path.write_text(default_sources, encoding="utf-8")
    st.info("Aucun sources.yaml uploadé — utilisation de l'exemple embarqué.")

# If a LinkedIn CSV is provided, save to temp path and patch YAML at runtime
li_csv_path = None
if li_csv is not None:
    li_csv_path = Path(tempfile.gettempdir()) / f"linkedin_{datetime.now().timestamp()}.csv"
    li_csv_path.write_bytes(li_csv.read())

if mode == "Newsletter":
    # Buttons always available
    col1, col2 = st.columns([1, 1])
    with col1:
        ingest_clicked = st.button("📥 Ingestion des sources", type="primary")
    with col2:
        generate_clicked = st.button("🖊️ Générer la newsletter")

    if "last_markdown" not in st.session_state:
        st.session_state.last_markdown = None
    if "last_banner_path" not in st.session_state:
        st.session_state.last_banner_path = None

    if ingest_clicked:
        if not os.getenv("OPENAI_API_KEY"):
            st.error("Veuillez renseigner votre OpenAI API Key (sidebar) ou via .env.")
        else:
            import yaml
            raw_cfg = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
            if li_csv_path is not None:
                raw_cfg.setdefault("linkedin", {})["csv_path"] = str(li_csv_path)
                patched = Path(tempfile.gettempdir()) / "sources_patched.yaml"
                patched.write_text(yaml.dump(raw_cfg, allow_unicode=True), encoding="utf-8")
                sources_path = patched

            with st.spinner("Chargement des connaissances et indexation…"):
                cfg, vector_db, url_kb = build_knowledge_bases(sources_path)
                ingest_sources(cfg, url_kb)
            st.success("Ingestion terminée. Prêt pour la génération prête ✅")
            st.toast("Documents indexée", icon="✅")

    if generate_clicked:
        if not os.getenv("OPENAI_API_KEY"):
            st.error("Veuillez renseigner votre OpenAI API Key (sidebar) ou via .env.")
        else:
            cfg, vector_db, url_kb = build_knowledge_bases(sources_path)

            collector = collector_agent(url_kb)
            curator = curator_agent(url_kb)
            writer = writer_agent(url_kb, language=os.getenv("DEFAULT_LANGUAGE", "fr"))
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

            with st.spinner("Les agents réfléchissent, trient et rédigent…"):
                team_run = team.run(prompt)

            md = team_run.content if isinstance(team_run.content, str) else str(team_run.content)

            # Header image: prefer detection then generation
            banner_path = None
            try:
                os.environ.setdefault("HEADER_IMAGE_MODE", "auto")
                if os.getenv("HEADER_IMAGE_MODE", "auto").lower().strip() in ("detect", "auto"):
                    banner_path = detect_best_header_image(url_kb, {}, OUT_DIR, datetime.now().strftime("%Y-%m-%d"))
            except Exception as e:
                st.warning(f"Détection image échouée: {e}")

            if not banner_path:
                try:
                    prompt_img = (img_prompt or "").strip()
                    if not prompt_img:
                        prompt_img = craft_image_prompt_from_newsletter(md)
                    banner_path = generate_header_image(prompt_img, OUT_DIR, datetime.now().strftime("%Y-%m-%d"), size="1024x1024")
                except Exception as e:
                    st.warning(f"Illustration non générée: {e}")

            if banner_path and Path(banner_path).exists():
                md = f"![Illustration IA]({Path(banner_path).name})\n\n" + md

            st.session_state.last_markdown = md
            st.session_state.last_banner_path = str(banner_path) if banner_path else None
            st.success("Newsletter générée ✅")

    # Preview & download
    if st.session_state.get("last_markdown"):
        st.markdown("## Aperçu de la newsletter")
        if st.session_state.get("last_banner_path") and Path(st.session_state["last_banner_path"]).exists():
            st.image(st.session_state["last_banner_path"], caption="Illustration d'en-tête")
        st.markdown(st.session_state["last_markdown"])

        filename = f"newsletter_{datetime.now().strftime('%Y-%m-%d')}.md"
        st.download_button(
            label="💾 Télécharger le Markdown",
            data=st.session_state["last_markdown"].encode("utf-8"),
            file_name=filename,
            mime="text/markdown",
        )

        html_doc = f"""
<html><head><meta charset='utf-8'><title>{filename}</title></head>
<body>
{st.session_state['last_markdown']}
</body></html>
"""
        st.download_button(
            label="💾 Télécharger en HTML (simple)",
            data=html_doc.encode("utf-8"),
            file_name=filename.replace(".md", ".html"),
            mime="text/html",
        )

else:
    st.subheader("🔎 RAG — Interroger la base vectorielle")
    q = st.text_area(
        "Votre question",
        placeholder="Ex: Quelles sont les avancées récentes sur les agents multimodaux ?",
        height=100
    )
    c1, c2 = st.columns([1,1])
    with c1:
        topk = st.number_input("Top documents (indicatif)", min_value=1, max_value=10, value=5, step=1)
    with c2:
        show_hits = st.checkbox("Montrer les documents les plus proches", value=True)

    run_q = st.button("Poser la question")

    if run_q:
        if not os.getenv("OPENAI_API_KEY"):
            st.error("Veuillez renseigner votre OpenAI API Key (sidebar) ou via .env.")
        else:
            cfg, vector_db, url_kb = build_knowledge_bases(sources_path)
            if not hasattr(url_kb, "vector_db"):
                st.error("La base de connaissances n'est pas initialisée.")
            else:
                qa = rag_agent(url_kb, language=lang)
                with st.spinner("Recherche dans la base et rédaction de la réponse…"):
                    resp = qa.run(
                        f"""
Tu es un assistant RAG. Réponds à la question ci-dessous en t'appuyant UNIQUEMENT sur les documents de la base. 
Retourne STRICTEMENT un JSON avec:
- "answer": une réponse en {lang} (markdown court, 4–10 phrases)
- "citations": une liste de 3–6 objets {{"url": <lien>, "title": <titre si connu>}}
Si l'information manque, indique-le et propose des pistes.
---
Question: {q}
"""
                    )
                data = _parse_rag_json(resp.content or "")
                _render_rag_answer(data)

                md_to_save = (data.get("answer","") + "\n\n" +
                              "\n".join(
                                  f"- [{c.get('title') or c.get('url')}]({c.get('url')})" if c.get("url") else f"- {c.get('title','')}"
                                  for c in (data.get("citations") or [])
                              ))
                st.download_button(
                    "💾 Télécharger la réponse (Markdown)",
                    data=md_to_save.encode("utf-8"),
                    file_name=f"rag_answer_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md",
                    mime="text/markdown",
                )