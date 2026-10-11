import io,json,struct,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'native'))
from host import read_message,write_message,Assistant

class SplitReader(io.BytesIO):
    def read(self,n=-1):return super().read(min(n,2))

class NativeTests(unittest.TestCase):
    def test_unicode_and_partial_reads(self):
        stream=io.BytesIO();write_message(stream,{'type':'status','text':'字幕'});data=stream.getvalue()
        self.assertEqual(struct.unpack('<I',data[:4])[0],len(data[4:]))
        self.assertEqual(read_message(SplitReader(data))['text'],'字幕')
    def test_bad_length_and_payload(self):
        for size in [0,65537]:
            with self.assertRaises(ValueError):read_message(io.BytesIO(struct.pack('<I',size)))
        with self.assertRaises(EOFError):read_message(io.BytesIO(b'\x04\0\0\0{}'))
        with self.assertRaises(ValueError):read_message(io.BytesIO(b'\x02\0\0\0[]'))
    def test_pairing_is_persistent(self):
        with tempfile.TemporaryDirectory() as directory:
            first=Assistant(Path(directory));second=Assistant(Path(directory))
            self.assertEqual(first.token,second.token);self.assertGreaterEqual(len(first.token),32)
            self.assertEqual(first.status()['state'],'stopped')
