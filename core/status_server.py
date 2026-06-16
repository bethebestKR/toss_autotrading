import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

_status: dict = {}
_lock = threading.Lock()


def update(data: dict):
    with _lock:
        _status.clear()
        _status.update(data)


def _default(obj):
    if hasattr(obj, 'item'):  # numpy scalar
        return obj.item()
    raise TypeError(f"{type(obj)} is not JSON serializable")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip('/') == '/status':
            with _lock:
                body = json.dumps(_status, ensure_ascii=False, default=_default).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def start(port: int = 8765) -> HTTPServer:
    server = HTTPServer(('localhost', port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[dashboard] http://localhost:{port}/status 서빙 중 — dashboard.html 열기")
    return server
