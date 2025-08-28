# app.py
from __future__ import annotations
import os
import io
import json
import time
import pathlib
import textwrap
import streamlit as st

from local_store import LocalStore

# ------------------------------------------------------------
# Configuration & helpers
# ------------------------------------------------------------
st.set_page_config(
    page_title="Assistant de réunions IA",
    page_icon="📝",
    layout="wide"
)

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_STORE_DIR = os.getenv("CONTEXT_STORE_DIR", ".context_store")

def load_context_text(store_dir: str, include_session: bool = True, max_chars: int = 8000) -> str:
    """Concatène des synthèses de documents pour les injecter comme contexte."""
    store = LocalStore(store_dir)
    items = store.list()

    # Contexte issu d'autres pages (ex: 02_Context_Agent.py)
    session_items = []
    if include_session and "context_summaries" in st.session_state:
        session_items = st.session_state["context_summaries"] or []

    # éviter doublons grossiers (par _path si dispo)
    seen = set()
    merged = []
    for coll in (session_items, items):
        for it in coll:
            key = it.get("_path") or f"{it.get('file')}::{it.get('title')}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(it)

    # Construire un texte compact
    lines = []
    for it in merged:
        file_ = it.get("file", "?")
        summ = it.get("summary", "").strip()
        if summ:
            lines.append(f"[{file_}] {summ}")
        # Points clés synthétiques
        kps = it.get("key_points") or []
        if kps:
            take = "; ".join(kps[:5])
            if take:
                lines.append(f"Points clés: {take}")
    ctx = "\n".join(lines).strip()
    return ctx[:max_chars]

def llm_meeting_summary(transcript: str, context_text: str, model_id: str, temperature: float = 0.2) -> dict:
    """
    Appel LLM via openai pour produire un CR structuré en français.
    Si OPENAI_API_KEY absent ou erreur, on renvoie un fallback simple.
    """
    transcript = (transcript or "").strip()
    if not transcript:
        return {"error": "Aucun transcript fourni."}

    system = textwrap.dedent(f"""
    Tu es un assistant qui rédige des comptes rendus de réunion professionnels pour des équipes data.
    Utilise le CONTEXTE ci-dessous pour orienter l'analyse. Réponds en JSON STRICT avec ce schéma :

    {{
      "meeting_title": "string",
      "date": "YYYY-MM-DD",
      "attendees": ["..."],
      "summary": "string",
      "decisions": ["..."],
      "actions": [{{"owner":"string","task":"string","due":"YYYY-MM-DD|null"}}],
      "risks_or_blockers": ["..."],
      "next_steps": ["..."]
    }}

    CONTEXTE (documents résumés):
    {context_text}
    """).strip()

    user = textwrap.dedent(f"""
    TRANSCRIPT DE LA RÉUNION (texte brut):
    {transcript}
    """).strip()

    api_key = os.getenv("OPENAI_API_KEY")
    try:
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY manquante")

        # Appel OpenAI (chat.completions)
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model_id,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        txt = resp.choices[0].message.content.strip()
        data = json.loads(txt)
        return data
    except Exception as e:
        # Fallback extractif minimal si LLM indisponible
        # On tente d'extraire quelques phrases "décisions" & "actions" par heuristiques simples.
        lines = [l.strip() for l in transcript.splitlines() if l.strip()]
        head = " ".join(lines[:6])[:800]
        actions = [l for l in lines if l.lower().startswith(("- [ ]", "- [x]", "todo:", "action:", "à faire", "action -"))][:5]
        decisions = [l for l in lines if any(k in l.lower() for k in ["décidé", "décision", "valider", "tranché"])]
        return {
            "meeting_title": "Compte rendu (fallback)",
            "date": time.strftime("%Y-%m-%d"),
            "attendees": [],
            "summary": head if head else "Résumé non disponible (LLM indisponible).",
            "decisions": decisions[:5],
            "actions": [{"owner": "", "task": a, "due": None} for a in actions[:5]],
            "risks_or_blockers": [],
            "next_steps": [],
            "_warning": f"Résumé généré sans LLM ({e}). Fournis OPENAI_API_KEY ou utilise ta pipeline existante."
        }

def download_json_button(data: dict, label: str = "Télécharger (JSON)", filename: str = "meeting_summary.json"):
    st.download_button(
        label=label,
        data=json.dumps(data, ensure_ascii=False, indent=2),
        file_name=filename,
        mime="application/json"
    )

# ------------------------------------------------------------
# Sidebar (paramètres globaux)
# ------------------------------------------------------------
with st.sidebar:
    st.header("Paramètres")
    model = st.text_input("Modèle LLM", DEFAULT_MODEL)
    temperature = st.slider("Température", 0.0, 1.0, 0.2, 0.05)
    store_dir = st.text_input("Dossier du contexte local", DEFAULT_STORE_DIR)
    include_session = st.checkbox("Inclure le contexte en session", value=True)
    st.caption("Le contexte combine le stockage local et (optionnellement) la session en cours.")

    st.markdown("---")
    st.markdown("**Navigation**")
    st.markdown("- Page **Contexte documents** : dans le menu *Pages* (à gauche).")

# ------------------------------------------------------------
# Body
# ------------------------------------------------------------
st.title("📝 Assistant de réunions IA — Accueil")

tab_cr, tab_ctx = st.tabs(["Compte rendu de réunion", "Contexte global"])

# ---------------------------
# Onglet 1 : Compte rendu
# ---------------------------
with tab_cr:
    st.subheader("1) Transcript de la réunion")
    st.write("Colle ci-dessous le **transcript texte** (ou importe un `.txt`).")

    # Import .txt facultatif
    upl_txt = st.file_uploader("Importer un fichier texte", type=["txt"], accept_multiple_files=False, key="upl_txt_transcript")
    transcript_default = ""
    if upl_txt is not None:
        try:
            transcript_default = upl_txt.read().decode("utf-8", errors="ignore")
        except Exception:
            transcript_default = upl_txt.read().decode(errors="ignore")

    transcript = st.text_area(
        "Transcript (texte brut)",
        value=transcript_default,
        height=300,
        placeholder="Colle ici la transcription de la réunion…"
    )

    st.subheader("2) Contexte injecté (documents résumés)")
    ctx_text = load_context_text(store_dir, include_session=include_session, max_chars=8000)
    if ctx_text:
        with st.expander("Voir le contexte injecté", expanded=False):
            st.code(ctx_text)
    else:
        st.info("Aucun contexte trouvé. Ajoute des documents via la page **Contexte documents** (menu à gauche).")

    st.subheader("3) Générer le compte rendu")
    col1, col2, col3 = st.columns([1,1,2])
    with col1:
        run_btn = st.button("▶️ Résumer la réunion")
    with col2:
        clear_btn = st.button("🧹 Effacer le transcript")

    if clear_btn:
        st.session_state.pop("upl_txt_transcript", None)
        st.experimental_rerun()

    if run_btn:
        with st.spinner("Génération du compte rendu…"):
            result = llm_meeting_summary(transcript, ctx_text, model_id=model, temperature=temperature)
        if "error" in result:
            st.error(result["error"])
        else:
            st.success("Compte rendu généré.")
            with st.expander("🧾 Résultat (JSON)", expanded=False):
                st.json(result)

            # Rendu lisible (Markdown)
            st.markdown("### Compte rendu (lecture humaine)")
            title = result.get("meeting_title") or "Compte rendu"
            date = result.get("date") or ""
            attendees = ", ".join(result.get("attendees", []))
            st.markdown(f"**{title}**  \n{date}  \nParticipants : {attendees if attendees else '—'}")

            st.markdown("#### Synthèse")
            st.write(result.get("summary", "—"))

            def _list(items, title):
                st.markdown(f"#### {title}")
                if not items:
                    st.write("—")
                else:
                    for x in items:
                        st.markdown(f"- {x}")

            _list(result.get("decisions", []), "Décisions")
            _list(result.get("risks_or_blockers", []), "Risques / Blocages")
            _list(result.get("next_steps", []), "Prochaines étapes")

            st.markdown("#### Actions")
            actions = result.get("actions", [])
            if not actions:
                st.write("—")
            else:
                for a in actions:
                    owner = a.get("owner") or "—"
                    task = a.get("task") or "—"
                    due = a.get("due") or "—"
                    st.markdown(f"- **{owner}** : {task} *(échéance : {due})*")

            # Téléchargement
            cols = st.columns([1,1,2])
            with cols[0]:
                download_json_button(result, label="💾 Télécharger (JSON)", filename=f"meeting_{int(time.time())}.json")
            with cols[1]:
                # Export Markdown rapide
                md = textwrap.dedent(f"""
                # {title}
                **Date :** {date}  
                **Participants :** {attendees or "—"}

                ## Synthèse
                {result.get("summary","—")}

                ## Décisions
                {os.linesep.join(f"- {x}" for x in result.get("decisions", []) or ["—"])}

                ## Actions
                {os.linesep.join(f"- {a.get('owner','—')}: {a.get('task','—')} (échéance: {a.get('due','—')})" for a in actions) if actions else "- —"}

                ## Risques / Blocages
                {os.linesep.join(f"- {x}" for x in result.get("risks_or_blockers", []) or ["—"])}

                ## Prochaines étapes
                {os.linesep.join(f"- {x}" for x in result.get("next_steps", []) or ["—"])}
                """).strip()
                st.download_button("📝 Télécharger (Markdown)", md, file_name=f"meeting_{int(time.time())}.md", mime="text/markdown")

            if "_warning" in result:
                st.warning(result["_warning"])

# ---------------------------
# Onglet 2 : Contexte global
# ---------------------------
with tab_ctx:
    st.subheader("Contexte stocké en local")
    store = LocalStore(store_dir)
    items = store.list()

    c1, c2 = st.columns([1,1])
    with c1:
        if st.button("🔄 Rafraîchir"):
            items = store.list()
    with c2:
        if st.button("🗑️ Vider le stockage local"):
            n = store.clear()
            st.success(f"{n} éléments supprimés.")
            items = []

    if not items:
        st.info("Aucun document résumé en local pour le moment. Ajoute des PDF/DOCX/PPTX/code depuis la page **Contexte documents**.")
    else:
        st.caption(f"{len(items)} élément(s) dans `{store_dir}`")
        for it in items:
            title = it.get("title") or it.get("file") or "document"
            with st.expander(title, expanded=False):
                st.json(it)
                path = it.get("_path")
                cols = st.columns([1,3])
                with cols[0]:
                    if st.button("🗑️ Supprimer", key=f"del_{path}"):
                        if path and store.delete(path):
                            st.success("Supprimé.")
                        else:
                            st.error("Suppression impossible.")
                with cols[1]:
                    st.caption(path or "(non persisté)")

    st.markdown("---")
    st.markdown("#### Prompt condensé (à copier)")
    ctx_text_all = load_context_text(store_dir, include_session=True, max_chars=8000)
    st.code("Contexte documents:\n" + (ctx_text_all if ctx_text_all else "(vide)"))

st.markdown("---")
st.caption("Astuce : pour ajouter du contexte, ouvre la page **Contexte documents** (menu à gauche) et dépose tes PDF/DOCX/PPTX/fichiers de code.")
