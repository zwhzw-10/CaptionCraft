import http.client
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from live import Live
from server import make_handler
from http.server import ThreadingHTTPServer
from test_live import Recognizer, Translator


class LiveAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        translator = Translator()
        translator.release.set()
        cls.live = Live(cls.temp.name, translator)
        cls.live.recognizer = Recognizer()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(None, 'test-token', np, live=cls.live))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp.cleanup()
    def request(self, path, body=None, **headers):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        connection.request('POST' if body is not None else 'GET', path, body,
            {'X-Local-Token': 'test-token', 'Content-Type': 'application/octet-stream', **headers})
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result
    def prepare(self):
        code, value = self.request('/live/config', json.dumps({'source':'en','display':'bilingual'}))
        self.assertEqual(code, 200)
        return value['session']
    def test_config_and_audio_protocol(self):
        session = self.prepare()
        options = {'session': session, 'sequence': 0, 'start': 0, 'end': .5}
        code, value = self.request('/live/audio', np.zeros(8000, dtype='<f4').tobytes(), **{'X-Caption-Options': json.dumps(options)})
        self.assertEqual(code, 200)
        self.assertEqual(value['engine'], 'sherpa')
        self.assertEqual(value['text'], 'hello world')
        options['sequence'] = 1
        self.assertEqual(self.request('/live/audio', np.array([np.nan], dtype='<f4').tobytes(), **{'X-Caption-Options':json.dumps(options)})[0], 400)
    def test_old_session_cannot_poll_or_stop_new_session(self):
        old = self.prepare()
        new = self.prepare()
        self.assertEqual(self.request('/live/translation', **{'X-Live-Session': old})[0], 409)
        self.request('/live/stop', json.dumps({'session': old}))
        self.assertEqual(self.live.session, new)
    def test_translation_request_and_auth(self):
        session = self.prepare()
        value = {'session': session,'text':'hello','language':'en','revision':1}
        self.assertEqual(self.request('/live/translate', json.dumps(value))[0], 202)
        self.assertEqual(self.request('/live/status', **{'X-Local-Token':'bad'})[0], 401)
        self.assertEqual(self.request('/live/status', Origin='https://youtube.com')[0], 403)
    def test_unsupported_engine_language(self):
        self.assertEqual(self.request('/live/config', json.dumps({'source':'ja','liveEngine':'sherpa'}))[0], 400)
