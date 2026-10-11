import importlib.util
import unittest
import tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from types import SimpleNamespace as S

spec=importlib.util.spec_from_file_location('preload',Path(__file__).resolve().parents[1]/'helper/preload.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
    def test_actual_download_path(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            folder=Path(directory); actual=folder/'audio.m4a'; actual.write_bytes(b'completed')
            self.assertEqual(m.find_downloaded_audio(folder,{'requested_downloads':[{'filepath':str(actual)}]},str(folder/'audio.webm'),[]),actual.resolve())
            self.assertEqual(m.find_downloaded_audio(folder,{},str(folder/'wrong.webm'),[str(actual)]),actual.resolve())
            self.assertEqual(m.find_downloaded_audio(folder,{},str(folder/'wrong.webm'),[]),actual.resolve())
            actual.unlink(); (folder/'audio.m4a.part').write_bytes(b'incomplete')
            with self.assertRaisesRegex(RuntimeError,'No completed audio'):m.find_downloaded_audio(folder,{},str(actual),[])
    def test_urls(self):
        for url in ['https://www.youtube.com/watch?v=abcdefghijk&t=10','https://youtu.be/abcdefghijk','https://www.youtube.com/shorts/abcdefghijk']:
            self.assertEqual(m.video_id(url),'abcdefghijk')
        for url in ['http://youtube.com/watch?v=abcdefghijk','https://evil.example/watch?v=abcdefghijk','https://youtube.com/watch?v=../bad','https://youtube.com/playlist?list=x']:
            with self.assertRaises(ValueError):m.video_id(url)
    def test_cues(self):
        cues=m.make_cues([S(no_speech_prob=.01,words=[S(word='Hello',start=1,end=1.4),S(word='world.',start=1.5,end=2)],text='Hello world.',start=1,end=2),S(no_speech_prob=.01,words=None,text='Next.',start=2.1,end=3)])
        self.assertEqual(cues[0]['text'],'Hello world.')
        self.assertEqual(cues[0]['end'],2.1)
        self.assertEqual(cues[1]['start'],2.1)
        self.assertTrue(all(c['end']>c['start'] for c in cues))
if __name__=='__main__':unittest.main(verbosity=2)
