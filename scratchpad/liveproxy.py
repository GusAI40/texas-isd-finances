"""Mirror production on 127.0.0.1 so a browser can actually render it.

Chromium cannot TLS through this sandbox's agent proxy, so Playwright can never
load https://txisd.dev directly. Everything else can: python's urllib goes
through the proxy fine. This sits in between — a plain HTTP server on localhost
that fetches from the live domain and passes the bytes through.

It exists because "the served HTML contains the fix" and "a person sees the fix"
are different claims, and only the second one is worth making.

    python scratchpad/liveproxy.py &        # serves 127.0.0.1:8799
"""
import http.server, urllib.request, urllib.error

BASE = "https://txisd.dev"
UA = "txisd-liveproxy/1.0"


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        req = urllib.request.Request(BASE + self.path, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body, status, ctype = r.read(), r.status, r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            body, status, ctype = e.read(), e.code, "text/plain"
        except Exception as e:                      # noqa: BLE001
            body, status, ctype = str(e).encode(), 502, "text/plain"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


http.server.ThreadingHTTPServer(("127.0.0.1", 8799), H).serve_forever()
