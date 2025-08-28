from __future__ import annotations
import json, hashlib, time, re
from typing import List, Dict, Any, Optional
from pathlib import Path

def _slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\-\.]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")[:80] or "item"

def _digest(item: Dict[str, Any]) -> str:
    basis = (
        f"{item.get('file','')}\n"
        f"{item.get('title','')}\n"
        f"{item.get('summary','')}\n"
        + "\n".join(item.get("key_points", []))
    )
    return hashlib.sha1(basis.encode("utf-8", errors="ignore")).hexdigest()[:12]

class LocalStore:
    """
    Store ultra-simple basé sur des fichiers JSON individuels dans un dossier local.
    - Chaque résumé = 1 fichier .json
    - Déduplication par hash de contenu (sha1 sur champs clés)
    - Fonctions: list, upsert, delete, clear, export/import JSONL
    """
    def __init__(self, root: str | Path = ".context_store"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, item: Dict[str, Any]) -> Path:
        did = _digest(item)
        slug = _slugify(item.get("file") or item.get("title") or "doc")
        ts = int(time.time())
        return self.root / f"{ts}_{slug}_{did}.json"

    def list(self) -> List[Dict[str, Any]]:
        items = []
        for p in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                data["_path"] = str(p)
                items.append(data)
            except Exception:
                # skip fichiers corrompus
                pass
        return items

    def upsert(self, item: Dict[str, Any]) -> Dict[str, Any]:
        # Dédup: si un item existant a le même digest, on ne recrée pas
        did = _digest(item)
        for p in self.root.glob("*.json"):
            try:
                cur = json.loads(p.read_text(encoding="utf-8"))
                if _digest(cur) == did:
                    cur["_path"] = str(p)
                    return cur
            except Exception:
                pass
        path = self._path_for(item)
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        item["_path"] = str(path)
        return item

    def delete(self, path_or_name: str) -> bool:
        p = Path(path_or_name)
        if not p.is_absolute():
            p = self.root / path_or_name
        if p.exists() and p.suffix == ".json":
            p.unlink(missing_ok=True)
            return True
        return False

    def clear(self) -> int:
        n = 0
        for p in self.root.glob("*.json"):
            try:
                p.unlink(missing_ok=True)
                n += 1
            except Exception:
                pass
        return n

    def export_jsonl(self, out_path: str | Path) -> Path:
        out = Path(out_path)
        items = self.list()
        out.write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in items),
            encoding="utf-8"
        )
        return out

    def import_jsonl(self, in_path: str | Path) -> int:
        p = Path(in_path)
        if not p.exists():
            return 0
        count = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                self.upsert(obj)
                count += 1
            except Exception:
                pass
        return count
