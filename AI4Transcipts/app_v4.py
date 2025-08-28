# app.py
from __future__ import annotations
import os, tempfile, pathlib, json, time
from typing import List, Dict, Any

import streamlit as st

# --- Tes modules métier ---
from context_agent import ContextAgent, MAX_CHARS_DEFAULT
from local_store import LocalStore

# --- Imports Agno pour l'agent Chat (outils intégrés ici) ---
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools import tool

from dotenv import load_dotenv

load_dotenv()


# ============================================================================
# CONFIG GÉNÉRALE
# ============================================================================
st.set_page_config(page_title="Contexte & Agent (PDF/DOCX/PPTX/Code)", page_icon="🧩", layout="wide")
st.title("🧩 Contexte documents + 🤖 Agent IA — App unifiée")

with st.sidebar:
    st.header("Paramètres globaux")
    MODEL_ID = st.text_input("Modèle (OPENAI)", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    STORE_DIR = st.text_input("Dossier local de stockage", ".context_store")

store = LocalStore(STORE_DIR)

# État de session
st.session_state.setdefault("context_summaries", store.list())
st.session_state.setdefault("chat", [])

# ============================================================================
# ONGLET 1 — ENRICHISSEMENT CONTEXTE
# ============================================================================
tab_enrich, tab_chat = st.tabs(["📥 Enrichir le contexte", "🤖 Agent Chat"])

with tab_enrich:
    st.subheader("📥 Upload & Résumé (stockage local)")
    st.write("Dépose des **PDF**, **PPTX**, **DOCX** ou des **fichiers de code/texte**. L’agent génère un **JSON structuré**.")

    max_chars = st.number_input("Taille max par doc (caractères)", min_value=2000, max_value=200_000,
                                step=1000, value=MAX_CHARS_DEFAULT)
    uploaded_files = st.file_uploader(
        "Dépose un ou plusieurs documents",
        type=["pdf","pptx","docx","txt","md","py","ipynb","js","ts","java","sql","scala","r","cpp","c","go","kt"],
        accept_multiple_files=True
    )

    colA, colB, colC, colD, colE = st.columns([1,1,1,1,1])
    with colA:
        run_all = st.button("▶️ Résumer")
    with colB:
        clear_session = st.button("🧹 Vider session")
    with colC:
        clear_disk = st.button("🗑️ Vider stockage local")
    with colD:
        export_btn = st.button("💾 Exporter (JSONL)")
    with colE:
        import_file = st.file_uploader("Importer JSONL", type=["jsonl"], accept_multiple_files=False, key="import_jsonl_enrich")

    if clear_session:
        st.session_state["context_summaries"].clear()
        st.success("Contexte de session vidé.")

    if clear_disk:
        n = store.clear()
        st.success(f"Stockage local vidé ({n} fichiers supprimés).")
        st.session_state["context_summaries"].clear()

    if export_btn:
        ts = int(time.time())
        fname = f"context_{ts}.jsonl"
        jsonl = "\n".join(json.dumps(x, ensure_ascii=False) for x in store.list())
        st.download_button("Télécharger le JSONL", data=jsonl, file_name=fname, mime="application/json")

    if import_file is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl") as tmp:
            tmp.write(import_file.read())
            tmp_path = tmp.name
        count = store.import_jsonl(tmp_path)
        st.success(f"{count} éléments importés.")
        st.session_state["context_summaries"] = store.list()

    def summarize_and_store(files) -> List[Dict[str, Any]]:
        agent = ContextAgent(model_id=MODEL_ID)
        results: List[Dict[str, Any]] = []
        progress = st.progress(0)
        total = len(files) or 1

        for i, f in enumerate(files, start=1):
            suffix = pathlib.Path(f.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(f.read())
                tmp_path = tmp.name
            try:
                data = agent.summarize_file(tmp_path, max_chars=max_chars)
                if data.get("doc_type") == "pdf" and not data.get("summary") and not data.get("key_points"):
                    st.warning(f"⚠️ {f.name} semble être un PDF scanné sans texte (OCR recommandé).")
                saved = store.upsert(data)
                results.append(saved)
                st.session_state["context_summaries"].append(saved)
                with st.expander(f"✅ {f.name}", expanded=False):
                    st.json(saved)
            except Exception as e:
                with st.expander(f"❌ {f.name} — Erreur", expanded=True):
                    st.error(str(e))
            finally:
                progress.progress(i / total)
        return results

    if uploaded_files and run_all:
        with st.spinner("L’agent résume les documents…"):
            _ = summarize_and_store(uploaded_files)

    # Liste cumulée + actions
    st.markdown("### 🧠 Contexte (session)")
    if not st.session_state["context_summaries"]:
        st.info("Aucun résumé en mémoire.")
    else:
        # Rafraîchir depuis disque
        disk_map = {item.get("_path"): item for item in store.list()}
        new_session = []
        for it in st.session_state["context_summaries"]:
            it = disk_map.get(it.get("_path")) or it
            title = it.get("title") or it.get("file") or "document"
            with st.expander(title):
                st.json(it)
                c1, c2, c3 = st.columns([1,2,3])
                with c1:
                    if st.button("🗑️ Supprimer du disque", key=f"del_{it.get('_path','')}_{hash(title)}"):
                        ok = it.get("_path") and store.delete(it["_path"])
                        if ok:
                            st.success("Supprimé du disque.")
                            continue
                with c2:
                    st.caption(it.get("_path") or "(non persisté)")
                with c3:
                    snippet = (it.get("summary") or "")[:180].replace("\n", " ")
                    st.caption(f"Résumé court: {snippet}…")
            new_session.append(it)
        st.session_state["context_summaries"] = new_session

    st.markdown("---")
    st.markdown(f"**Dossier local :** `{STORE_DIR}`")

    st.markdown("#### Prompt condensé pour ton compte rendu")
    bullets = [f"- **{it.get('file','?')}** — {it.get('summary','')}" for it in st.session_state["context_summaries"]]
    st.code("Contexte documents:\n" + "\n".join(bullets))

# ============================================================================
# ONGLET 2 — AGENT CHAT (ingérer / lister / rechercher / supprimer)
# ============================================================================
with tab_chat:
    st.subheader("🤖 Agent Contexte — Chat")

    # Tools de l'agent, branchés sur le même store + le même summarizer
    summarizer = ContextAgent(model_id=MODEL_ID)

    @tool(name="ingest_file", description="Résumé + stockage local d’un document (pdf/docx/pptx/code).")
    def ingest_file(path: str, max_chars: int = MAX_CHARS_DEFAULT) -> Dict[str, Any]:
        data = summarizer.summarize_file(path, max_chars=max_chars)
        saved = store.upsert(data)
        return {"ok": True, "id": saved.get("_path"), "file": saved.get("file"), "title": saved.get("title"), "size": saved.get("size")}

    @tool(name="list_context", description="Lister les résumés présents en local.")
    def list_context() -> List[Dict[str, Any]]:
        items = store.list()
        return [{"id": it.get("_path"), "file": it.get("file"), "title": it.get("title"), "size": it.get("size")} for it in items]

    @tool(name="search_context", description="Recherche mot-clé dans summary/key_points.")
    def search_context(query: str) -> List[Dict[str, Any]]:
        q = (query or "").lower()
        out = []
        for it in store.list():
            blob = (it.get("summary", "") + " " + " ".join(it.get("key_points", []))).lower()
            if q and q in blob:
                out.append({"id": it.get("_path"), "file": it.get("file"), "title": it.get("title")})
        return out

    @tool(name="delete_context_item", description="Supprime un résumé via son id (chemin du fichier JSON).")
    def delete_context_item(item_id: str) -> Dict[str, Any]:
        ok = store.delete(item_id)
        return {"ok": ok, "id": item_id}

    SYSTEM_PROMPT = """
    Tu es **AgentContexte**, assistant pour réunions data.
    - Utilise les tools pour INGÉRER (ingest_file), LISTER (list_context),
      CHERCHER (search_context) et SUPPRIMER (delete_context_item).
    - Si un utilisateur donne un chemin de fichier, ingère-le (ingest_file).
    - Réponds de façon concise et opérationnelle.
    """

    agent_chat = Agent(
        model=OpenAIChat(id=MODEL_ID, api_key=os.getenv("OPENAI_API_KEY")),
        instructions=SYSTEM_PROMPT,
        tools=[ingest_file, list_context, search_context, delete_context_item],
        markdown=True,
    )

    # Zone d'upload pour ingestion "pilotée par l'agent"
    with st.sidebar:
        st.markdown("### 📎 Ingestion par l’agent")
        up_files = st.file_uploader(
            "Dépose des documents à ingérer",
            type=["pdf","pptx","docx","txt","md","py","ipynb","js","ts","java","sql","scala","r","cpp","c","go","kt"],
            accept_multiple_files=True,
            key="agent_upload"
        )
        ingest_clicked = st.button("📥 Ingestion (tools)")

    if up_files and ingest_clicked:
        with st.spinner("Ingestion via agent…"):
            for f in up_files:
                suffix = pathlib.Path(f.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(f.read())
                    tmp_path = tmp.name
                prompt = f"Ingère ce fichier: {tmp_path} en appelant ingest_file(path='{tmp_path}')."
                rr = agent_chat.run(prompt)
                st.success(f"✅ {f.name} — {getattr(rr, 'content', rr)}")

    # Affiche l'historique
    for m in st.session_state["chat"]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Saisie utilisateur
    msg = st.chat_input("Parle à l’agent… (ex: 'liste le contexte', 'recherche AUC', 'supprime <id>')")
    if msg:
        st.session_state["chat"].append({"role": "user", "content": msg})
        with st.chat_message("user"):
            st.markdown(msg)

        rr = agent_chat.run(msg)
        content = getattr(rr, "content", rr)

        with st.chat_message("assistant"):
            st.markdown(str(content))

        st.session_state["chat"].append({"role": "assistant", "content": str(content)})
