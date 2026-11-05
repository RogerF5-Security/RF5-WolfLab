"""Build a SHA-256 manifest for separate firmware segments; preserve NVS on install."""
import hashlib,json,os,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
build=ROOT/'.pio/build/c3_supermini';dist=ROOT/'dist';dist.mkdir(exist_ok=True)
files=[]
for name,offset in [('bootloader.bin','0x0'),('partitions.bin','0x8000'),('boot_app0.bin','0xe000'),('firmware.bin','0x10000')]:
    source=build/name
    if name=='boot_app0.bin' and not source.exists():source=Path(os.environ.get('PLATFORMIO_CORE_DIR',str(Path.home()/'.platformio')))/'packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin'
    target=dist/name;shutil.copy2(source,target)
    files.append(dict(file=name,offset=offset,size=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
(dist/'manifest.json').write_text(json.dumps(dict(project='RF5-WolfLab-C3',version='1.0.2',chip='esp32c3',flashMinBytes=4194304,files=files),indent=2)+'\n')
print('Firmware preparado en',dist)
