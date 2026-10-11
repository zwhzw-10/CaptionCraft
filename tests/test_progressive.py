import json
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from language_settings import normalize_settings, cache_suffix
from local_translate import route_for, unpack_model
from preload import make_cues, merged_ranges, pick_chunk, parse_json3, Preloader

class Model:
    def transcribe(self, pcm, **options):
        self.options = options
        word = S(word='こんにちは。', start=1, end=2)
        return iter([S(text=word.word, start=1, end=2, words=[word], no_speech_prob=.01)]), S(language='ja')

class Tests(unittest.TestCase):
    def test_independent_languages(self):
        settings = normalize_settings({'source':'es','target':'ja','display':'bilingual'})
        self.assertEqual(settings['source'], 'es')
        self.assertEqual(settings['target'], 'ja')
        self.assertEqual(cache_suffix(settings,'base'), cache_suffix({**settings,'target':'zh'},'base'))
        for invalid in [{'source':'de'},{'target':'xx'},{'display':'bad'}]:
            with self.assertRaises(ValueError): normalize_settings(invalid)

    def test_priority_and_coverage(self):
        self.assertEqual(pick_chunk({0},4,95),3)
        self.assertEqual(pick_chunk({0,3},4,95),1)
        self.assertEqual(merged_ranges({0,1,3},110),[[0,60],[90,110]])

    def test_no_spaces_inserted_into_japanese(self):
        words = [S(word='私',start=0,end=.3),S(word='は',start=.3,end=.5),S(word='学生です。',start=.5,end=1)]
        self.assertEqual(make_cues([S(no_speech_prob=.01,words=words)],'ja')[0]['text'],'私は学生です。')

    def test_subtitle_rollup_nonoverlap(self):
        cues=parse_json3({'events':[{'tStartMs':1000,'dDurationMs':2000,'segs':[{'utf8':'Hello'}]},
                                  {'tStartMs':2000,'dDurationMs':1000,'segs':[{'utf8':'world'}]}]})
        self.assertEqual(cues[0]['end'],2)
        self.assertEqual(cues[1]['text'],'world')

    def test_translation_routes(self):
        index=[{'from_code':a,'to_code':b} for a,b in [('ja','en'),('en','zh'),('es','en'),('en','fr')]]
        self.assertEqual(len(route_for(index,'ja','zh')),2)
        self.assertEqual(len(route_for(index,'es','fr')),2)
        self.assertEqual(route_for(index,'ja','ja'),[])
        with self.assertRaises(ValueError): route_for(index,'ja','ko')

    def test_archive_paths_and_language(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as td:
            archive=Path(td)/'bad.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('../outside','x')
                z.writestr('p/metadata.json',json.dumps({'from_code':'ja','to_code':'en'}))
            with self.assertRaisesRegex(ValueError,'Unsafe'):unpack_model(archive,Path(td)/'out','ja','en')

    def test_publish_partial_original_and_translation_separately(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as td:
            worker=Preloader(td,None,threading.Lock())
            worker.publish({0:[{'start':0,'end':2,'text':'hola'}]}, {0},60)
            self.assertEqual(worker.status()['readyRanges'],[[0,30]])
            self.assertEqual(worker.status()['translationRanges'],[])
            worker.publish({0:[{'start':0,'end':2,'text':'hola','translation':'你好'}]}, {0},60)
            self.assertEqual(worker.status()['translationRanges'],[[0,30]])

    def test_multilingual_progressive_job_and_original_cache_reuse(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as td:
            model=Model();worker=Preloader(td,model,threading.Lock())
            worker.download=lambda *_:Path(td)/'audio'
            updates=[]
            original_update=worker.update
            def capture(**data):
                original_update(**data);updates.append(worker.status())
            worker.update=capture
            with patch('preload.audio_duration',return_value=65),patch('preload.decode_window',return_value=[0]*16000):
                worker.begin('https://youtube.com/watch?v=abcdefghijk',settings={'source':'ja','display':'original','preferExisting':False},position=35)
                worker.worker.join(3)
            final=worker.status()
            self.assertEqual(final['state'],'ready')
            self.assertEqual(final['language'],'ja')
            self.assertEqual(model.options['language'],'ja')
            partial=next(s for s in updates if s.get('cues') and not s.get('complete'))
            self.assertEqual(partial['readyRanges'],[[30,60]])
            self.assertTrue(any(c['start']>=30 for c in partial['cues']))
            cache=list((Path(td)/'.cache/captions').glob('*original.json'))
            self.assertEqual(len(cache),1)
            def forbidden(*_):raise AssertionError('Original audio must not be downloaded again')
            worker.download=forbidden
            worker.begin('https://youtube.com/watch?v=abcdefghijk',settings={'source':'ja','display':'original','preferExisting':False})
            worker.worker.join(3)
            self.assertEqual(worker.status()['state'],'ready')

if __name__=='__main__': unittest.main(verbosity=2)

