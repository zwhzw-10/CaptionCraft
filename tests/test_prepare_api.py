import http.client
import importlib.util
import json
import threading
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from http.server import ThreadingHTTPServer
import numpy as np
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('server',root/'helper/server.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
class Stub:
    def status(self):return {'state':'ready','videoId':'abcdefghijk','cues':[{'start':0,'end':1,'text':'Hello'}]}
    def begin(self,url,uploaded=None,settings=None,position=0):
        if url!='https://youtube.com/watch?v=abcdefghijk':raise ValueError('bad url')
        return {'state':'recognizing','upload':uploaded is not None}
    def cancel(self):pass
    def prioritize(self,seconds):
        if float(seconds)<0:raise ValueError('bad seek')
class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),s.make_handler(None,'test-token',np,Stub()))
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
    def req(self,path,body=None,**headers):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        h={'Host':f'127.0.0.1:{self.server.server_port}','X-Local-Token':'test-token','Content-Type':'application/json'};h.update(headers)
        conn.request('POST' if body is not None else 'GET',path,body,h)
        response=conn.getresponse();result=(response.status,json.loads(response.read()));conn.close();return result
    def test_routes(self):
        self.assertEqual(self.req('/prepare/status')[1]['state'],'ready')
        self.assertEqual(self.req('/prepare',json.dumps({'url':'https://youtube.com/watch?v=abcdefghijk'}))[0],202)
        self.assertTrue(self.req('/prepare/upload',b'audio',**{'X-Video-URL':'https://youtube.com/watch?v=abcdefghijk'})[1]['upload'])
        self.assertEqual(self.req('/prepare',json.dumps({'url':'https://evil.example/'}))[0],400)
        self.assertEqual(self.req('/prepare',b'bad json')[0],400)
        self.assertEqual(self.req('/prepare',json.dumps({'url':'https://youtube.com/watch?v=abcdefghijk','settings':{'source':'de'}}))[0],400)
        self.assertEqual(self.req('/prepare/seek',json.dumps({'seconds':60}))[0],200)
        self.assertEqual(self.req('/prepare/seek',json.dumps({'seconds':-1}))[0],400)
        self.assertEqual(self.req('/prepare/cancel',b'')[0],200)
        self.assertEqual(self.req('/prepare/status',**{'X-Local-Token':'bad'})[0],401)
if __name__=='__main__':unittest.main(verbosity=2)
