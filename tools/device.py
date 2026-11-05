"""Identify ESP32-C3, back up all flash, then install verified firmware segments."""
import argparse, hashlib, json, re, subprocess, sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXPECTED_FIRMWARE='1.0.2'
def run(*args):
    r=subprocess.run([sys.executable,'-m','esptool',*map(str,args)],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf-8',errors='replace')
    print(r.stdout,flush=True)
    if r.returncode:raise RuntimeError('esptool fallo. No continuar con una escritura.')
    return r.stdout
def choose_port(requested):
    from serial.tools import list_ports
    if requested:return requested
    ports=list(list_ports.comports());c=[p.device for p in ports if p.vid==0x303A and p.pid==0x1001]
    if len(c)!=1:raise RuntimeError('Sin puerto Espressif unico. Usa --port COM6. Detectados: '+', '.join(p.device for p in ports))
    return c[0]
def verify_dist():
    manifest=json.loads((ROOT/'dist/manifest.json').read_text(encoding='utf-8'))
    if manifest.get('version')!=EXPECTED_FIRMWARE:
        raise RuntimeError('Faltan los binarios corregidos 1.0.2. Compila antes de instalar; no se escribio firmware.')
    if manifest.get('chip')!='esp32c3':raise RuntimeError('Chip incorrecto en manifest')
    expected={'bootloader.bin':'0x0','partitions.bin':'0x8000','boot_app0.bin':'0xe000','firmware.bin':'0x10000'}
    if len(manifest.get('files',[]))!=4:raise RuntimeError('Manifest incompleto')
    for item in manifest['files']:
        if expected.pop(item['file'],None)!=item['offset']:raise RuntimeError('Segmento u offset incorrecto')
        path=(ROOT/'dist'/item['file']).resolve()
        if path.parent!=(ROOT/'dist').resolve():raise RuntimeError('Ruta fuera de dist')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('SHA-256 incorrecto: '+path.name)
    if expected:raise RuntimeError('Faltan segmentos')
    return manifest
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['inspect','install','restore']);p.add_argument('--port');p.add_argument('--backup',type=Path);args=p.parse_args()
    port=choose_port(args.port);common=['--chip','esp32c3','--port',port,'--baud','460800','--after','hard-reset']
    identity=run(*common,'--no-stub','flash-id')
    if args.action=='inspect':return
    if args.action=='restore':
        if not args.backup:raise RuntimeError('Falta --backup')
        path=args.backup.resolve();expected=Path(str(path)+'.sha256').read_text(encoding='ascii').split()[0]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise RuntimeError('SHA-256 del respaldo incorrecto')
        run(*common,'write-flash','0x0',path);return
    manifest=verify_dist();sizes=re.findall(r'(?:Detected flash size|Flash size):\s*(\d+)\s*MB',identity,re.I)
    if not sizes or int(sizes[-1])<4:raise RuntimeError('No se confirmaron al menos 4 MB de flash. No se escribio firmware.')
    backup_dir=ROOT/'backups';backup_dir.mkdir(exist_ok=True)
    backup=backup_dir/('ESP32C3-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.bin')
    run(*common,'read-flash','0','ALL',backup)
    if backup.stat().st_size!=int(sizes[-1])*1024*1024:raise RuntimeError('Respaldo incompleto; no se escribio firmware')
    Path(str(backup)+'.sha256').write_text(hashlib.sha256(backup.read_bytes()).hexdigest()+'  '+backup.name+'\n',encoding='ascii')
    print('Respaldo completo y SHA-256 guardados:',backup,flush=True)
    segments=[]
    for item in manifest['files']:segments.extend([item['offset'],ROOT/'dist'/item['file']])
    run(*common,'write-flash','--flash-mode','dio','--flash-freq','40m','--flash-size','4MB',*segments)
    print('Escritura verificada por esptool. Abri ABRIR_PANEL.cmd para comprobar el arranque.\nSSID inicial: WiFi Gratis | Portal: http://192.168.4.1/',flush=True)
if __name__=='__main__':
    try:main()
    except Exception as exc:print('ERROR:',exc,file=sys.stderr);sys.exit(1)
