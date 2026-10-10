"""Exercise normal-launcher selection/fallback without running card binaries."""
from pathlib import Path
import json,os,shutil,subprocess,tempfile
ROOT=Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='ac-virtual-cable-') as t:
    sd=Path(t)/'SD with spaces';app=sd/'Apps/LINK4BRICK';runtime=Path(t)/'runtime'
    shutil.copytree(ROOT/'Apps/LINK4BRICK',app);runtime.mkdir()
    (app/'bin').mkdir();(app/'cores').mkdir()
    (app/'cores/mgba-link_libretro.so').write_bytes(b'core stand-in')
    probe=app/'bin/audiocast-core-probe'
    probe.write_text('#!/bin/sh\nexit "${PROBE_RESULT:-0}"\n');probe.chmod(0o755)
    ra=sd/'RetroArch/ra64.trimui';ra.parent.mkdir()
    ra.write_text('''#!/usr/bin/env python3
import os,sys,json
from pathlib import Path
record=Path(os.environ['CAPTURE'])
calls=json.loads(record.read_text()) if record.exists() else []
calls.append({'args':sys.argv[1:],'clock':os.environ.get('AUDIOCAST_CLOCK_SOCKET'),'protocol':os.environ.get('AUDIOCAST_LINK_PROTOCOL'),'advance':os.environ.get('AUDIOCAST_OFFSET_US'),'config':Path(sys.argv[sys.argv.index('--appendconfig')+1]).read_text()})
record.write_text(json.dumps(calls))
core=sys.argv[sys.argv.index('-L')+1]
if core.endswith('mgba-link_libretro.so'):
 if os.environ.get('SIM_READY')=='1':Path(os.environ['AUDIOCAST_CLOCK_SOCKET']+'.ready').write_bytes(b'1')
 sys.exit(int(os.environ.get('PRIVATE_RESULT','0')))
''');ra.chmod(0o755)
    capture=Path(t)/'calls.json';config=app/'cable/config.txt'
    env=dict(os.environ,AC_APP=str(app),AC_SD=str(sd),AC_RUN=str(runtime),CAPTURE=str(capture))
    stock=str(sd/'RetroArch/.retroarch/cores/mgba_libretro.so')
    entry=Path(t)/'normal-game.sh'
    entry.write_text('. "$AC_APP/cable/env.sh"\nexec /bin/sh "$AC_APP/run-ra.sh" "$@"\n')
    def run(settings,args=None,**extra):
        config.write_text(settings);capture.unlink(missing_ok=True)
        (runtime/'clock.sock.ready').unlink(missing_ok=True)
        (runtime/'override.cfg').write_text('audio_device = "ac_game"\naudio_latency = "65"\nconfig_save_on_exit = "false"\n')
        (runtime/'ra.cfg').write_text('untouched copied config\n')
        result=subprocess.run(['sh',str(entry)]+(args or ['-v','-L',stock,'Unrelated music program.gba']),env=dict(env,**extra),capture_output=True)
        assert result.returncode==0,result
        return json.loads(capture.read_text())
    active='PROTOCOL=fms-gba\nPPQN=24\nOFFSET_US=0\n'
    calls=run('PROTOCOL=off\n');assert len(calls)==1 and calls[0]['args'][-3:]==['-L',stock,'Unrelated music program.gba'] and calls[0]['clock'] is None
    calls=run(active,SIM_READY='1')
    assert len(calls)==1 and calls[0]['args'][-3:]==['-L',str(app/'cores/mgba-link_libretro.so'),'Unrelated music program.gba']
    assert 'video_threaded = "false"' in calls[0]['config'] and 'libretro_log_level = "2"' in calls[0]['config']
    assert calls[0]['clock']==str(runtime/'clock.sock') and calls[0]['protocol']=='fms-gba'
    for audio in ['on','off']:
        (app/'settings.txt').write_text(f'LINK_AUDIO={audio}\n')
        for protocol,ppq in [('fms-gba',24),('fms-clock',2),('stepper-gba',48)]:
            for advance in [0,5,60,65,150]:
                calls=run(f'PROTOCOL={protocol}\nPPQN={ppq}\nOFFSET_US={advance*1000}\n',SIM_READY='1')
                assert len(calls)==1 and calls[0]['advance']==str(advance*1000)
                assert 'audio_latency = "65"' in calls[0]['config']
    for rate in [1,2,3,4,6,8]:
        calls=run(f'PROTOCOL=fms-clock\nPPQN={rate}\nOFFSET_US=0\n',SIM_READY='1')
        assert len(calls)==1 and calls[0]['protocol']=='fms-clock'
    for rate in [12,24,48,96]:
        calls=run(f'PROTOCOL=fms-clock\nPPQN={rate}\nOFFSET_US=0\n')
        assert calls[0]['clock'] is None
    for rate in [4,6,12,24,48,96]:
        calls=run(f'PROTOCOL=stepper-gba\nPPQN={rate}\nOFFSET_US=0\n',SIM_READY='1')
        assert len(calls)==1 and calls[0]['protocol']=='stepper-gba' and calls[0]['args'][-2]==str(app/'cores/mgba-link_libretro.so')
    for rate in [2,8,16,192]:
        calls=run(f'PROTOCOL=stepper-gba\nPPQN={rate}\nOFFSET_US=0\n')
        assert calls[0]['clock'] is None and calls[0]['args'][-2]==stock
    calls=run('PROTOCOL=fms-gba\nPPQN=24\nOFFSET_US=0\n',SIM_READY='1')
    assert len(calls)==1 and calls[0]['protocol']=='fms-gba' and calls[0]['clock']==str(runtime/'clock.sock')
    gb=str(sd/'RetroArch/.retroarch/cores/gambatte_gb_libretro.so')
    calls=run('PROTOCOL=dmgo-gb\nPPQN=16\nOFFSET_US=0\n',['-L',gb,'DMGo.gb'])
    assert len(calls)==1 and calls[0]['args'][-2]==gb and calls[0]['clock'] is None
    calls=run(active,['-L',gb,'Ordinary.gb'])
    assert calls[0]['args'][-2]==gb and calls[0]['clock'] is None
    for value in ['0','60','65','150','$(touch attacked)']:
        (app/'settings.txt').write_text(f'LINK_AUDIO=off\nAUDIO_BUFFER_MS={value}\n')
        calls=run(active,SIM_READY='1')
        assert 'audio_latency = "65"' in calls[0]['config']
    (app/'settings.txt').write_text('AUDIO_BUFFER_MS=64\n')
    calls=run(active,SIM_READY='1');assert 'audio_latency = "65"' in calls[0]['config']
    # Failures before any frame must fall back, including frontend exit code 0.
    for code in ['0','1','139']:
        calls=run(active,PRIVATE_RESULT=code)
        assert calls[1]['config']=='audio_device = "ac_game"\naudio_latency = "65"\nconfig_save_on_exit = "false"\n'
        assert len(calls)==2 and calls[1]['args'][-3:]==['-L',stock,'Unrelated music program.gba'] and calls[1]['clock'] is None
    for settings in ['PROTOCOL=gb-serial\n','PROTOCOL=$(touch attacked)\n','PROTOCOL=gba-clock\nPPQN=24\n','PROTOCOL=fms-gba\nPPQN=2\n','PROTOCOL=gba-clock\nOFFSET_US=999999999999999999999\n']:
        calls=run(settings);assert len(calls)==1 and calls[0]['clock'] is None and calls[0]['args'][-2]==stock
    calls=run(active,PROBE_RESULT='3');assert len(calls)==1 and calls[0]['clock'] is None
    other=str(sd/'RetroArch/.retroarch/cores/gpsp_libretro.so')
    calls=run(active,['--verbose','-L',other,'FMS.gba']);assert len(calls)==1 and calls[0]['args'][-2]==other and calls[0]['clock'] is None
    # The integration chooses by emulator, not FMS filename; ordinary flags and
    # spaced paths survive rotation of the shell positional arguments.
    calls=run(active,['--verbose','-L',stock,'-s','Save directory','Other.gba'],SIM_READY='1')
    assert calls[0]['args'][4:]==['--verbose','-L',str(app/'cores/mgba-link_libretro.so'),'-s','Save directory','Other.gba']
    assert (runtime/'ra.cfg').read_text()=='untouched copied config\n'
    assert not list(sd.rglob('*.log')) and not (Path.cwd()/'attacked').exists()
print('PASS: normal game entry, ROM-independent core selection, clock configuration, API-probe refusal, first-frame failure fallback (including exit 0), other cores unchanged, spaced arguments, no file logs')
