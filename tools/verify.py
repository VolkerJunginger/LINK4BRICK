"""Offline launcher tests and Linux ALSA/session integration; never executes SD code."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parent.parent


def command(args, ok=True, **kw):
    p = subprocess.run(args, capture_output=True, text=True, timeout=15, **kw)
    assert (p.returncode == 0) == ok, (p.returncode, p.stdout, p.stderr)
    return p.stdout


def setup(tmp, build=None):
    app = tmp / "Apps/LINK4BRICK"
    shutil.copytree(ROOT / "Apps/LINK4BRICK", app)
    # Small stand-ins test state selection without a graphics dependency.
    (app / "icon-on.png").write_bytes(b"on-image")
    (app / "icon-off.png").write_bytes(b"off-image")
    (app / "icon.png").write_bytes(b"off-image")
    runtime = tmp / "runtime"
    runtime.mkdir()
    for p in app.glob("*.sh"):
        p.write_text(p.read_text().replace("/tmp/", str(runtime) + "/"))
        p.chmod(0o755)
    (app / "bin").mkdir(exist_ok=True)
    helper = app / "bin/audiocast-cksum"
    if build:
        shutil.copyfile(build / "audiocast-cksum", helper)
    else:
        # Local macOS shell tests use a host stand-in. CI uses the actual
        # compiled helper and verifies it independently against POSIX cksum.
        helper.write_text('#!/bin/sh\n[ "$1" != --self-test ] || exit 0\n'
                          'exec /usr/bin/cksum <"$1"\n')
    helper.chmod(0o755)
    for name in ["linkaudio-send", "linkclock-send", "audiocast-session", "alsa-probe"]:
        p = app / "bin" / name
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(0o755)
    ra = tmp / "RetroArch"
    ra.mkdir()
    (ra / "retroarch.cfg").write_text('audio_device = ""\n')
    (ra / "ra64.trimui").write_text("#!/bin/sh\nexit 0\n")
    (ra / "ra64.trimui").chmod(0o755)
    return app, runtime


def launchers(fixtures=None, build=None):
    with tempfile.TemporaryDirectory(prefix="acb-launch-") as name:
        tmp = Path(name)
        app, runtime = setup(tmp, build)
        if fixtures:
            for p in Path(fixtures).glob("*/*/launch*.sh"):
                dest = tmp / p.relative_to(fixtures)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, dest)
        else:
            for system in ["GB", "GBA", "PS", "N64", "PPSSPP", "NDS", "OPENBOR"]:
                p = tmp / "Emus" / system / "launch.sh"
                p.parent.mkdir(parents=True)
                text = '#!/bin/sh\nRA_DIR=/mnt/SDCARD/RetroArch\nHOME=$RA_DIR/ $RA_DIR/ra64.trimui -v "$*"\n'
                if system in ["PPSSPP", "NDS", "OPENBOR"]:
                    text = '#!/bin/sh\ncd "$(dirname "$0")"\n./emulator "$*"\n'
                p.write_text(text)
        originals = {p: p.read_bytes() for p in tmp.glob("*/*/launch*.sh")
                     if p.parent != app}
        control = ["sh", str(app / "control.sh")]
        # Reproduce firmware with an unavailable system cksum. No production
        # operation may call it, including enable, restore and interrupted restore.
        unavailable = tmp / "unavailable"
        unavailable.mkdir()
        (unavailable / "cksum").write_text("#!/bin/sh\nexit 127\n")
        (unavailable / "cksum").chmod(0o755)
        old_path = os.environ["PATH"]
        os.environ["PATH"] = str(unavailable) + os.pathsep + old_path
        out = command(control + ["on"])
        assert "ON:" in out
        assert (app / "icon.png").read_bytes() == b"on-image"
        manifest = (app / "launchers.list").read_text().splitlines()
        eligible = {p: data for p, data in originals.items() if p.parent.name == "GBA"}
        assert len(manifest) == len(eligible), (len(manifest), len(eligible), out)
        for p, data in eligible.items():
            assert p.read_bytes() == (app / "wrapper.sh").read_bytes()
            assert Path(str(p)+".audiocast-original").read_bytes() == data
            assert Path(str(p)+".audiocast-run").exists()
        assert all(p.read_bytes() == data for p, data in originals.items() if p not in eligible)
        command(control + ["off"])
        assert all(p.read_bytes() == data for p, data in originals.items())
        assert not list(tmp.rglob("*.audiocast-*"))
        # Changed launcher must be preserved, disabled, and recoverable.
        command(control + ["on"])
        first = next(iter(eligible))
        first.write_text("#!/bin/sh\necho user edit\n")
        command(control + ["off"], ok=False)
        assert "user edit" in first.read_text()
        assert not (app / "enabled").exists()
        assert (app / "icon.png").read_bytes() == b"off-image"
        first.write_bytes(originals[first])
        command(control + ["off"])
        # Interrupted restore: some originals already restored and backups removed.
        command(control + ["on"])
        first.write_bytes(originals[first])
        Path(str(first)+".audiocast-original").unlink()
        command(control + ["off"])
        assert all(p.read_bytes() == data for p, data in originals.items())
        assert not list(runtime.iterdir())
        # Missing/failing/empty-output helpers must not activate any wrapper.
        helper = app / "bin/audiocast-cksum"
        saved = helper.read_bytes()
        helper.unlink()
        command(control + ["on"], ok=False)
        assert all(p.read_bytes() == data for p, data in originals.items())
        for body in ["exit 1", '[ "$1" != --self-test ] || exit 0\nexit 1',
                     "exit 0"]:
            helper.write_text("#!/bin/sh\n" + body + "\n")
            helper.chmod(0o755)
            command(control + ["on"], ok=False)
            assert not (app / "enabled").exists()
            assert (app / "icon.png").read_bytes() == b"off-image"
            assert all(p.read_bytes() == data for p, data in originals.items())
        helper.write_bytes(saved)
        helper.chmod(0o755)
        # A corrupted original and legacy blank checksums must never pass.
        command(control + ["on"])
        backup = Path(str(first)+".audiocast-original")
        backup.write_text("changed backup")
        command(control + ["off"], ok=False)
        assert backup.read_text() == "changed backup"
        assert first.read_bytes() == (app / "wrapper.sh").read_bytes()
        backup.write_bytes(originals[first])
        manifest_path = app / "launchers.list"
        valid_manifest = manifest_path.read_text()
        manifest_path.write_text("".join("|" + line.split("|",1)[1] + "\n"
                                        for line in valid_manifest.splitlines()))
        out = command(control + ["off"], ok=False)
        assert "Missing/invalid original checksum" in out and "OFF:" not in out
        assert backup.exists()
        manifest_path.write_text(valid_manifest)
        command(control + ["off"])
        assert all(p.read_bytes() == data for p, data in originals.items())
        assert not list(runtime.iterdir())
        # Exercise reversible controls directly; the StockUI entry now opens settings.
        old_log = tmp / "AudioCast-StockUI-v0.2b.log"
        old_log.write_text("previous release log\n")
        command(["sh", str(app / "control.sh"), "toggle"])
        assert (app / "enabled").exists()
        command(["sh", str(app / "control.sh"), "toggle"])
        assert not (app / "enabled").exists()
        assert (app / "icon.png").read_bytes() == b"off-image"
        assert old_log.read_text() == "previous release log\n"
        old_log.unlink()
        command(["sh", str(app / "control.sh"), "toggle"])
        command(["sh", str(app / "control.sh"), "toggle"])
        assert not list(tmp.rglob("*.log"))
        assert (app / "icon.png").read_bytes() == b"off-image"
        assert not (app / "icon.png.new").exists()
        # An unavailable image must not prevent enable or byte-exact restore.
        (app / "icon-on.png").unlink()
        command(control + ["on"])
        assert (app / "enabled").exists()
        command(control + ["off"])
        assert all(p.read_bytes() == data for p, data in originals.items())
        assert (app / "icon.png").read_bytes() == b"off-image"
        os.environ["PATH"] = old_path
        print(f"PASS: {len(eligible)} GBA launchers restored; {len(originals)-len(eligible)} others unchanged; absent system cksum, helper failures, corrupt/blank manifests, user edits and interrupted restore")


def checksums(build):
    helper = str(build / "audiocast-cksum")
    command([helper, "--self-test"])
    with tempfile.TemporaryDirectory(prefix="ac-checksum-") as tmp:
        tmp = Path(tmp)
        file = tmp / "input with spaces"
        vectors = [b"", b"abc", b"123456789", bytes(range(256)),
                   os.urandom(4097), os.urandom(65537)]
        for data in vectors:
            file.write_bytes(data)
            expected = subprocess.run(["/usr/bin/cksum"], input=data,
                                      capture_output=True, check=True).stdout.decode().strip()
            assert command([helper, str(file)]).strip() == expected
        for bad in [tmp / "missing", tmp]:
            assert command([helper, str(bad)], ok=False) == ""
    print("PASS: bundled POSIX checksum matches independent system implementation; read errors fail")


def session(build):
    with tempfile.TemporaryDirectory(prefix="acb-session-") as name:
        tmp = Path(name)
        fifo = tmp / "pcm.fifo"
        os.mkfifo(fifo)
        writer = tmp / "write.py"
        writer.write_text(
            "import sys\nwith open(sys.argv[1], 'wb', buffering=0) as f:\n"
            " for i in range(2048): f.write(b'\\x01\\x02\\x03\\x04'*256)\n")
        import sys
        args = [str(build / "audiocast-session"), "/bin/cat", str(fifo),
                sys.executable, str(writer), str(fifo)]
        # Fake sender exits or never reads: producer must still finish.
        for body in ["exit 0", "exec sleep 30"]:
            sender = tmp / "sender"
            sender.write_text("#!/bin/sh\n" + body + "\n")
            sender.chmod(0o755)
            args[1] = str(sender)
            out = command(args)
            assert "session ended: fifo_bytes=2097152" in out, out
            assert re.search(r"dropped_bytes=[1-9]", out), out
        # A real sender consumes the pipe and exits on EOF without SIGKILL.
        args[1] = str(build / "linkaudio-send")
        out = command(args)
        assert "48000Hz stereo S16_LE" in out
        assert "no_buffer=" in out and "commit_rejected=" in out
        assert "session ended: fifo_bytes=2097152" in out
        # Terminate a session while its process group waits.
        p = subprocess.Popen([str(build / "audiocast-session"), str(sender),
                              str(fifo), "/bin/sleep", "30"],
                             stdout=subprocess.PIPE, text=True)
        line = p.stdout.readline()
        ids = [int(v) for v in re.findall(r"(?:launcher|sender)_pid=(\d+)", line)]
        p.terminate()
        p.communicate(timeout=6)
        assert p.returncode == 128 + signal.SIGTERM
        assert all(not Path(f"/proc/{pid}").exists() for pid in ids)
        print("PASS: sender exit/stall never blocks producer; session signals reap owned children")


def runtime(build):
    with tempfile.TemporaryDirectory(prefix="acb-runtime-") as name:
        tmp = Path(name)
        app, temp = setup(tmp, build)
        for binary in ["audiocast-session", "linkaudio-send", "alsa-probe"]:
            shutil.copyfile(build / binary, app / "bin" / binary)
            (app / "bin" / binary).chmod(0o755)
        # Only substitute the physical codec with ALSA null for Linux CI.
        run = app / "run.sh"
        run.write_text(run.read_text().replace(
            'pcm.ac_speaker { type hw card "audiocodec" device 0 }',
            'pcm.ac_speaker { type null }'))
        emulator = tmp / "Emus/GBA/launch.sh"
        emulator.parent.mkdir(parents=True)
        emulator.write_text('#!/bin/sh\nRA_DIR="$TEST_RA"\n'
                            'HOME=$RA_DIR/ $RA_DIR/ra64.trimui "$@"\n')
        ra = tmp / "RetroArch/ra64.trimui"
        ra.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >"$AC_SD/args.txt"\n'
                      'test "$ALSA_CONFIG_PATH" = "$AC_RUN/alsa.conf" || exit 9\n'
                      '"$AC_APP/bin/alsa-probe" ac_game 6 || exit $?\n'
                      'touch "$AC_SD/playback-ok"\n')
        env = dict(os.environ, TEST_RA=str(ra.parent))
        original_config = (ra.parent / "retroarch.cfg").read_bytes()
        command(["sh", str(app / "control.sh"), "on"])
        command(["sh", str(emulator), "ROM with spaces.gba"], env=env)
        assert (tmp / "playback-ok").exists()
        assert not list(tmp.rglob("*.log"))
        assert 'log_to_file = "false"' in run.read_text()
        # Capture diagnostics in the test process only, after testing the
        # unmodified production launch above. No log file is used.
        quiet_run = run.read_text()
        run.write_text(quiet_run.replace("exec >/dev/null 2>&1", ":"))
        out = command(["sh", str(emulator), "ROM with spaces.gba"], env=env)
        assert "session ended: fifo_bytes=1152000" in out, out
        assert "PLAYBACK_OK" in out
        run.write_text(quiet_run)
        args = (tmp / "args.txt").read_text().splitlines()
        assert args[0] == "--config" and args[2] == "--appendconfig"
        assert args[-1] == "ROM with spaces.gba"
        assert (ra.parent / "retroarch.cfg").read_bytes() == original_config
        assert not list(temp.iterdir()), list(temp.iterdir())
        command(["sh", str(app / "control.sh"), "off"])
        gba = tmp / "Emus/GBA/launch_secondary.sh"
        gba.parent.mkdir(parents=True, exist_ok=True)
        gba.write_bytes(emulator.read_bytes())
        command(["sh", str(app / "control.sh"), "on"])
        command(["sh", str(gba), "Advance game with spaces.gba"], env=env)
        assert (tmp / "args.txt").read_text().splitlines()[-1] == "Advance game with spaces.gba"
        assert not list(temp.iterdir())
        assert (ra.parent / "retroarch.cfg").read_bytes() == original_config
        command(["sh", str(app / "control.sh"), "off"])
        # A rejected silent preflight must run the original script without
        # AudioCast's ALSA environment or appended config.
        (app / "bin/alsa-probe").write_text("#!/bin/sh\nexit 4\n")
        ra.write_text('#!/bin/sh\n'
                      'test -z "${ALSA_CONFIG_PATH:-}" || exit 9\n'
                      'printf "%s\\n" "$@" >"$AC_SD/fallback-args.txt"\n')
        command(["sh", str(app / "control.sh"), "on"])
        command(["sh", str(emulator), "Fallback.gba"], env=env)
        assert (tmp / "fallback-args.txt").read_text().splitlines() == ["Fallback.gba"]
        assert not list(temp.iterdir())
        command(["sh", str(app / "control.sh"), "off"])
        assert not list(tmp.rglob("*.log"))
        print("PASS: silent .gba wrapper -> original RetroArch path -> real ALSA plug/file -> FIFO -> sender; failed-preflight fallback")


def package(path):
    from install import load_package
    files = load_package(Path(path))
    assert files['settings.txt'][0] == b'LINK_AUDIO=on\n'
    for relative in ['run.sh', 'cable/run-ra.sh']:
        assert b'audio_latency = "65"' in files[relative][0]
    assert files['icon.png'][0] == files['icon-on.png'][0]
    assert files['icon-on.png'][0] != files['icon-off.png'][0]
    print("PASS: stable StockUI ZIP, complete manifest, ARM64 binaries, fixed 65 ms buffer")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--package")
    args = parser.parse_args()
    if args.package:
        package(args.package)
    else:
        build = args.build.resolve() if args.build else None
        if build:
            checksums(build)
        launchers(args.fixtures, build)
        if args.build:
            build = args.build.resolve()
            session(build)
            runtime(build)
