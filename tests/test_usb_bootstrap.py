import importlib.util,json,threading,time,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('usb_panel',Path(__file__).resolve().parents[1]/'host/wolflab.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
class Endpoint:
    def __init__(self,drop_first=False,prefix=b''):
        self.drop_first=drop_first;self.prefix=prefix;self.buf=bytearray();self.writes=[]
    @property
    def in_waiting(self):return len(self.buf)
    def write(self,data):
        req=json.loads(data.strip());self.writes.append(req)
        if self.drop_first and len(self.writes)==1:return len(data)
        self.buf.extend(self.prefix+b'@RF5 '+json.dumps(dict(id=req['id'],ok=True)).encode()+b'\n');return len(data)
    def read(self,n):
        if not self.buf:time.sleep(.01);return b''
        n=min(n,11);result=self.buf[:n];del self.buf[:n];return bytes(result)
class BootstrapTests(unittest.TestCase):
    def bridge(self):
        b=object.__new__(w.SerialBridge);b.stop=threading.Event();return b
    def test_first_usb_reply_lost_then_recovers_without_reopening(self):
        device=Endpoint(drop_first=True);self.assertTrue(self.bridge().exchange(device,{'cmd':'hello'})['ok'])
        self.assertEqual(len(device.writes),2);self.assertEqual(device.writes[0]['id'],device.writes[1]['id'])
    def test_boot_noise_before_protocol_marker(self):
        self.assertTrue(self.bridge().exchange(Endpoint(prefix=b'\x00ROM startup: '),{'cmd':'hello'})['ok'])
    def test_mutating_command_sent_once(self):
        device=Endpoint();self.assertTrue(self.bridge().exchange(device,{'cmd':'start'})['ok']);self.assertEqual(len(device.writes),1)
    def test_installer_rejects_previous_firmware(self):
        import tempfile
        from unittest.mock import patch
        path=Path(__file__).resolve().parents[1]/'tools/device.py'
        spec=importlib.util.spec_from_file_location('install_guard',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'dist').mkdir();(root/'dist/manifest.json').write_text(json.dumps({'chip':'esp32c3','version':'1.0.1','files':[]}))
            with patch.object(module,'ROOT',root),self.assertRaisesRegex(RuntimeError,'1.0.2'):
                module.verify_dist()
if __name__=='__main__':unittest.main(verbosity=2)
