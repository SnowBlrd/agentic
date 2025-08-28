from pathlib import Path
from typing import Optional, List, Dict
import csv

def read_linkedin_csv(csv_path: Optional[str]) -> List[Dict[str, str]]:
    items = []
    if not csv_path:
        return items
    p = Path(csv_path)
    if not p.exists():
        return items
    with p.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append({k: (v or "").strip() for k, v in row.items()})
    return items
