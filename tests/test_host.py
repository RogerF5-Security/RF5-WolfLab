import importlib.util,json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
w=load('wolflab',ROOT/'host/wolflab.py');d=load('device',ROOT/'tools/device.py')

class HostTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=w.Store(Path(self.tmp.name)/'test.db');self.bridge=w.DemoBridge(self.store);self.bridge.stop.set()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),w.make_handler(self.store,self.bridge,True,'wall-secret','admin-secret'))
        threading.Thread(target=self.server.serve_forever,daemon=True).start();self.url=f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def request(self,path,body=None,key='admin-secret',extra=None):
        headers={'X-WolfLab-Key':key}
        if body is not None:headers['Content-Type']='application/json'
        if extra:headers.update(extra)
        req=urllib.request.Request(self.url+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=3) as r:return r.status,r.read(),r.headers
        except urllib.error.HTTPError as e:
            with e:return e.code,e.read(),e.headers
    def test_public_has_no_private_fields(self):
        self.bridge.rows[0].update(name='SECRET-PERSON',identifier='PRIVATE-EMPLOYEE');self.bridge.boot_id='private-test';self.bridge.refresh()
        code,body,_=self.request('/api/public',key='');self.assertEqual(code,200);self.assertNotIn(b'SECRET-PERSON',body);self.assertNotIn(b'PRIVATE-EMPLOYEE',body)
        self.assertEqual(set(json.loads(body)['recent'][0]),{'alias','uptime_ms'})
    def test_admin_requires_token_and_same_origin(self):
        self.assertEqual(self.request('/api/state',key='bad')[0],403)
        self.assertEqual(self.request('/api/control',{'action':'pause'},extra={'Origin':'https://evil.example'})[0],403);self.assertTrue(self.bridge.active)
        self.assertEqual(self.request('/api/control',{'action':'pause'})[0],200);self.assertFalse(self.bridge.active)
    def test_config_rejects_utf8_overflow_atomically(self):
        c=dict(w.DEFAULT,ssid='🐺'*9);self.assertEqual(self.request('/api/configure',{'config':c})[0],400);self.assertEqual(self.bridge.config['ssid'],w.DEFAULT['ssid'])
        c=dict(w.DEFAULT,ssid='Evento_2');self.assertEqual(self.request('/api/configure',{'config':c})[0],200);self.assertEqual(self.store.config['ssid'],'Evento_2')
        for v in [True,1.5,0,241]:self.assertEqual(self.request('/api/configure',{'config':dict(c,durationMin=v)})[0],400)
    def test_employee_mode_ack(self):
        c=dict(w.DEFAULT,identifierMode='employee');self.assertEqual(self.request('/api/configure',{'config':c})[0],400)
        self.assertEqual(self.request('/api/configure',{'config':c,'ackPersonalData':True})[0],200)
    def test_next_demo_restarts_without_deleting_evidence_or_scenario(self):
        before=self.store.records();config=dict(self.bridge.config);sequence=self.bridge.seq
        with patch.object(self.bridge,'call',wraps=self.bridge.call) as call:
            self.assertEqual(self.request('/api/control',{'action':'restart'})[0],200)
            call.assert_called_once_with('start')
        self.assertEqual(self.store.records(),before)
        self.assertEqual(self.bridge.config,config);self.assertEqual(self.bridge.seq,sequence)
        self.assertTrue(self.bridge.active)
        self.assertEqual(self.request('/api/control',{'action':'invalid'})[0],400)
    def test_dedup_and_new_boot(self):
        count=len(self.store.records());self.bridge.refresh();self.bridge.refresh();self.assertEqual(len(self.store.records()),count)
        self.bridge.boot_id='second-boot';self.bridge.refresh();self.assertEqual(len(self.store.records()),count*2)
    def test_csv_formula_and_content_type(self):
        for s in ['=HYPERLINK(1)',' +SUM(1)','@cmd','\ttext']:self.assertTrue(w.csv_safe(s).startswith("'"))
        self.bridge.rows[0]['name']='=HYPERLINK(1)';self.bridge.boot_id='csv';self.bridge.refresh();code,body,headers=self.request('/api/export.csv')
        self.assertEqual(code,200);self.assertIn(b"'=HYPERLINK(1)",body);self.assertIn('text/csv',headers['Content-Type']);self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
    def test_clear_confirmation_and_both_stores(self):
        self.assertEqual(self.request('/api/clear',{'confirmation':'no'})[0],400);self.assertTrue(self.store.records())
        self.assertEqual(self.request('/api/clear',{'confirmation':'BORRAR'})[0],200);self.assertFalse(self.store.records());self.assertFalse(self.bridge.rows)
    def test_dns_rebinding(self):self.assertEqual(self.request('/',extra={'Host':'attacker.example'})[0],403)
    def test_traversal(self):self.assertNotEqual(self.request('/assets/../../private/test.db')[0],200)
    def test_remote_client_cannot_admin_with_valid_key(self):
        cls=w.make_handler(self.store,self.bridge,True,'wall-secret','admin-secret');h=object.__new__(cls);h.client_address=('192.0.2.7',1234);h.headers={'X-WolfLab-Key':'admin-secret'}
        self.assertFalse(h.private_ok());self.assertFalse(h.wall_ok({}));self.assertTrue(h.wall_ok({'key':['wall-secret']}))
    def test_retention_applied_without_restart(self):
        with self.store.db() as db:db.execute("UPDATE records SET observed_utc='2000-01-01T00:00:00+00:00'")
        self.assertFalse(self.store.records())

class FakeSerial:
    def __init__(self,ok=True):self.buf=bytearray();self.ok=ok
    def write(self,data):
        req=json.loads(data);self.buf=bytearray(b'Boot noise\n@RF5 {broken}\n'+b'@RF5 '+json.dumps(dict(id='wrong',ok=True)).encode()+b'\n@RF5 '+json.dumps(dict(id=req['id'],ok=self.ok,error='rejected')).encode()+b'\n')
    @property
    def in_waiting(self):return len(self.buf)
    def read(self,n):
        n=min(n,7);result=self.buf[:n];del self.buf[:n];return bytes(result)

class SerialAndInstallerTests(unittest.TestCase):
    def bridge(self):
        b=object.__new__(w.SerialBridge);b.stop=threading.Event();return b
    def test_serial_chunking_noise_and_request_matching(self):self.assertTrue(self.bridge().exchange(FakeSerial(),{'cmd':'hello'})['ok'])
    def test_serial_rejection_and_command_cap(self):
        with self.assertRaises(ValueError):self.bridge().exchange(FakeSerial(False),{'cmd':'pause'})
        with self.assertRaises(ValueError):self.bridge().exchange(FakeSerial(),{'cmd':'configure','config':{'ssid':'x'*3000}})
    def test_backup_failure_prevents_flash_write(self):
        operations=[]
        def fake_run(*args):
            operations.append(args)
            if 'read-flash' in args:raise RuntimeError('backup failed')
            return 'Detected flash size: 4MB'
        with tempfile.TemporaryDirectory() as tmp,patch.object(d,'ROOT',Path(tmp)),patch.object(d,'choose_port',return_value='COMFAKE'),patch.object(d,'verify_dist',return_value={'files':[]}),patch.object(d,'run',side_effect=fake_run),patch.object(d.sys,'argv',['device.py','install']):
            with self.assertRaises(RuntimeError):d.main()
        self.assertFalse(any('write-flash' in op for op in operations))

if __name__=='__main__':unittest.main(verbosity=2)
