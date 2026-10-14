import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from live import Live, stream_settings


class Stream:
    def __init__(self):
        self.count = 0
    def accept_waveform(self, rate, pcm):
        assert rate == 16000
        self.count += len(pcm)


class Recognizer:
    final = False
    def create_stream(self):
        return Stream()
    def is_ready(self, stream):
        return False
    def get_result(self, stream):
        return 'hello world'
    def is_endpoint(self, stream):
        return self.final
    def reset(self, stream):
        stream.count = 0


class Translator:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = []
    def ensure(self, source, target, **options):
        options['check']()
        return [(source, target)]
    def translate(self, texts, route, check, beam_size):
        self.calls.append(texts[0])
        self.entered.set()
        self.release.wait(3)
        check()
        return ['translated ' + texts[0]]


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.translator = Translator()
        self.live = Live(self.temp.name, self.translator)
        self.live.recognizer = Recognizer()
        self.session = self.live.prepare({'source': 'en', 'target': 'zh', 'display': 'bilingual'})['session']
    def tearDown(self):
        self.translator.release.set()
        self.live.close()
        self.temp.cleanup()
    def push(self, start, end, sequence=0, session=None):
        return self.live.push(np.zeros(round((end-start)*16000), dtype=np.float32),
            {'start': start, 'end': end, 'sequence': sequence, 'session': session or self.session}, np)
    def test_engine_language_policy(self):
        self.assertEqual(stream_settings({'source': 'en'})['engine'], 'sherpa')
        self.assertEqual(stream_settings({'source': 'ja'})['engine'], 'whisper')
        self.assertEqual(stream_settings({'source': 'auto'})['engine'], 'whisper')
        with self.assertRaises(ValueError):
            stream_settings({'source': 'ja', 'liveEngine': 'sherpa'})
    def test_overlap_samples_not_fed_twice(self):
        self.push(0, .5)
        self.push(0, 1, 1)
        self.assertEqual(self.live.stream.count, 16000)
    def test_out_of_order_and_old_session_rejected(self):
        self.push(0, .5)
        with self.assertRaises(ValueError):
            self.push(0, .5)
        self.live.prepare({'source': 'en'})
        with self.assertRaises(ValueError):
            self.push(0, 1, 1)
    def test_gap_resets_stream_and_marks_loss(self):
        first = self.push(0, .5)
        next_ = self.push(3, 3.5, 1)
        self.assertTrue(next_['gap'])
        self.assertGreater(next_['utterance'], first['utterance'])
        self.assertEqual(self.live.stream.count, 8000)
    def test_invalid_duration_rejected(self):
        with self.assertRaises(ValueError):
            self.live.push(np.zeros(8000), {'start': 0, 'end': 4, 'session': self.session, 'sequence': 0}, np)
    def test_endpoint_finalization(self):
        self.live.recognizer.final = True
        result = self.push(0, .5)
        self.assertTrue(result['final'])
        self.assertEqual(self.live.stream.count, 0)
    def queue(self, text, revision):
        return self.live.queue_translation({'session': self.session, 'language': 'en', 'text': text, 'revision': revision})
    def test_translation_queue_bounded_and_asr_independent(self):
        self.queue('first', 1)
        self.assertTrue(self.translator.entered.wait(1))
        self.queue('second', 2)
        self.queue('latest', 3)
        self.assertEqual(self.live.pending['text'], 'latest')
        # A translator waiting on a model/network cannot hold ASR's lock.
        started = time.monotonic()
        self.assertEqual(self.push(0, .5)['text'], 'hello world')
        self.assertLess(time.monotonic() - started, .3)
        self.translator.release.set()
        deadline = time.monotonic() + 2
        while self.live.worker and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(self.translator.calls, ['first', 'latest'])
        self.assertEqual(self.live.translation_status(self.session)['revision'], 3)
    def test_old_revision_cannot_replace_latest(self):
        self.queue('latest', 5)
        self.assertTrue(self.queue('old', 2)['ignored'])
    def test_cancelled_translation_cannot_leak_into_new_session(self):
        self.queue('old audio', 1)
        self.assertTrue(self.translator.entered.wait(1))
        new = self.live.prepare({'source': 'en'})['session']
        self.translator.release.set()
        deadline = time.monotonic()+2
        while self.live.worker and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertEqual(self.live.translation_status(new)['state'], 'idle')


if __name__ == '__main__':
    unittest.main()
