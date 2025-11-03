import os
import json
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.config import DEFAULT_LANG, OUT_DIR
from src.knowledge.kb import build_knowledge_bases
from src.ingestion.ingest import ingest_sources
from src.agents.collector import collector_agent
from src.agents.curator import curator_agent
from src.agents.writer import writer_agent
from src.agents.team import build_team
from src.agents.rag import rag_agent, kb_search_urls

load_dotenv()

st.set_page_config(page_title="Newsletter IA — Agno", page_icon="📰", layout="wide")

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
)
if openai_key_input:
    os.environ["OPENAI_API_KEY"] = openai_key_input

lang = st.sidebar.selectbox("Langue", ["fr", "en"], index=0)
os.environ["DEFAULT_LANGUAGE"] = lang

st.sidebar.markdown("---")
use_qdrant = st.sidebar.checkbox(
    "Utiliser Qdrant (sinon LanceDB)", value=bool(os.getenv("QDRANT_URL"))
)
if use_qdrant:
    qdrant_url = st.sidebar.text_input("QDRANT_URL", value=os.getenv("QDRANT_URL", "http://localhost:6333"))
    qdrant_key = st.sidebar.text_input("QDRANT_API_KEY (optionnel)", type="password", value=os.getenv("QDRANT_API_KEY", ""))
    os.environ["QDRANT_URL"] = qdrant_url
    if qdrant_key:
        os.environ["QDRANT_API_KEY"] = qdrant_key
else:
    os.environ.pop("QDRANT_URL", None)
    os.environ.pop("QDRANT_API_KEY", None)

st.sidebar.markdown("---")
src_file = st.sidebar.file_uploader("sources.yaml (sinon exemple)", type=["yaml", "yml"], accept_multiple_files=False)
li_csv = st.sidebar.file_uploader("LinkedIn CSV (url,text,author,date)", type=["csv"], accept_multiple_files=False)

# ---------- Body ----------
st.title("📰 Newsletter IA — Multi-agents (Agno + OpenAI)")
st.caption("Collecte → Tri → Rédaction — et RAG sur la base vectorielle.")

# Charger sources.yaml (uploadé ou exemple)
if src_file is not None:
    sources_path = Path(tempfile.gettempdir()) / f"sources_{datetime.now().timestamp()}.yaml"
    sources_path.write_bytes(src_file.read())
    st.success("sources.yaml chargé.")
else:
    default_sources = (Path(__file__).parent / "sources.yaml").read_text(encoding="utf-8")
    sources_path = Path(tempfile.gettempdir()) / "sources_example.yaml"
    sources_path.write_text(default_sources, encoding="utf-8")
    st.info("Aucun sources.yaml uploadé — utilisation de l'exemple.")

# CSV LinkedIn enregistré si fourni
li_csv_path = None
if li_csv is not None:
    li_csv_path = Path(tempfile.gettempdir()) / f"linkedin_{datetime.now().timestamp()}.csv"
    li_csv_path.write_bytes(li_csv.read())

if mode == "Newsletter":
    col1, col2 = st.columns([1, 1])
    with col1:
        ingest_clicked = st.button("📥 Ingestion des sources", type="primary")
    with col2:
        generate_clicked = st.button("🖊️ Générer la newsletter")

    if "last_markdown" not in st.session_state:
        st.session_state.last_markdown = None

    if ingest_clicked:
        import yaml
        raw_cfg = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
        if li_csv_path is not None:
            raw_cfg.setdefault("linkedin", {})["csv_path"] = str(li_csv_path)
            patched = Path(tempfile.gettempdir()) / "sources_patched.yaml"
            patched.write_text(yaml.dump(raw_cfg, allow_unicode=True), encoding="utf-8")
            sources_path = patched
        with st.spinner("Indexation en cours…"):
            cfg, vector_db, url_kb = build_knowledge_bases(sources_path)
            ingest_sources(cfg, url_kb)
        st.success("Ingestion terminée ✅")

    if generate_clicked:
        cfg, vector_db, url_kb = build_knowledge_bases(sources_path)
        collector = collector_agent(url_kb)
        curator = curator_agent(url_kb)
        writer = writer_agent(url_kb, language=os.getenv("DEFAULT_LANGUAGE", DEFAULT_LANG))
        team = build_team(collector, curator, writer)

        today = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""
Objectif: produire une newsletter hebdomadaire sur l'IA (date {today}).

Étapes:
1) Collector: consolide ~30+ items depuis KB (arXiv, RSS, web explicite, LinkedIn CSV).
2) Curator: regroupe par sujets (3–6 clusters) et priorise par qualité.
3) Writer: rédige 900–1400 mots (Titre, Note d'éditeur, Highlights, Sections, Références).
Contraintes: pas d'invention de liens; style clair; sources citées.
"""
        with st.spinner("Génération de la newsletter…"):
            team_run = team.run(prompt)
        md = team_run.content if isinstance(team_run.content, str) else str(team_run.content)

        # ⛔️ Pas d'image d'en-tête (génération/détection désactivée)
        st.session_state.last_markdown = md
        st.success("Newsletter générée ✅")

    if st.session_state.get("last_markdown"):
        st.markdown("## Aperçu de la newsletter")
        st.markdown(st.session_state["last_markdown"])
        filename = f"newsletter_{datetime.now().strftime('%Y-%m-%d')}.md"
        st.download_button(
            "💾 Télécharger le Markdown",
            data=st.session_state["last_markdown"].encode("utf-8"),
            file_name=filename,
            mime="text/markdown"
        )

else:
    st.subheader("🔎 RAG — Interroger la base vectorielle")
    q = st.text_area(
        "Votre question",
        placeholder="Ex: Quelles avancées récentes sur les agents multimodaux ?",
        height=100
    )
    run_q = st.button("Poser la question")

    if run_q:
        cfg, vector_db, url_kb = build_knowledge_bases(sources_path)

        # Toujours afficher les 5 documents les plus pertinents
        hits = kb_search_urls(q, url_kb, k=5)
        st.markdown("### 🔎 Top 5 documents pertinents")
        if hits:
            from bs4 import BeautifulSoup
            for i, h in enumerate(hits, 1):
                url = h.get("url") or "(sans URL)"
                score = h.get("score")
                raw = h.get("text") or ""
                snippet = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
                snippet = snippet[:400] + ("…" if len(snippet) > 400 else "")
                # URL cliquable si http/https, sinon texte brut
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    st.markdown(f"**{i}.** [{url}]({url})")
                else:
                    st.markdown(f"**{i}.** {url}")
                if score is not None:
                    st.caption(f"score: {score:.4f}")
                if snippet:
                    st.write(snippet)
        else:
            st.info("Aucun document proche trouvé (la base peut être vide ou la requête trop spécifique).")

        qa = rag_agent(url_kb, language=os.getenv("DEFAULT_LANGUAGE", DEFAULT_LANG))
        with st.spinner("Recherche & rédaction…"):
            resp = qa.run(
                f"""
Tu es un assistant RAG. Réponds à la question ci-dessous en t'appuyant UNIQUEMENT sur les documents de la base. 
Retourne STRICTEMENT un JSON avec:
- "answer": une réponse en {os.getenv('DEFAULT_LANGUAGE', DEFAULT_LANG)} (markdown court, 4–10 phrases)
- "citations": une liste de 3–6 objets {{"url": <lien>, "title": <titre si connu>}}
Si l'information manque, indique-le et propose des pistes.
---
Question: {q}
"""
            )
        data = _parse_rag_json(resp.content or "")
        _render_rag_answer(data)

        md_to_save = (data.get("answer","") + "\n\n" + "\n".join(
            f"- [{c.get('title') or c.get('url')}]({c.get('url')})" if c.get("url") else f"- {c.get('title','')}"
            for c in (data.get("citations") or [])
        ))
        st.download_button(
            "💾 Télécharger la réponse (Markdown)",
            data=md_to_save.encode("utf-8"),
            file_name=f"rag_answer_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md",
            mime="text/markdown"
        )
