"""
FreshMart - Static Website Server
=================================
Serves the clean static grocery storefront from `grocery-website/`.
Includes strict no-cache headers so changes are always fresh.
"""

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5050
DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grocery-website")


class NoCacheHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler that disables all browser caching."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def run_server():
    server_address = ("127.0.0.1", PORT)
    httpd = HTTPServer(server_address, NoCacheHandler)
    url = f"http://127.0.0.1:{PORT}"

    print("=================================================================")
    print(f" FreshMart Static Website Server Running at: {url}")
    print(f" Serving Directory: {DIRECTORY}")
    print(" (Cache is completely disabled)")
    print("=================================================================")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n Server stopped.")
        sys.exit(0)


if __name__ == "__main__":
    run_server()
