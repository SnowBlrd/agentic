# pages/03_Agent_Chat.py
from __future__ import annotations
import os, tempfile, pathlib
import streamlit as st
from context_orchestrator_agent import build_agent
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="Agent Contexte — Chat", page_icon="🤖", layout="wide")
st.title("🤖 Agent Contexte (PDF/DOCX/PPTX/Code)")

with st.sidebar:
    st.header("Fichiers à ingérer")
    up_files = st.file_uploader(
        "Dépose un ou plusieurs documents",
        type=["pdf","pptx","docx","txt","md","py","ipynb","js","ts","java","sql","scala","r","cpp","c","go","kt"],
        accept_multiple_files=True
    )
    ingest_clicked = st.button("📥 Ingestion via agent")

# Historique chat
if "chat" not in st.session_state:
    st.session_state.chat = []

agent = build_agent()

# Ingestion via tool (on pilote explicitement l'agent)
if up_files and ingest_clicked:
    with st.spinner("Ingestion en cours..."):
        for f in up_files:
            suffix = pathlib.Path(f.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(f.read())
                tmp_path = tmp.name
            # On pousse explicitement le tool call
            prompt = f"Ingère ce fichier: {tmp_path}\nUtilise le tool ingest_file(path='{tmp_path}')."
            rr = agent.run(prompt)
            st.success(f"✅ {f.name} — {getattr(rr, 'content', rr)}")

# Afficher l'historique
for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Entrée utilisateur
msg = st.chat_input("Parle à l’agent… (ex: 'liste le contexte', 'recherche churn', 'supprime ID')")
if msg:
    st.session_state.chat.append({"role": "user", "content": msg})
    with st.chat_message("user"):
        st.markdown(msg)

    # Laisse l’agent décider d’appeler les tools (list/search/delete)
    rr = agent.run(msg)
    content = getattr(rr, "content", rr)

    with st.chat_message("assistant"):
        st.markdown(str(content))

    st.session_state.chat.append({"role": "assistant", "content": str(content)})