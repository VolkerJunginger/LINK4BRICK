"""Live Link tempo/phase without PCM input or an advertised audio channel."""
import os,socket,struct,subprocess,tempfile,time
from pathlib import Path
import sys
build=Path(sys.argv[1]).resolve()
with tempfile.TemporaryDirectory(prefix='l4b-clock-only-') as d:
    path=d+'/clock.sock';sock=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
    sock.bind(path);sock.settimeout(.5)
    peer=None
    if '--peer-first' in sys.argv[2:]:
        peer=subprocess.Popen([str(build/'link-audio-peer'),'--clock-only'],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        time.sleep(1.1)
    sender=subprocess.Popen([str(build/'linkclock-send')],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        env=dict(os.environ,AUDIOCAST_CLOCK_SOCKET=path))
    if peer is None:
        peer=subprocess.Popen([str(build/'link-audio-peer'),'--clock-only'],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    found=set();heartbeats=[]
    try:
        deadline=time.monotonic()+18
        while time.monotonic()<deadline and peer.poll() is None:
            try:packet=sock.recv(100)
            except socket.timeout:continue
            assert len(packet)==40,len(packet)
            magic,version,stamp,beat,tempo,peers,playing=struct.unpack('=IIqddII',packet)
            assert magic==0x41434c4b and version==1 and playing in (0,1)
            age=time.clock_gettime(time.CLOCK_MONOTONIC)*1e6-stamp
            assert 0<=age<500000,age
            if peers:found.add(round(tempo))
            heartbeats.append((stamp,beat,tempo,peers))
        out=peer.communicate(timeout=4)[0];assert peer.returncode==0,out
        assert {90,150}<=found,found
        # Compare the shared four-beat phase, allowing each client's local
        # beat number to differ by whole bars. Tempo matching alone cannot
        # establish that queued START reaches the peer's next "one".
        phase_errors=[];phase_tempos=set()
        for line in out.splitlines():
            if not line.startswith('PHASE '):continue
            _,stamp,beat,tempo=line.split();stamp=int(stamp);beat=float(beat);tempo=float(tempo)
            if stamp-heartbeats[0][0]<2000000:continue
            sample=min(heartbeats,key=lambda s:abs(s[0]-stamp))
            assert abs(sample[0]-stamp)<20000
            # Ignore the exact tempo-edit instant; the reference may already
            # have committed it before the remote process observes the change.
            if abs(sample[2]-tempo)>=.01:continue
            predicted=sample[1]+(stamp-sample[0])*sample[2]/60000000
            phase_error=((predicted-beat+2)%4)-2
            phase_errors.append(abs(phase_error)*60000000/tempo)
            phase_tempos.add(round(tempo))
        assert len(phase_errors)>=4,phase_errors
        assert {90,150}<=phase_tempos,phase_tempos
        assert max(phase_errors)<10000,phase_errors
        print('PASS: shared next-one phase versus Link Audio peer, max error %.1f us'%max(phase_errors))
        assert sender.poll() is None,'Closed stdin must not stop the clock'
        assert len(heartbeats)>1000,len(heartbeats)
        span=(heartbeats[-1][0]-heartbeats[0][0])/1e6
        assert 100<len(heartbeats)/span<500,len(heartbeats)/span
        sender.terminate();output=sender.communicate(timeout=5)[0]
        assert sender.returncode==0,output
        print(out.strip());print('PASS: independent timer, closed stdin, live 90/150 BPM, fresh phase snapshots, no audio channel, clean signal exit')
    finally:
        for child in [sender,peer]:
            if child.poll() is None:child.terminate();child.wait(timeout=4)
        sock.close()
    # Missing receiver and full datagram queues never block shutdown.
    for suffix in ['absent','full']:
        path=d+'/'+suffix+'.sock'
        receiver=None
        if suffix=='full':
            receiver=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM);receiver.bind(path)
        child=subprocess.Popen([str(build/'linkclock-send')],stdin=subprocess.DEVNULL,
            env=dict(os.environ,AUDIOCAST_CLOCK_SOCKET=path))
        time.sleep(.2);assert child.poll() is None
        child.terminate();assert child.wait(timeout=3)==0
        if receiver:receiver.close()
    child=subprocess.run([str(build/'linkclock-send')],stdin=subprocess.DEVNULL,
        env={k:v for k,v in os.environ.items() if k!='AUDIOCAST_CLOCK_SOCKET'},timeout=3)
    assert child.returncode==0
print('PASS: absent/full receiver nonblocking; sync OFF exits without opening Link')
