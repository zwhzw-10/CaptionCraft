import http.client
import importlib.util
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from types import SimpleNamespace
import numpy as np

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('helper_server', root / 'helper/server.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Model:
    calls = 0
    def transcribe(self, samples, **options):
        self.calls += 1
        assert options['language'] == 'en' and options['task'] == 'transcribe'
        return iter([SimpleNamespace(text=' Hello local world. ', no_speech_prob=0.01)]), None


class HelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = Model()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), module.make_handler(cls.model, 'test-token', np))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()

    def request(self, method='GET', path='/health', body=None, **extra):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = {'Host': f'127.0.0.1:{self.server.server_port}', 'X-Local-Token': 'test-token',
                   'Origin': 'chrome-extension://' + 'a' * 32, 'Content-Type': 'application/octet-stream', 'X-Caption-Options': json.dumps({'source':'en'})}
        headers.update(extra)
        conn.request(method, path, body, headers)
        response = conn.getresponse()
        data = response.read()
        result = response.status, dict(response.getheaders()), json.loads(data) if data else None
        conn.close()
        return result

    def test_health(self):
        code, headers, data = self.request()
        self.assertEqual(code, 200); self.assertEqual(data['languages'], ['en','ja','fr','es','ko','ru'])
        self.assertEqual(headers['Access-Control-Allow-Origin'], 'chrome-extension://' + 'a' * 32)

    def test_auth_and_origin(self):
        self.assertEqual(self.request(**{'X-Local-Token': 'wrong'})[0], 401)
        self.assertEqual(self.request(Origin='https://youtube.com')[0], 403)
        self.assertEqual(self.request(Host='evil.example')[0], 403)

    def test_preflight(self):
        code, headers, _ = self.request('OPTIONS')
        self.assertEqual(code, 204)
        self.assertEqual(headers['Access-Control-Allow-Private-Network'], 'true')

    def test_recognition_and_silence(self):
        code, _, result = self.request('POST', '/transcribe', np.full(64000, .03, dtype='<f4').tobytes())
        self.assertEqual(code, 200); self.assertEqual(result['text'], 'Hello local world.')
        count = self.model.calls
        self.assertEqual(self.request('POST', '/transcribe', np.zeros(64000, dtype='<f4').tobytes())[2]['text'], '')
        self.assertEqual(count, self.model.calls)

    def test_bad_pcm(self):
        self.assertEqual(self.request('POST', '/transcribe', b'bad')[0], 413)
        self.assertEqual(self.request('POST', '/transcribe', b'x' * (module.MAX_BYTES + 4))[0], 413)
        self.assertEqual(self.request('POST', '/transcribe', np.array([np.nan], dtype='<f4').tobytes())[0], 400)
        self.assertEqual(self.request('POST', '/transcribe', np.array([2], dtype='<f4').tobytes())[0], 400)
        self.assertEqual(self.request('GET', '/missing')[0], 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
