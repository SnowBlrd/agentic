import os
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from src.config import ROOT

_LOCAL_HTTPD = None
_LOCAL_HTTP_BASE = None

class _RootedHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def start_local_http(root_dir: Path = ROOT, port: int | None = None) -> str:
    global _LOCAL_HTTPD, _LOCAL_HTTP_BASE
    if _LOCAL_HTTPD is not None:
        return _LOCAL_HTTP_BASE
    port = port or int(os.getenv("LOCAL_HTTP_PORT", "8765"))
    handler = lambda *args, **kwargs: _RootedHandler(*args, directory=str(root_dir), **kwargs)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    _LOCAL_HTTPD = httpd
    _LOCAL_HTTP_BASE = f"http://127.0.0.1:{port}"
    print(f"[HTTP] Serving {root_dir} at {_LOCAL_HTTP_BASE}")
    return _LOCAL_HTTP_BASE

def path_to_http_url(path: Path) -> str:
    base = start_local_http(ROOT)
    rel = path.resolve().relative_to(ROOT.resolve())
    return f"{base}/{str(rel).replace(os.sep, '/')}"
