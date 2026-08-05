import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# The one credential this stub treats as a valid, logged-in Keycloak session/token.
# Anything else (including no Authorization header at all) is "not authenticated".
VALID_BEARER = "Bearer good-token"


class EchoHandler(BaseHTTPRequestHandler):
    """Stands in for oauth2-proxy. For /oauth2/auth (what nginx's auth_request
    hits) it validates the Authorization header against VALID_BEARER, mirroring
    the real /oauth2/auth 200-or-401 contract nginx.conf.template relies on for
    tiering /api/ requests into authenticated vs anonymous. Everything else
    (e.g. the device-flow endpoints) just echoes the request back."""

    def _respond(self, status=200):
        body = json.dumps({
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers.items()),
        }).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-From-Oauth2-Stub", "1")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self):
        if self.headers.get("Authorization") == VALID_BEARER:
            self.send_response(200)
            self.send_header("X-Auth-Request-User", "testuser")
            self.send_header("X-Auth-Request-Email", "testuser@example.com")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_GET(self):
        if self.path.startswith("/oauth2/auth"):
            self._auth()
        else:
            self._respond()

    def do_POST(self):
        self._respond()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("X-From-Oauth2-Stub", "1")
        self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 4180), EchoHandler).serve_forever()
