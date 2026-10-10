#!/usr/bin/env python3
"""Install LINK4BRICK v1.0.1 on a StockUI card, with a local undo journal."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import uuid
import zipfile

VERSION = '1.0.1'
APP = 'Apps/LINK4BRICK/'
MUTABLE = {'enabled', 'launchers.list', 'settings.txt', 'cable/config.txt', 'icon.png'}
RETIRED = ['cable/log.sh', 'cable/status.sh', 'cable/session-output.sh',
           'cable/show-launch-error.sh']
BINS = ['linkaudio-send','linkclock-send', 'audiocast-session', 'alsa-probe', 'audiocast-cksum',
        'audiocast-core-probe', 'audiocast-settings']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    parts = PurePosixPath(relative).parts
    if not parts or relative.startswith('/') or '\\' in relative or '..' in parts:
        raise ValueError('Unsafe path: ' + relative)
    target = root
    for part in parts:
        target = target / part
        if target.is_symlink():
            raise ValueError('Symlink refused: ' + str(target))
    if target.exists() and not target.is_file():
        raise ValueError('Not a regular file: ' + str(target))
    return target


def atomic_write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_package(package):
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip():
            raise ValueError('Duplicate entries or corrupt ZIP')
        if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError('Package is unexpectedly large')
        for item in archive.infolist():
            safe_path(Path('/nonexistent-link4brick-validation'), item.filename.rstrip('/'))
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Symlink in package')
        manifest = json.loads(archive.read(APP + 'release.json'))
        if manifest['product'] != 'LINK4BRICK' or manifest['version'] != VERSION or not manifest.get('installable', False):
            raise ValueError('Incorrect release manifest')
        files = {}
        actual = {n[len(APP):] for n in names if n.startswith(APP) and not n.endswith('/')}
        if actual != set(manifest['files']) | {'release.json'}:
            raise ValueError('Package manifest does not cover every app file')
        for relative, expected in manifest['files'].items():
            data = archive.read(APP + relative)
            if digest(data) != expected:
                raise ValueError('Checksum mismatch: ' + relative)
            mode = 0o755 if relative.endswith('.sh') or relative.startswith('bin/') else 0o644
            files[relative] = (data, mode)
        files['release.json'] = (archive.read(APP + 'release.json'), 0o644)
        for relative in ['bin/' + n for n in BINS] + ['cores/mgba-link_libretro.so']:
            data = files[relative][0]
            if data[:6] != b'\x7fELF\x02\x01' or int.from_bytes(data[18:20], 'little') != 183:
                raise ValueError('Not an ARM64 executable: ' + relative)
        config = json.loads(files['config.json'][0])
        if config['label'] != 'LINK4BRICK' or config['launch'] != 'launch.sh':
            raise ValueError('Incorrect StockUI app configuration')
        if any(n.endswith(('.log', '.pak', '.gb', '.gba', '.sav', '.srm')) for n in files):
            raise ValueError('Unexpected game, log or package data')
        if {'enabled', 'launchers.list'} & set(files):
            raise ValueError('Package contains installed launcher state')
        return files


def changes_for(card, files):
    if not (card / 'Emus/GBA').is_dir() or not (card / 'RetroArch').is_dir():
        raise ValueError('Expected StockUI Emus/GBA and RetroArch directories')
    legacy = card / 'Apps/AudioCast'
    if (legacy / 'enabled').exists() or (legacy / 'launchers.list').exists():
        raise ValueError('Turn the old AudioCast app OFF before installing LINK4BRICK')
    changes = {}
    for relative, (data, mode) in files.items():
        target = safe_path(card, APP + relative)
        if relative in MUTABLE and target.exists():
            continue
        if target.exists() and target.read_bytes() == data:
            continue
        changes[APP + relative] = (data, mode)
    for relative in RETIRED:
        target = safe_path(card, APP + relative)
        if target.exists():
            changes[APP + relative] = (None, 0o644)
    # Remove only our previous checker, preserving all other BrickTools entries.
    relative = 'Apps/BrickTools/menu.json'
    menu = safe_path(card, relative)
    if menu.exists():
        entries = json.loads(menu.read_text())
        if isinstance(entries, list):
            filtered = [entry for entry in entries
                        if not isinstance(entry, dict) or
                        entry.get('execute') != './scripts/audiocast_check.sh']
            if len(filtered) != len(entries):
                changes[relative] = ((json.dumps(filtered, indent=2) + '\n').encode(), 0o644)
                checker = 'Apps/BrickTools/scripts/audiocast_check.sh'
                if safe_path(card, checker).exists():
                    changes[checker] = (None, 0o755)
    return changes


def restore_entries(card, backup, entries):
    for entry in reversed(entries):
        path = safe_path(card, entry['path'])
        if entry['before'] is None:
            if path.exists():
                path.unlink()
        else:
            data = safe_path(backup, 'originals/' + entry['path']).read_bytes()
            if digest(data) != entry['before']:
                raise ValueError('Backup checksum mismatch: ' + entry['path'])
            atomic_write(path, data, entry['mode'])


def install(card, files, backup):
    changes = changes_for(card, files)
    if not changes:
        print('Already installed; settings and launcher backups preserved.')
        return None
    if backup == card or card in backup.parents:
        raise ValueError('Choose a backup folder on your computer, outside the SD card')
    backup.mkdir(parents=True, exist_ok=False)
    journal = {'product': 'LINK4BRICK', 'version': VERSION, 'card': str(card),
               'complete': False, 'files': []}
    receipt = backup / 'installation.json'
    # Save all originals before modifying anything on the card.
    for relative, (data, mode) in changes.items():
        path = safe_path(card, relative)
        before = path.read_bytes() if path.exists() else None
        if before is not None:
            atomic_write(safe_path(backup, 'originals/' + relative), before)
        journal['files'].append({'path': relative, 'before': digest(before) if before is not None else None,
                                 'after': digest(data) if data is not None else None,
                                 'mode': stat.S_IMODE(path.stat().st_mode) if path.exists() else mode})
    atomic_write(receipt, (json.dumps(journal, indent=2) + '\n').encode())
    try:
        for relative, (data, mode) in changes.items():
            path = safe_path(card, relative)
            if data is None:
                path.unlink()
            else:
                atomic_write(path, data, mode)
        for entry in journal['files']:
            path = safe_path(card, entry['path'])
            actual = digest(path.read_bytes()) if path.exists() else None
            if actual != entry['after']:
                raise ValueError('Installed verification failed: ' + entry['path'])
        journal['complete'] = True
        atomic_write(receipt, (json.dumps(journal, indent=2) + '\n').encode())
    except BaseException:
        restore_entries(card, backup, journal['files'])
        raise
    print('Installed LINK4BRICK v' + VERSION + '; settings and launcher backups preserved.')
    print('Undo journal: ' + str(receipt))
    print('Eject the card, reboot the Brick, then open LINK4BRICK settings.')
    return receipt


def undo(receipt, card):
    journal = json.loads(receipt.read_text())
    if journal.get('product') != 'LINK4BRICK' or journal['card'] != str(card):
        raise ValueError('Undo journal belongs to another card')
    entries = list(journal['files'])
    backup = receipt.parent
    # Verify all current files and all backups before changing anything.
    for entry in entries:
        path = safe_path(card, entry['path'])
        actual = digest(path.read_bytes()) if path.exists() else None
        if actual != entry['after']:
            relative = entry['path'][len(APP):] if entry['path'].startswith(APP) else ''
            if relative in MUTABLE and entry['before'] is None:
                continue
            raise ValueError('File changed since installation; preserving it: ' + entry['path'])
        if entry['before'] is not None:
            data = safe_path(backup, 'originals/' + entry['path']).read_bytes()
            if digest(data) != entry['before']:
                raise ValueError('Backup checksum mismatch: ' + entry['path'])
    # A fresh install must be switched OFF before its control tools are removed.
    if any(e['path'] == APP + 'control.sh' and e['before'] is None for e in entries):
        if (card / APP / 'enabled').exists() or (card / APP / 'launchers.list').exists():
            raise ValueError('Turn LINK4BRICK OFF before undoing a fresh installation')
    entries = [entry for entry in entries if not (entry['before'] is None
               and entry['path'].startswith(APP) and entry['path'][len(APP):] in MUTABLE
               and (digest(safe_path(card, entry['path']).read_bytes())
                    if safe_path(card, entry['path']).exists() else None) != entry['after'])]
    restore_entries(card, backup, entries)
    print('Update undone; original files restored and unrelated files preserved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--card', type=Path, default=Path('/Volumes/128GBRICK'))
    parser.add_argument('--package', type=Path)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--check', action='store_true', help='Validate only; do not write to the card')
    parser.add_argument('--undo', type=Path, help='Restore the installation.json journal')
    args = parser.parse_args()
    card = args.card.expanduser().resolve()
    if not card.is_dir():
        raise ValueError('SD card is not mounted: ' + str(card))
    if args.undo:
        undo(args.undo.expanduser().resolve(), card)
        return
    package = args.package or Path(__file__).resolve().parent / 'LINK4BRICK-StockUI-v1.0.1.zip'
    files = load_package(package)
    changes = changes_for(card, files)
    if args.check:
        print('PASS: verified release; ' + str(len(changes)) + ' file changes; settings and launchers preserved.')
        return
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
    backup = (args.backup or Path(__file__).resolve().parent / 'backups' / stamp).expanduser().resolve()
    install(card, files, backup)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print('Installation stopped: ' + str(error), file=sys.stderr)
        sys.exit(1)
