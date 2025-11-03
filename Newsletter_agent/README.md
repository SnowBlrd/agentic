# agno-rag-newsletter

Architecture modulaire pour un système multi‑agents (Agno + OpenAI) qui :
- collecte des sources (arXiv, RSS, URLs, CSV LinkedIn),
- matérialise le HTML en Markdown propre, indexe dans Qdrant/LanceDB,
- génère une newsletter structurée avec image d'en‑tête,
- expose un mode RAG (Q&A sur la base).

## Installation
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
cp .env.example .env  # puis renseigner OPENAI_API_KEY
```

## Lancer l'UI
```bash
streamlit run app.py
```

## Script CLI (newsletter)
```bash
python -m src.pipeline.run_newsletter --sources sources.yaml
```

---