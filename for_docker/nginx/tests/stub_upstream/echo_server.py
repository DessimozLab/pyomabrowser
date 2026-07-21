import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class EchoHandler(BaseHTTPRequestHandler):
    """Stands in for the Django "web" backend: reports exactly what request it received."""

    def _respond(self):
        body = json.dumps({
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers.items()),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-From-Stub", "1")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._respond()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("X-From-Stub", "1")
        self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), EchoHandler).serve_forever()