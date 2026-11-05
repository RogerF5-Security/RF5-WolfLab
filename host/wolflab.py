"""RF5 WolfLab USB panel 1.0.3; use C3 firmware 1.0.2 for the corrected startup."""
from __future__ import annotations
import argparse
import csv
import io
import ipaddress
import json
import queue
import secrets
import sqlite3
import threading
import time
import webbrowser
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/'host/web'
DEFAULT=dict(ssid='WiFi Gratis',title='Acceso Wi-Fi',campaign='WolfLab demo',location='Presentacion',identifierMode='campaign',durationMin=15,channel=6)

def validate_config(value):
    if not isinstance(value,dict):raise ValueError('Configuracion invalida')
    out={}
    for key,maximum in [('ssid',32),('title',64),('campaign',64),('location',64)]:
        s=value.get(key)
        if not isinstance(s,str) or not 1<=len(s.encode('utf-8'))<=maximum or any(ord(c)<32 or ord(c)==127 for c in s):
            raise ValueError(f'{key}: entre 1 y {maximum} bytes UTF-8, sin caracteres de control')
        out[key]=s
    for key,lo,hi in [('durationMin',1,240),('channel',1,11)]:
        n=value.get(key)
        if type(n) is not int or not lo<=n<=hi:raise ValueError(f'{key}: entero entre {lo} y {hi}')
        out[key]=n
    if value.get('identifierMode') not in ('campaign','employee'):raise ValueError('Identificador invalido')
    out['identifierMode']=value['identifierMode']
    return out

def csv_safe(value):
    s=str(value if value is not None else '')
    return "'"+s if s.lstrip().startswith(('=','+','-','@')) or s.startswith(('\t','\r','\n')) else s

class Store:
    def __init__(self,path,retention_days=7):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=threading.RLock();self.retention_days=retention_days
        self.config=dict(DEFAULT);self.status={};self.connected=False;self.port='';self.error='Buscando firmware WolfLab por USB...';self.last_seen=None
        with self.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS records(boot_id TEXT,seq INTEGER,observed_utc TEXT,uptime_ms INTEGER,alias TEXT,name TEXT,identifier TEXT,mode TEXT,campaign TEXT,location TEXT,ssid TEXT,PRIMARY KEY(boot_id,seq))''')
            self.prune(db)
        if __import__('os').name!='nt':self.path.chmod(0o600);self.path.parent.chmod(0o700)
    @contextmanager
    def db(self):
        connection=sqlite3.connect(str(self.path),timeout=10)
        try:
            connection.execute('PRAGMA secure_delete=ON')
            with connection:yield connection
        finally:connection.close()
    def prune(self,db):
        cutoff=datetime.fromtimestamp(time.time()-self.retention_days*86400,timezone.utc).isoformat()
        db.execute('DELETE FROM records WHERE observed_utc < ?',(cutoff,))
    def ingest(self,obj):
        if not obj.get('ok'):raise ValueError(obj.get('error','Respuesta invalida'))
        status=obj.get('status',{})
        if status.get('firmware')!='RF5-WolfLab-C3':raise ValueError('Este puerto no contiene firmware RF5 WolfLab')
        config=validate_config(obj['config']);boot_id=str(status.get('bootId',''))[:64]
        incoming=obj.get('records',[])
        if not boot_id or not isinstance(incoming,list) or len(incoming)>128:raise ValueError('Snapshot fuera de limite')
        now=datetime.now(timezone.utc).isoformat()
        with self.lock,self.db() as db:
            self.prune(db)
            for r in incoming:
                db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?)',(boot_id,int(r['seq']),now,int(r['uptimeMs']),str(r['alias'])[:32],str(r.get('name',''))[:64],str(r.get('identifier',''))[:32],str(r.get('mode',''))[:16],str(r.get('campaign',''))[:64],str(r.get('location',''))[:64],str(r.get('ssid',''))[:32]))
            self.config,self.status=config,status;self.connected=True;self.error='';self.last_seen=now
    def disconnect(self,error):
        with self.lock:self.connected=False;self.error=str(error)[:250]
    def records(self):
        with self.lock,self.db() as db:
            self.prune(db);db.row_factory=sqlite3.Row
            return [dict(r) for r in db.execute('SELECT * FROM records ORDER BY observed_utc DESC,seq DESC LIMIT 5000')]
    def state(self,public=False):
        with self.lock:
            out=dict(connected=self.connected,config=dict(self.config),status=dict(self.status),lastSeen=self.last_seen)
            if public:
                with self.db() as db:
                    self.prune(db)
                    out['recent']=[dict(alias=r[0],uptime_ms=r[1]) for r in db.execute('SELECT alias,uptime_ms FROM records WHERE boot_id=? ORDER BY seq DESC LIMIT 12',(self.status.get('bootId',''),))]
            else:out.update(error=self.error,port=self.port,records=self.records(),retentionDays=self.retention_days)
            return out
    def clear(self):
        with self.lock,self.db() as db:db.execute('DELETE FROM records')

def serial_ports():
    try:
        from serial.tools import list_ports
        return [dict(port=p.device,description=p.description,esp=p.vid==0x303A and p.pid==0x1001) for p in list_ports.comports()]
    except ImportError:return []

class SerialBridge:
    def __init__(self,store,port=None):
        self.store,self.requested_port=store,port;self.jobs=queue.Queue();self.stop=threading.Event()
        threading.Thread(target=self.run,daemon=True,name='WolfLab-USB').start()
    def call(self,cmd,**kwargs):
        result,event={},threading.Event()
        self.jobs.put((dict(cmd=cmd,**kwargs),result,event,time.monotonic()+9))
        if not event.wait(10):raise TimeoutError('Sin respuesta USB; comproba la placa y el puerto')
        if 'error' in result:raise RuntimeError(result['error'])
        return result['reply']
    def exchange(self,device,payload):
        request_id=secrets.token_hex(8)
        raw=json.dumps(dict(payload,id=request_id),ensure_ascii=False,separators=(',',':')).encode()+b'\n'
        if len(raw)>2048:raise ValueError('Comando USB demasiado grande')
        # Only HELLO may be repeated: configuration/start/clear are never replayed.
        # C3 HWCDC can lose the beginning of the first reply while its IN endpoint wakes.
        hello=payload.get('cmd')=='hello'
        device.write(raw);deadline=time.monotonic()+(7 if hello else 5);buf=bytearray()
        retry_at=time.monotonic()+1;attempts=1;received=0;frames=0;download_mode=False
        while time.monotonic()<deadline and not self.stop.is_set():
            part=device.read(min(max(device.in_waiting,1),4096));received+=len(part);buf.extend(part)
            lower=bytes(buf).lower()
            if b'waiting for download' in lower or b'download_boot' in lower:download_mode=True
            if hello and attempts<4 and time.monotonic()>=retry_at:
                device.write(b'\n'+raw);attempts+=1;retry_at=time.monotonic()+1
            if len(buf)>131072:raise RuntimeError('Respuesta USB fuera de limite')
            while b'\n' in buf:
                line,_,rest=buf.partition(b'\n');buf=bytearray(rest)
                marker=line.find(b'@RF5 ')
                if marker<0:continue
                frames+=1
                try:obj=json.loads(line[marker+5:])
                except (ValueError,UnicodeError):continue
                if not isinstance(obj,dict):continue
                if obj.get('id')==request_id:
                    if not obj.get('ok'):raise ValueError(obj.get('error','Error del firmware'))
                    return obj
        if download_mode:
            raise TimeoutError('La placa esta en modo de descarga. Presiona RESET una vez, sin BOOT.')
        raise TimeoutError(f'USB abierto, sin respuesta WolfLab valida. Recibidos: {received} bytes; tramas RF5: {frames}; intentos: {attempts}. Verifica el arranque del firmware.')
    def run(self):
        while not self.stop.is_set():
            device=None
            try:
                import serial
                ports=[p['port'] for p in serial_ports() if p['esp']]
                port=self.requested_port or (ports[0] if len(ports)==1 else None)
                if not port:raise RuntimeError('Sin puerto Espressif unico. Conecta la placa o usa --port COM6')
                device=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2)
                device.dtr=False;device.rts=False;device.port=port;device.open();self.store.port=port
                # Terminate stale input and give the native USB endpoint time to settle.
                device.write(b'\n');self.stop.wait(.35)
                self.store.ingest(self.exchange(device,{'cmd':'hello'}));next_poll=0
                while not self.stop.is_set():
                    try:payload,result,event,deadline=self.jobs.get(timeout=.1)
                    except queue.Empty:payload=None
                    if payload:
                        try:
                            if time.monotonic()>deadline:raise TimeoutError('Comando vencido; no se ejecuto')
                            result['reply']=self.exchange(device,payload)
                        except Exception as exc:result['error']=str(exc)
                        finally:event.set()
                        next_poll=0
                    if time.monotonic()>=next_poll:
                        self.store.ingest(self.exchange(device,{'cmd':'snapshot'}));next_poll=time.monotonic()+2.5
            except Exception as exc:
                self.store.disconnect(exc)
                while True:
                    try:_,result,event,_=self.jobs.get_nowait()
                    except queue.Empty:break
                    result['error']=str(exc);event.set()
                self.stop.wait(3)
            finally:
                if device is not None:device.close()

class DemoBridge:
    def __init__(self,store):
        self.store=store;self.stop=threading.Event();self.lock=threading.RLock();self.boot_at=time.monotonic();self.started_at=self.boot_at
        self.config=dict(DEFAULT);self.boot_id='demo-'+secrets.token_hex(6);self.active=True;self.rows=[];self.seq=0;self.count=0
        self.store.port='DEMO / SIN RADIO'
        for _ in range(3):self.add()
        self.refresh();threading.Thread(target=self.run,daemon=True,name='WolfLab-demo').start()
    def add(self):
        self.seq+=1;self.count+=1
        self.rows.append(dict(seq=self.seq,uptimeMs=int((time.monotonic()-self.boot_at)*1000),alias=f'Oveja {self.seq:03}',name=f'Demo {self.seq:03}',identifier=f'DEMO-{self.seq:03}',mode=self.config['identifierMode'],campaign=self.config['campaign'],location=self.config['location'],ssid=self.config['ssid']))
        self.rows=self.rows[-128:]
    def refresh(self):
        elapsed=int(time.monotonic()-self.started_at)
        if elapsed>=self.config['durationMin']*60:self.active=False
        status=dict(firmware='RF5-WolfLab-C3',version='1.0.1-demo',chip='SIMULACION',flashBytes=4194304,bootId=self.boot_id,active=self.active,uptimeMs=int((time.monotonic()-self.boot_at)*1000),remainingSec=max(0,self.config['durationMin']*60-elapsed) if self.active else 0,connectedNow=2 if self.active else 0,associations=self.count+4,portalSessions=self.count+2,submissions=self.count,stored=len(self.rows),overwritten=max(0,self.count-128),rateLimited=0,freeHeap=130000)
        self.store.ingest(dict(ok=True,config=self.config,status=status,records=self.rows))
    def run(self):
        while not self.stop.wait(8):
            with self.lock:
                self.refresh()
                if self.active:self.add();self.refresh()
    def call(self,cmd,**kwargs):
        with self.lock:
            if cmd=='configure':self.config=validate_config(kwargs['config']);self.started_at=time.monotonic();self.active=True
            elif cmd=='pause':self.active=False
            elif cmd=='start':self.started_at=time.monotonic();self.active=True
            elif cmd=='clear':self.rows=[];self.count=0
            elif cmd not in ('snapshot','hello'):raise ValueError('Comando invalido')
            self.refresh();return {'ok':True}

def make_handler(store,bridge,demo,wall_key,admin_key):
    class Handler(BaseHTTPRequestHandler):
        server_version='WolfLab/1.0.2'
        def log_message(self,*_):pass
        def local(self):
            try:return ipaddress.ip_address(self.client_address[0]).is_loopback
            except ValueError:return False
        def host_ok(self):
            try:
                host=urlsplit('http://'+self.headers.get('Host','')).hostname
                return host=='localhost' or bool(ipaddress.ip_address(host))
            except (ValueError,TypeError):return False
        def private_ok(self):return self.local() and secrets.compare_digest(self.headers.get('X-WolfLab-Key',''),admin_key)
        def wall_ok(self,q):return self.local() or secrets.compare_digest(q.get('key',[''])[0],wall_key)
        def send(self,body,ctype='application/json; charset=utf-8',status=200):
            if not isinstance(body,(str,bytes)):body=json.dumps(body,ensure_ascii=False,separators=(',',':'))
            if isinstance(body,str):body=body.encode()
            self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)))
            for k,v in [('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),('Referrer-Policy','no-referrer'),('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]:self.send_header(k,v)
            self.end_headers();self.wfile.write(body)
        def do_GET(self):
            if not self.host_ok():return self.send({'error':'Host no permitido'},status=403)
            parsed=urlsplit(self.path);path=parsed.path;q=parse_qs(parsed.query)
            if path=='/' and self.local():return self.send((WEB/'index.html').read_text(encoding='utf-8').replace('{{ADMIN_KEY}}',admin_key),'text/html; charset=utf-8')
            if path=='/wall' and self.wall_ok(q):return self.send((WEB/'wall.html').read_bytes(),'text/html; charset=utf-8')
            if path in ('/assets/style.css','/assets/app.js','/assets/wall.js','/assets/wolf.svg','/assets/sheep.svg'):
                name=path.rsplit('/',1)[1]
                ctype='image/svg+xml' if name.endswith('.svg') else 'text/css; charset=utf-8' if name.endswith('.css') else 'text/javascript; charset=utf-8'
                return self.send((WEB/name).read_bytes(),ctype)
            if path=='/api/public' and self.wall_ok(q):
                result=store.state(public=True);result['demo']=demo;return self.send(result)
            if not self.private_ok():return self.send({'error':'Acceso restringido al operador local'},status=403)
            if path=='/api/state':
                result=store.state();result['demo']=demo;return self.send(result)
            if path=='/api/scenarios':return self.send(json.loads((ROOT/'scenarios.json').read_text(encoding='utf-8')))
            if path=='/api/ports':return self.send(serial_ports())
            if path=='/api/export.json':return self.send(dict(schema='rf5-wolflab/1',exportedUtc=datetime.now(timezone.utc).isoformat(),identity='Declarada por el visitante; no verificada',records=store.records()))
            if path=='/api/export.csv':
                out=io.StringIO(newline='');keys=['boot_id','seq','observed_utc','uptime_ms','alias','name','identifier','mode','campaign','location','ssid']
                writer=csv.DictWriter(out,fieldnames=keys);writer.writeheader()
                for r in store.records():writer.writerow({k:csv_safe(r[k]) for k in keys})
                return self.send('\ufeff'+out.getvalue(),'text/csv; charset=utf-8')
            self.send({'error':'Ruta inexistente'},status=404)
        def do_POST(self):
            if not self.host_ok() or not self.private_ok():return self.send({'error':'Acceso restringido'},status=403)
            origin=self.headers.get('Origin')
            if origin and origin!='http://'+self.headers.get('Host',''):return self.send({'error':'Origen no permitido'},status=403)
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send({'error':'Se requiere JSON'},status=415)
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 1<=size<=8192:return self.send({'error':'Tamano fuera de limite'},status=413)
                data=json.loads(self.rfile.read(size))
                if not isinstance(data,dict):raise ValueError('Objeto JSON requerido')
                if self.path=='/api/configure':
                    config=validate_config(data.get('config'))
                    if config['identifierMode']=='employee' and data.get('ackPersonalData') is not True:raise ValueError('Confirma el tratamiento de IMB en el panel')
                    result=bridge.call('configure',config=config)
                elif self.path=='/api/control':
                    action=data.get('action')
                    if action not in ('start','pause','restart'):raise ValueError('Accion invalida')
                    # Firmware 1.0.2 start restarts an active AP and clears only sessions.
                    # Records, sequence numbers and the saved scenario remain intact.
                    result=bridge.call('start' if action=='restart' else action)
                elif self.path=='/api/clear':
                    if data.get('confirmation')!='BORRAR':raise ValueError('Escribi BORRAR para eliminar los registros')
                    result=bridge.call('clear');store.clear()
                else:return self.send({'error':'Ruta inexistente'},status=404)
                return self.send(result)
            except (ValueError,TypeError,KeyError) as exc:self.send({'error':str(exc)},status=400)
            except Exception as exc:self.send({'error':str(exc)},status=503)
    return Handler

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo',action='store_true');parser.add_argument('--port');parser.add_argument('--listen',default='127.0.0.1');parser.add_argument('--http-port',type=int,default=8765);parser.add_argument('--no-browser',action='store_true');parser.add_argument('--retention-days',type=int,default=7)
    args=parser.parse_args()
    if not 1<=args.retention_days<=30:parser.error('Retencion: entre 1 y 30 dias')
    store=Store(ROOT/'private'/('demo.sqlite3' if args.demo else 'campaign.sqlite3'),args.retention_days)
    bridge=DemoBridge(store) if args.demo else SerialBridge(store,args.port)
    wall_key,admin_key=secrets.token_urlsafe(24),secrets.token_urlsafe(32)
    server=ThreadingHTTPServer((args.listen,args.http_port),make_handler(store,bridge,args.demo,wall_key,admin_key));server.daemon_threads=True
    url=f'http://127.0.0.1:{args.http_port}'
    print(f"RF5 WolfLab {'DEMO / SIN RADIO' if args.demo else 'USB'} | {url}",flush=True)
    if args.listen!='127.0.0.1':print(f'Mural remoto (red de confianza): http://<IP-DE-ESTA-PC>:{args.http_port}/wall?key={wall_key}',flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:pass
    finally:bridge.stop.set();server.server_close()

if __name__=='__main__':main()
