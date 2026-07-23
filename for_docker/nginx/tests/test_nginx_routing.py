"""
Integration tests for the nginx download-routing config (nginx.conf.template).

These bugs live entirely in nginx directive semantics (alias/try_files/rewrite/
proxy_pass interactions) that are invisible to any Django-level test, so this
spins up the real nginx image (built from ../Dockerfile, same as production)
plus a tiny stub "web" backend that just echoes back the request it received.

Requires Docker + the Compose plugin. Run with:
    python3 -m unittest for_docker.nginx.tests.test_nginx_routing -v
or:
    pytest for_docker/nginx/tests/test_nginx_routing.py
"""
import json
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = TEST_DIR / "docker-compose.test.yml"
COMPOSE_CMD = ["docker", "compose", "-f", str(COMPOSE_FILE)]

FIXTURE_GENOMES_JSON = (TEST_DIR / "fixtures" / "downloads" / "genomes.json").read_bytes()


def _fetch(url):
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(), dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())


class NginxDownloadRoutingTest(unittest.TestCase):
    """
    Covers the two bugs fixed in nginx.conf.template's download locations:
      1. alias+try_files silently always falling through to the backend even
         when the requested file exists on disk under /All/.
      2. the backend receiving a mangled request path (missing the /All/
         prefix) once try_files was made to work, because proxy_pass without
         an explicit URI picks up the internally-rewritten $uri instead of
         the original request path.
    """

    @classmethod
    def setUpClass(cls):
        subprocess.run(COMPOSE_CMD + ["up", "-d", "--build"], check=True, cwd=TEST_DIR)
        cls.base_url = f"http://127.0.0.1:{cls._published_port()}"
        cls._wait_until_ready()

    @classmethod
    def tearDownClass(cls):
        subprocess.run(COMPOSE_CMD + ["down", "-v", "--remove-orphans"], check=True, cwd=TEST_DIR)

    @classmethod
    def _published_port(cls):
        out = subprocess.run(
            COMPOSE_CMD + ["port", "nginx", "80"],
            check=True, cwd=TEST_DIR, capture_output=True, text=True,
        ).stdout.strip()
        return out.rsplit(":", 1)[-1]

    @classmethod
    def _wait_until_ready(cls, timeout=30):
        # Poll a path that round-trips through the stub "web" upstream (not just
        # the locally-served file), so we don't proceed before that container's
        # slower cold start (interpreter boot) has actually bound its port.
        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                status, _, headers = _fetch(cls.base_url + "/All/__readiness_probe__")
                if status == 200 and headers.get("X-From-Stub") == "1":
                    return
                last_error = f"status={status} headers={headers}"
            except (urllib.error.URLError, ConnectionError) as exc:
                last_error = exc
            time.sleep(0.5)
        raise RuntimeError(f"nginx/stub never became reachable: {last_error}")

    def test_existing_local_file_is_served_directly_by_nginx(self):
        status, body, headers = _fetch(self.base_url + "/All/genomes.json")
        self.assertEqual(status, 200)
        self.assertEqual(body, FIXTURE_GENOMES_JSON)
        self.assertNotIn("X-From-Stub", headers)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "*")

    def test_missing_local_file_falls_back_to_backend_with_untouched_path(self):
        status, body, headers = _fetch(self.base_url + "/All/does-not-exist.txt")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-From-Stub"), "1")
        payload = json.loads(body)
        self.assertEqual(payload["path"], "/All/does-not-exist.txt")

    def test_versioned_release_path_always_goes_straight_to_backend(self):
        # genomes.json exists in the fixture dir, but versioned release paths
        # are never served locally in the container, so this must still reach
        # the backend, unmodified, rather than being served from disk.
        status, body, headers = _fetch(self.base_url + "/All.Mar2026/genomes.json")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-From-Stub"), "1")
        payload = json.loads(body)
        self.assertEqual(payload["path"], "/All.Mar2026/genomes.json")


if __name__ == "__main__":
    unittest.main()