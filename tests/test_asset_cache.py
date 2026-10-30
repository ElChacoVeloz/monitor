import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from server import Handler

class AssetCacheTest(unittest.TestCase):
    def test_query_assets_are_not_cached(self):
        srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            for path in ['/style.css?v=lcars1', '/app.js?v=lcars1', '/index.html?v=test']:
                with self.subTest(path=path):
                    with urllib.request.urlopen(f'http://127.0.0.1:{srv.server_port}{path}') as response:
                        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join()
