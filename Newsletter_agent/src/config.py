import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = Path(os.getenv("NEWSLETTER_OUT_DIR", "output"))
OUT_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_LANG = os.getenv("DEFAULT_LANGUAGE", "fr")