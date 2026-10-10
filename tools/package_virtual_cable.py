#!/usr/bin/env python3
"""Package one LINK4BRICK app, with normal-game virtual cable integration."""
import argparse,hashlib,json,shutil,struct,subprocess,sys,tempfile,zipfile
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--build',type=Path,required=True);parser.add_argument('--core',type=Path,required=True)
parser.add_argument('--link',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--host',action='store_true',help='Layout test only; not installable on Brick')
args=parser.parse_args();ROOT=Path(__file__).resolve().parent.parent
bins=['linkaudio-send','linkclock-send','audiocast-session','alsa-probe','audiocast-cksum','audiocast-core-probe','audiocast-settings']
def arm64(p):
  header=p.read_bytes()[:64]
  assert header[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',header,18)[0]==183,p
if not args.host:
  for p in [args.core]+[args.build/n for n in bins]:arm64(p)
with tempfile.TemporaryDirectory() as t:
  stage=Path(t);app=stage/'Apps/LINK4BRICK';shutil.copytree(ROOT/'Apps/LINK4BRICK',app)
  (app/'bin').mkdir();(app/'cores').mkdir()
  for n in bins:shutil.copyfile(args.build/n,app/'bin'/n);(app/'bin'/n).chmod(0o755)
  shutil.copyfile(args.core,app/'cores/mgba-link_libretro.so');(app/'cores/mgba-link_libretro.so').chmod(0o755)
  config=app/'cable/config.txt';config.write_text('PROTOCOL=fms-gba\nPPQN=24\nOFFSET_US=0\n')
  meta=json.loads((app/'config.json').read_text());meta['description']='LINK4BRICK audio and GBA sync for FMS and STEPPER'
  (app/'config.json').write_text(json.dumps(meta,indent=2)+'\n')
  shutil.copyfile(app/'icon-on.png',app/'icon.png')
  for p in app.rglob('*.sh'):p.chmod(0o755);subprocess.run(['sh','-n',str(p)],check=True)
  shutil.copyfile(ROOT/'INSTALL.txt',stage/'README.txt')
  shutil.copyfile(ROOT/'tools/install.py',stage/'install_link4brick.py')
  manifest={'product':'LINK4BRICK','version':'1.0.1','installable':not args.host,'files':{str(p.relative_to(app)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(app.rglob('*')) if p.is_file()}}
  (app/'release.json').write_text(json.dumps(manifest,indent=2)+'\n')
  shutil.copyfile(ROOT/'THIRD_PARTY.md',stage/'THIRD_PARTY.txt');(stage/'LICENSES').mkdir()
  for p in [ROOT/'LICENSE',ROOT/'LICENSES/mGBA-MPL-2.0.txt',ROOT/'LICENSES/mGBA-inih.txt',ROOT/'LICENSES/Ableton-Link.md',ROOT/'LICENSES/Inter-OFL.txt']:
    shutil.copyfile(p,stage/'LICENSES'/p.name)
  shutil.copyfile(args.link/'modules/asio-standalone/asio/LICENSE_1_0.txt',stage/'LICENSES/Asio.txt')
  args.output.parent.mkdir(parents=True,exist_ok=True)
  with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(stage.rglob('*')):
      if p.is_file():z.write(p,p.relative_to(stage))
  with zipfile.ZipFile(args.output) as z:
    assert z.testzip() is None
    assert all(n.startswith(('Apps/LINK4BRICK/','LICENSES/')) or n in ['README.txt','THIRD_PARTY.txt','install_link4brick.py'] for n in z.namelist())
    assert not any(n.lower().endswith(('.gb','.gba','.sav','.srm','.log','.pak')) for n in z.namelist())
    assert json.loads(z.read('Apps/LINK4BRICK/config.json'))['label']=='LINK4BRICK'
    assert b'PROTOCOL=fms-gba\n' in z.read('Apps/LINK4BRICK/cable/config.txt')
    assert 'Apps/LINK4BRICK/enabled' not in z.namelist() and 'Apps/LINK4BRICK/launchers.list' not in z.namelist()
    assert 100000<len(z.read('Apps/LINK4BRICK/ui/font.bin'))<200000
    assert len(z.read('Apps/LINK4BRICK/ui/logo.rgba'))==25600
    assert z.read('Apps/LINK4BRICK/settings.txt') == b'LINK_AUDIO=on\n'
    for rel in ['run.sh','cable/run-ra.sh']:
      assert b'audio_latency = "65"' in z.read('Apps/LINK4BRICK/'+rel)
    assert b'Audio buffer' not in z.read('Apps/LINK4BRICK/bin/audiocast-settings')
    for n in bins:assert (z.getinfo('Apps/LINK4BRICK/bin/'+n).external_attr>>16)&0o111
  args.output.with_suffix(args.output.suffix+'.sha256').write_text(hashlib.sha256(args.output.read_bytes()).hexdigest()+'  '+args.output.name+'\n')
if not args.host:
  from install import load_package
  load_package(args.output)
print('PASS: ARM64 unless --host, ZIP integrity, one LINK4BRICK app, normal game launch, disabled install state, no ROMs/saves/logs/.pak')
