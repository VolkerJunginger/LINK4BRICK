"""Actual clock-only launch -> direct ALSA speaker, plus owned-process cleanup."""
import json,os,shutil,signal,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from verify import setup,command
build=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='l4b-direct-speaker-') as temporary:
    sd=Path(temporary)/'SD';sd.mkdir()
    app,runtime=setup(sd,build)
    for binary in ['linkaudio-send','linkclock-send','audiocast-session','alsa-probe']:
        shutil.copyfile(build/binary,app/'bin'/binary);(app/'bin'/binary).chmod(0o755)
    (app/'cores').mkdir();(app/'cores/mgba-link_libretro.so').write_bytes(b'loader stand-in')
    probe=app/'bin/audiocast-core-probe';probe.write_text('#!/bin/sh\nexit 0\n');probe.chmod(0o755)
    run=app/'run.sh';run.write_text(run.read_text().replace(
        'pcm.ac_speaker { type hw card "audiocodec" device 0 }','pcm.ac_speaker { type null }'))
    (app/'settings.txt').write_text('LINK_AUDIO=off\n')
    (app/'cable/config.txt').write_text('PROTOCOL=fms-gba\nPPQN=24\nOFFSET_US=0\n')
    game=sd/'Emus/GBA/launch.sh';game.parent.mkdir(parents=True)
    game.write_text('#!/bin/sh\nRA_DIR="$TEST_RA"\n$RA_DIR/ra64.trimui -L "$TEST_CORE" "$@"\n')
    # Use an unspaced RA_DIR alias so the stock invocation remains valid.
    alias=Path(temporary)/'RetroArch';alias.symlink_to(sd/'RetroArch',target_is_directory=True)
    ra=sd/'RetroArch/ra64.trimui'
    ra.write_text('''#!/usr/bin/env python3
import os,socket,struct,subprocess,sys
from pathlib import Path
run=Path(os.environ['AC_RUN']);app=Path(os.environ['AC_APP'])
assert not (run.parent/'audiocast.fifo').exists()
alsa=(run/'alsa.conf').read_text()
assert 'type file' not in alsa and 'ac_tee' not in alsa
assert 'slave { pcm "ac_speaker" format S16_LE rate 48000 channels 2 }' in alsa
assert os.environ['ALSA_CONFIG_PATH']==str(run/'alsa.conf')
assert 'audio_latency = "65"' in (run/'override.cfg').read_text()
clock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);clock.bind(os.environ['AUDIOCAST_CLOCK_SOCKET']);clock.settimeout(2)
for _ in range(12):
 data=clock.recv(100);assert len(data)==40
 assert struct.unpack('=IIqddII',data)[0]==0x41434c4b
clock.close()
result=subprocess.run([str(app/'bin/alsa-probe'),'ac_game','1'],capture_output=True,text=True)
assert result.returncode==0,result.stderr
assert 'frames=48000' in result.stdout,result.stdout
Path(os.environ['AUDIOCAST_CLOCK_SOCKET']+'.ready').write_bytes(b'1')
Path(os.environ['AC_SD'],'direct-speaker-ok').write_bytes(b'1')
''');ra.chmod(0o755)
    env=dict(os.environ,TEST_RA=str(alias),TEST_CORE=str(sd/'RetroArch/cores/mgba_libretro.so'))
    control=['sh',str(app/'control.sh')]
    original=game.read_bytes();main_config=(sd/'RetroArch/retroarch.cfg').read_bytes()
    command(control+['on']);command(['sh',str(game),'FMS with spaces.gba'],env=env)
    assert (sd/'direct-speaker-ok').exists()
    assert not list(runtime.iterdir()),list(runtime.iterdir())
    assert not list(sd.rglob('*.log'))
    assert (sd/'RetroArch/retroarch.cfg').read_bytes()==main_config
    command(control+['off']);assert game.read_bytes()==original
print('PASS: normal launcher, direct real ALSA playback, live clock without FIFO/tee/relay, no logs, cleanup and restoration')

with tempfile.TemporaryDirectory(prefix='l4b-clock-supervisor-') as temporary:
    root=Path(temporary)
    clock=root/'clock.py';game=root/'game.py'
    clock.write_text('''#!/usr/bin/env python3
import os,time
from pathlib import Path
Path(os.environ['CLOCK_PID']).write_text(str(os.getpid()))
assert os.read(0,1)==b''
while True:time.sleep(.05)
''');clock.chmod(0o755)
    game.write_text('''#!/usr/bin/env python3
import os,subprocess,sys,time
from pathlib import Path
child=subprocess.Popen(['sleep','30'])
Path(os.environ['GAME_PIDS']).write_text(str(os.getpid())+' '+str(child.pid))
time.sleep(float(os.environ.get('GAME_TIME','30')))
sys.exit(int(os.environ.get('GAME_EXIT','0')))
''');game.chmod(0o755)
    env=dict(os.environ,CLOCK_PID=str(root/'clock.pid'),GAME_PIDS=str(root/'game.pid'))
    def alive(pid):
        p=Path('/proc')/str(pid)/'stat'
        return p.exists() and p.read_text().split()[2]!='Z'
    sentinel=subprocess.Popen(['sleep','30'])
    try:
        for interrupted in [False,True]:
            for p in [root/'clock.pid',root/'game.pid']:p.unlink(missing_ok=True)
            process=subprocess.Popen([str(build/'audiocast-session'),str(clock),'--clock-only',str(game)],
                env=dict(env,GAME_TIME='30' if interrupted else '.1',GAME_EXIT='23'))
            deadline=time.monotonic()+3
            while not all((root/n).exists() for n in ['clock.pid','game.pid']):
                assert time.monotonic()<deadline;time.sleep(.01)
            pids=[int((root/'clock.pid').read_text())]+[int(x) for x in (root/'game.pid').read_text().split()]
            if interrupted:process.terminate()
            assert process.wait(timeout=5)==(143 if interrupted else 23)
            assert not any(alive(pid) for pid in pids),pids
            assert sentinel.poll() is None
        # An exited clock must not stop speaker/game playback.
        result=subprocess.run([str(build/'audiocast-session'),'/bin/true','--clock-only','/bin/sh','-c','sleep .2; exit 7'],timeout=3)
        assert result.returncode==7
    finally:sentinel.terminate();sentinel.wait(timeout=3)
print('PASS: status propagation, closed clock stdin, signal cleanup of owned descendants, unrelated process intact, clock failure leaves game running')
