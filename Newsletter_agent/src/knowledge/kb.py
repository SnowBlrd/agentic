from pathlib import Path
import yaml
from agno.knowledge.url import UrlKnowledge
from src.knowledge.vector_db import get_vector_db


def build_knowledge_bases(sources_yaml: Path):
    cfg = yaml.safe_load(Path(sources_yaml).read_text(encoding="utf-8")) or {}
    vector_db = get_vector_db()
    url_kb = UrlKnowledge(urls=[], vector_db=vector_db)
    return cfg, vector_db, url_kb