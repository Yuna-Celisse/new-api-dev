#!/usr/bin/env python3
"""Install a published, checksummed development image without registry credentials."""
import datetime
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request

BASE = Path('/opt/new-api')
REPO = 'Yuna-Celisse/new-api-dev'
IMAGE = 'ghcr.io/yuna-celisse/new-api'


def request(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'new-api-dev-updater', 'Accept': 'application/vnd.github+json' if 'api.github.com' in url else '*/*'})
    return urllib.request.urlopen(req, timeout=120)


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def compose(*args):
    run('docker', 'compose', '--env-file', 'image.env', '-f', 'compose.yaml', *args, cwd=BASE)


def healthy():
    for _ in range(90):
        try:
            with request('http://127.0.0.1:8091/api/status') as res:
                if json.load(res).get('success') is True:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def main():
    os.umask(0o077)
    BASE.mkdir(exist_ok=True)
    lock = (BASE / '.update.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with request(f'https://api.github.com/repos/{REPO}/releases?per_page=30') as res:
        releases = json.load(res)
    candidates = [r for r in releases if not r['draft'] and re.fullmatch(r'dev-[0-9a-f]{40}', r['tag_name'])]
    if not candidates:
        raise RuntimeError('No completed development image release is available yet')
    release = max(candidates, key=lambda r: r['published_at'])
    revision = release['tag_name'][4:]
    target = f'{IMAGE}:dev-{revision}'
    current_file = BASE / 'image.env'
    current = current_file.read_text() if current_file.exists() else ''
    if current.strip() == f'NEW_API_IMAGE={target}' and healthy():
        print('Already running upstream', revision)
        return
    assets = {a['name']: a['browser_download_url'] for a in release['assets']}
    names = ('SHA256SUMS', 'revision.txt', 'new-api-dev.tar.gz')
    if not all(n in assets for n in names):
        raise RuntimeError('Incomplete image release')
    download = BASE / 'downloads'
    download.mkdir(exist_ok=True)
    try:
        for name in names:
            with request(assets[name]) as res, (download / name).open('wb') as out:
                shutil.copyfileobj(res, out, 1024 * 1024)
        checksums = {}
        for line in (download / 'SHA256SUMS').read_text().splitlines():
            digest, filename = line.split(maxsplit=1)
            checksums[filename.strip().lstrip('*')] = digest
        for name in names[1:]:
            h = hashlib.sha256()
            with (download / name).open('rb') as src:
                for block in iter(lambda: src.read(1024 * 1024), b''):
                    h.update(block)
            if h.hexdigest() != checksums.get(name):
                raise RuntimeError(f'Checksum mismatch: {name}')
        if (download / 'revision.txt').read_text().strip() != revision:
            raise RuntimeError('Release revision mismatch')
        with gzip.open(download / 'new-api-dev.tar.gz', 'rb') as archive:
            proc = subprocess.Popen(['docker', 'load'], stdin=subprocess.PIPE)
            try:
                shutil.copyfileobj(archive, proc.stdin, 1024 * 1024)
            finally:
                proc.stdin.close()
            if proc.wait() != 0:
                raise RuntimeError('docker load failed')
        label = subprocess.check_output(['docker', 'image', 'inspect', target, '--format', '{{index .Config.Labels "org.opencontainers.image.revision"}}'], text=True).strip()
        if label != revision:
            raise RuntimeError('Image revision label mismatch')
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup = BASE / 'backups' / f'new-api-{timestamp}'
        backup.mkdir(parents=True)
        if current:
            compose('stop')
        with tarfile.open(backup / 'data.tar.gz', 'w:gz') as archive:
            archive.add(BASE / 'data', arcname='data')
        (backup / 'image.env').write_text(current)
        try:
            pending = BASE / 'image.env.tmp'
            pending.write_text(f'NEW_API_IMAGE={target}\n')
            pending.replace(current_file)
            compose('up', '-d', '--pull', 'never')
            if not healthy():
                raise RuntimeError('New image failed startup health check')
        except BaseException:
            compose('stop')
            (BASE / 'data').rename(BASE / f'data-failed-{timestamp}')
            with tarfile.open(backup / 'data.tar.gz') as archive:
                archive.extractall(BASE, filter='data')
            current_file.write_text(current)
            if current:
                compose('up', '-d', '--pull', 'never')
                if not healthy():
                    raise RuntimeError('Previous image also failed health check after rollback')
            raise
        print('Healthy deployment of upstream', revision, flush=True)
        # Keep seven stopped-database snapshots; leave AxonHub backups untouched.
        snapshots = sorted((BASE / 'backups').glob('new-api-*'))
        for old in snapshots[:-7]:
            shutil.rmtree(old)
    finally:
        for name in names:
            (download / name).unlink(missing_ok=True)


if __name__ == '__main__':
    main()
