"""Exercise real menu actions, data settings, busy guard and icon restoration."""
import os,shutil,subprocess,tempfile,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;build=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='ac-settings-') as d:
    sd=Path(d);app=sd/'Apps/LINK4BRICK';shutil.copytree(root/'Apps/LINK4BRICK',app);(app/'bin').mkdir();(app/'cores').mkdir()
    for n in ['audiocast-cksum','audiocast-core-probe','audiocast-settings','linkaudio-send','linkclock-send','audiocast-session','alsa-probe']:shutil.copy(build/n,app/'bin'/n)
    (app/'cores/mgba-link_libretro.so').write_bytes(b'fixture')
    for state in ['on','off']:(app/('icon-'+state+'.png')).write_bytes(state.encode())
    (sd/'RetroArch').mkdir();(sd/'RetroArch/ra64.trimui').write_text('#!/bin/sh\nexit 0\n');(sd/'RetroArch/ra64.trimui').chmod(0o755)
    (sd/'Emus/GBA').mkdir(parents=True);(sd/'RetroArch/retroarch.cfg').write_text('')
    launcher=sd/'Emus/GBA/launch.sh';original=b'#!/bin/sh\nRA_DIR=/mnt/SDCARD/RetroArch\n$RA_DIR/ra64.trimui -L gambatte_gb_libretro.so "$*"\n';launcher.write_bytes(original)
    def cli(*args,ok=True):
        r=subprocess.run(args,cwd=app,capture_output=True,text=True);assert (r.returncode==0)==ok,r.stdout+r.stderr;return r.stdout.strip()
    menu=str(app/'bin/audiocast-settings');helper=['sh',str(app/'settings.sh')]
    assert cli(*helper,'audio-value')=='1'
    assert cli(*helper,'get-advance')=='0'
    cli(menu,'--render',str(sd/'menu.ppm'));assert (sd/'menu.ppm').read_bytes().startswith(b'P6\n1024 768\n')
    cli(menu,'--change','0');assert (app/'enabled').exists() and (app/'icon.png').read_bytes()==b'on'
    cli(menu,'--change','1');assert cli(*helper,'audio-value')=='0'
    cli(menu,'--change','2');assert cli(*helper,'get-clock')=='fms-gba'
    for advance in range(5,70,5):
        cli(menu,'--change','4');assert cli(*helper,'get-advance')==str(advance)
    assert (app/'cable/config.txt').read_text()=='PROTOCOL=fms-gba\nPPQN=24\nOFFSET_US=65000\n'
    # Re-loading the actual menu and changing mode, PPQ or audio retains advance.
    cli(menu,'--change','3',ok=False)
    cli(menu,'--change','2');assert cli(*helper,'get-clock')=='stepper-gba' and cli(*helper,'get-ppqn')=='24'
    assert cli(*helper,'get-advance')=='65'
    for ppq in [48,96,4,6,12,24]:
        cli(menu,'--change','3');assert cli(*helper,'get-ppqn')==str(ppq)
        assert cli(*helper,'get-advance')=='65'
        cli(menu,'--render',str(sd/'stepper-menu.ppm'))
    for bad in ['2','8','16','192','$(touch HACKED)']:
        before=(app/'cable/config.txt').read_bytes();cli(*helper,'set-ppqn',bad,ok=False);assert (app/'cable/config.txt').read_bytes()==before
    cli(menu,'--change','2');assert cli(*helper,'get-clock')=='fms-clock' and cli(*helper,'get-ppqn')=='2'
    for ppq in [3,4,6,8,1,2]:
        cli(menu,'--change','3');assert cli(*helper,'get-ppqn')==str(ppq)
    cli(*helper,'set-ppqn','24',ok=False)
    cli(menu,'--change','2');assert cli(*helper,'get-clock')=='off'
    cli(*helper,'set-advance','150');cli(menu,'--change','4');assert cli(*helper,'get-advance')=='150'
    cli(*helper,'set-advance','0');cli(menu,'--change','4','-1');assert cli(*helper,'get-advance')=='0'
    cli(*helper,'set-advance','65');cli(menu,'--change','4','-1');assert cli(*helper,'get-advance')=='60'
    for bad in ['-5','1','64','151','155','065','+65','65.0','999999999999999999999','$(touch HACKED)']:
        before=(app/'cable/config.txt').read_bytes()
        cli(*helper,'set-advance',bad,ok=False);assert (app/'cable/config.txt').read_bytes()==before
    for bad in ['-5000','64000','150001','065000','999999999999999999999','$(touch HACKED)']:
        (app/'cable/config.txt').write_text('PROTOCOL=fms-gba\nPPQN=24\nOFFSET_US='+bad+'\n')
        assert cli(*helper,'get-advance')=='0' and not (app/'HACKED').exists()
    cli(*helper,'set-advance','65');cli(menu,'--render',str(sd/'advance-menu.ppm'))
    assert cli(*helper,'get-advance')=='65'
    cli(*helper,'set-clock','off');assert cli(*helper,'get-advance')=='65'
    cli(menu,'--change','0');assert launcher.read_bytes()==original and (app/'icon.png').read_bytes()==b'off'
    (app/'settings.txt').write_text('LINK_AUDIO=$(touch HACKED)\nBAD=1\n');assert cli(*helper,'audio-value')=='1' and not (app/'HACKED').exists()
    # Removed buffer actions cannot alter old settings or execute data.
    for value in ['0','60','65','150','$(touch HACKED)']:
        (app/'settings.txt').write_text('LINK_AUDIO=off\nAUDIO_BUFFER_MS='+value+'\n')
        before=(app/'settings.txt').read_bytes()
        cli(*helper,'set-buffer','65',ok=False);cli(*helper,'get-buffer',ok=False)
        cli(menu,'--change','5',ok=False)
        assert (app/'settings.txt').read_bytes()==before and cli(*helper,'get-audio')=='off'
        cli(*helper,'set-audio','on');assert (app/'settings.txt').read_text()=='LINK_AUDIO=on\n'
    cli(menu,'--change','2','-1');assert cli(*helper,'get-clock')=='fms-clock'
    for bad in ['dmgo-gb','gba-clock','gb-serial']:
        cli(*helper,'set-clock',bad,ok=False)
    (app/'settings.txt').write_text('LINK_AUDIO=off\nAUDIO_BUFFER_MS=$(touch HACKED)\n');assert cli(*helper,'get-audio')=='off' and not (app/'HACKED').exists()
    (app/'settings.txt').unlink();(app/'settings.txt').symlink_to(sd/'sentinel');(sd/'sentinel').write_text('unchanged');cli(*helper,'set-audio','off',ok=False);assert (sd/'sentinel').read_text()=='unchanged'
    (app/'settings.txt').unlink()
    config=app/'cable/config.txt';config.unlink();config.symlink_to(sd/'sentinel')
    cli(*helper,'set-advance','65',ok=False);assert (sd/'sentinel').read_text()=='unchanged';config.unlink()
    busy=Path('/tmp/audiocast-v0.2b');assert not busy.exists();busy.mkdir()
    try:
        cli(menu,'--change','1',ok=False);assert not (app/'settings.txt').exists()
        cli(*helper,'set-clock','stepper-gba',ok=False)
        cli(*helper,'set-advance','65',ok=False)

    finally:busy.rmdir()
    assert not list(sd.rglob('*.log')) and not list(app.glob('*.tmp.*'))
print('PASS: menu actions, 0-150 ms sync advance in 5 ms steps, persistence across modes/PPQ/audio, bounded values, GBA launcher and dynamic icons restored, data not executed, symlink/busy protection, no logs')
