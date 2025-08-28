# pages/02_Contexte_Documents.py
from __future__ import annotations
import os, tempfile, pathlib, json, time
from typing import List, Dict, Any
from dotenv import load_dotenv
import streamlit as st
from context_agent import ContextAgent, MAX_CHARS_DEFAULT
from local_store import LocalStore

load_dotenv()

# -----------------------------------------
# CONFIG
# -----------------------------------------
st.set_page_config(
    page_title="Contexte documents — Enrichissement (PDF/DOCX/PPTX/Code)",
    page_icon="🧩",
    layout="wide"
)
st.title("🧩 Enrichissement du contexte par documents")

st.write("""
Dépose des **PDF**, **PPTX**, **DOCX** ou des **fichiers de code/texte**.
L’agent *ContextBuilder* extrait le texte puis génère un **résumé structuré (JSON)** adapté aux réunions data.
Tous les résumés sont **stockés en local** (fichiers `.json`) et disponibles pour ta page de **compte rendu**.
""")

# -----------------------------------------
# SIDEBAR
# -----------------------------------------
with st.sidebar:
    st.header("Paramètres")
    model = st.text_input("Modèle (OPENAI)", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    store_dir = st.text_input("Dossier local de stockage", ".context_store")
    max_chars = st.number_input("Taille max (caractères) par document", min_value=2000, max_value=200_000, step=1000, value=MAX_CHARS_DEFAULT)
    auto_add = st.checkbox("Ajouter au contexte de session après résumé", value=True)
    st.caption("La session permet de réutiliser directement les résumés dans ta page de compte rendu.")

# -----------------------------------------
# INIT SESSION & STORE
# -----------------------------------------
if "context_summaries" not in st.session_state:
    st.session_state["context_summaries"] = []

store = LocalStore(store_dir)

# Charger du disque si la session est vide
if not st.session_state["context_summaries"]:
    st.session_state["context_summaries"] = store.list()

# -----------------------------------------
# UPLOAD
# -----------------------------------------
uploaded_files = st.file_uploader(
    "Dépose un ou plusieurs documents",
    type=[
        "pdf", "pptx", "docx", "txt", "md", "py", "ipynb", "js", "ts",
        "java", "sql", "scala", "r", "cpp", "c", "go", "kt"
    ],
    accept_multiple_files=True
)

# -----------------------------------------
# ACTIONS
# -----------------------------------------
colA, colB, colC, colD, colE = st.columns([1,1,1,1,1])
with colA:
    run_all = st.button("▶️ Résumer tous les fichiers")
with colB:
    clear_session = st.button("🧹 Vider contexte (session)")
with colC:
    clear_disk = st.button("🗑️ Vider stockage local")
with colD:
    export_btn = st.button("💾 Exporter (JSONL)")
with colE:
    import_file = st.file_uploader("Importer JSONL", type=["jsonl"], accept_multiple_files=False, key="import_jsonl")

# -----------------------------------------
# HANDLERS
# -----------------------------------------
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

# -----------------------------------------
# RÉSUMÉ DES FICHIERS UPLOADÉS
# -----------------------------------------
def summarize_and_store(files) -> List[Dict[str, Any]]:
    agent = ContextAgent(model_id=model)
    results: List[Dict[str, Any]] = []
    progress = st.progress(0)
    total = len(files)

    for i, f in enumerate(files, start=1):
        suffix = pathlib.Path(f.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(f.read())
            tmp_path = tmp.name
        try:
            data = agent.summarize_file(tmp_path, max_chars=max_chars)
            # Alerte PDF sans texte
            if data.get("doc_type") == "pdf" and not data.get("summary") and not data.get("key_points"):
                st.warning(f"⚠️ {f.name} semble être un PDF scanné sans texte (OCR recommandé).")

            saved = store.upsert(data)        # Sauvegarde locale
            results.append(saved)

            if auto_add:
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

# -----------------------------------------
# LISTE CUMULÉE + ACTIONS PAR ÉLÉMENT
# -----------------------------------------
st.subheader("🧠 Contexte (session)")
if not st.session_state["context_summaries"]:
    st.info("Aucun résumé en mémoire pour le moment.")
else:
    # Recharge la carte disque pour garder les *paths* à jour
    disk_map = {item.get("_path"): item for item in store.list()}
    new_session = []
    for item in st.session_state["context_summaries"]:
        it = disk_map.get(item.get("_path")) or item
        title = it.get("title") or it.get("file") or "document"
        with st.expander(f"{title}"):
            st.json(it)
            c1, c2, c3 = st.columns([1, 2, 3])
            with c1:
                if st.button("🗑️ Supprimer du disque", key=f"del_{it.get('_path','')}_{hash(title)}"):
                    ok = it.get("_path") and store.delete(it["_path"])
                    if ok:
                        st.success("Supprimé du disque.")
                        continue  # ne pas réinsérer dans la session
            with c2:
                st.caption(it.get("_path") or "(non persisté)")
            with c3:
                # Mini aperçu utile pour injecter rapidement dans prompt
                snippet = (it.get("summary") or "")[:180].replace("\n", " ")
                st.caption(f"Résumé court: {snippet}…")
        new_session.append(it)
    st.session_state["context_summaries"] = new_session

st.markdown("---")
st.markdown(f"**Dossier local :** `{store_dir}`")

# -----------------------------------------
# PROMPT CONDENSÉ POUR TA PAGE DE CR
# -----------------------------------------
st.markdown("#### Prompt condensé à injecter dans le compte rendu")
bullets = []
for it in st.session_state["context_summaries"]:
    bullets.append(f"- **{it.get('file','?')}** — {it.get('summary','')}")
st.code("Contexte documents:\n" + "\n".join(bullets))
