#!/usr/bin/env python3
"""Plan, then optionally add/commit/push data in independently capped batches."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GIT_CONFIG = ['-c', 'gc.auto=0', '-c', 'maintenance.auto=false', '-c', 'core.compression=9',
              '-c', 'pack.window=0', '-c', 'pack.threads=1', '-c', 'pack.compression=6', '-c', 'pack.useSparse=false']


def git(*args, input=None):
    return subprocess.check_output(['git', *GIT_CONFIG, *args], cwd=ROOT, input=input)


def partition(files, target, first_reserve=0):
    batch, size = [], 0
    capacity = target - first_reserve
    if capacity <= 0:
        raise ValueError('Unpublished history already consumes the batch budget; push it first.')
    for path, length in files:
        if length > target:
            raise ValueError(f'File exceeds batch capacity: {path} ({length} bytes)')
        if batch and size + length > capacity:
            yield batch, size
            batch, size, capacity = [], 0, target
        if not batch and length > capacity:
            raise ValueError('Existing unpublished commit must be pushed separately before adding data.')
        batch.append((path, length))
        size += length
    if batch:
        yield batch, size


def pending_files():
    paths = set()
    for args in [('ls-files', '--others', '--exclude-standard', '-z', '--', 'data/'),
                 ('diff', '--name-only', '--diff-filter=ACM', '-z', '--', 'data/')]:
        paths.update(os.fsdecode(p) for p in git(*args).split(b'\0') if p)
    return sorted((path, (ROOT / path).stat().st_size) for path in paths)


def remote_tip(remote, branch):
    result = git('ls-remote', '--heads', remote, f'refs/heads/{branch}').decode().split()
    return result[0] if result else None


def outgoing_objects(base):
    args = ['rev-list', '--objects', 'HEAD'] + (['^' + base] if base else [])
    objects = [line.split(b' ', 1)[0] for line in git(*args).splitlines()]
    if not objects:
        return 0
    rows = git('cat-file', '--batch-check=%(objectsize)', input=b'\n'.join(objects) + b'\n')
    return sum(int(row) for row in rows.splitlines())


def pack_bytes(base):
    revisions = b'HEAD\n' + (('^' + base + '\n').encode() if base else b'')
    # Stream to a counter: never materialize a second 1 GB pack on this disk.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(['git', *GIT_CONFIG, 'pack-objects', '--stdout', '--revs',
                                    '--no-reuse-delta', '--delta-base-offset', '--quiet'], cwd=ROOT,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
        process.stdin.write(revisions)
        process.stdin.close()
        length = 0
        while chunk := process.stdout.read(1024 * 1024):
            length += len(chunk)
        process.stdout.close()
        if process.wait():
            errors.seek(0)
            raise RuntimeError(errors.read().decode(errors='replace'))
        return length


def check_branch(base):
    if base:
        try:
            git('cat-file', '-e', base + '^{commit}')
        except subprocess.CalledProcessError:
            raise RuntimeError('Remote commit is not local. Fetch the remote before running this script.')
        git('merge-base', '--is-ancestor', base, 'HEAD')


def publish(remote, branch, base, limit, staged_bytes, files):
    actual = pack_bytes(base)
    if actual > limit:
        raise RuntimeError(f'Push refused: pack {actual} bytes exceeds {limit}. Commit remains local.')
    commit = git('rev-parse', 'HEAD').decode().strip()
    print(f'Push {commit[:10]}: {actual:,} pack bytes; {staged_bytes:,} added bytes; {files} files', flush=True)
    subprocess.run(['git', *GIT_CONFIG, 'push', '--porcelain', '--no-follow-tags', '--no-thin', remote,
                    f'HEAD:refs/heads/{branch}'], cwd=ROOT, check=True)
    if remote_tip(remote, branch) != commit:
        raise RuntimeError('Remote tip did not match the pushed commit. Stopping.')
    record = {'time': datetime.now(timezone.utc).isoformat(), 'commit': commit, 'remote': remote,
              'branch': branch, 'files': files, 'addedBytes': staged_bytes,
              'packBytes': actual, 'limitBytes': limit}
    git_dir = Path(git('rev-parse', '--absolute-git-dir').decode().strip())
    with (git_dir / 'data-push-batches.jsonl').open('a') as stream:
        stream.write(json.dumps(record) + '\n')
    return commit


def compact_if_room():
    objects = Path(git('rev-parse', '--git-path', 'objects').decode().strip())
    if not objects.is_absolute():
        objects = ROOT / objects
    size = sum(p.stat().st_size for p in objects.rglob('*') if p.is_file())
    # Repack only when both the existing objects and the temporary pack fit.
    if size > 100_000_000 and shutil.disk_usage(ROOT).free > size * 1.1 + 256 * 1024**2:
        subprocess.run(['git', '-c', 'gc.auto=0', '-c', 'pack.threads=2', '-c', 'pack.windowMemory=64m',
                        'repack', '-d'], cwd=ROOT, check=True)


@contextmanager
def sync_lock():
    # The downloader uses the same OS lock. Hold it throughout the snapshot/push.
    import fcntl
    with (ROOT / 'data' / '.sync.lock').open('a+b') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Downloader is active. Stop it cleanly before pushing data.')
        yield


def main(args):
    if git('diff', '--cached', '--name-only', '-z'):
        raise RuntimeError('Index already contains staged changes; preserving it unchanged.')
    if git('ls-files', '-u'):
        raise RuntimeError('Resolve merge conflicts before publishing.')
    branch = git('symbolic-ref', '--short', 'HEAD').decode().strip()
    if args.branch and args.branch != branch:
        raise RuntimeError('Target branch must match the checked-out branch.')
    base = remote_tip(args.remote, branch)
    check_branch(base)
    reserve = outgoing_objects(base)
    if reserve > args.limit:
        raise RuntimeError(f'Existing unpublished history is {reserve:,} raw bytes, exceeding the limit; no staging or pushing performed.')
    files = pending_files()
    oversized = [p for p, n in files if n > 100_000_000]
    if oversized:
        raise RuntimeError('Files over the per-file safety limit: ' + ', '.join(oversized))
    target = args.limit * 95 // 100
    separate_pending = bool(reserve and (reserve > target // 2 or (files and files[0][1] > target - reserve)))
    batches = list(partition(files, target, 0 if separate_pending else reserve))
    print(json.dumps({'limitBytes': args.limit, 'targetBytes': args.limit * 95 // 100,
                      'pendingHistoryBytes': reserve, 'pushPendingHistoryFirst': separate_pending, 'dataFiles': len(files),
                      'dataBytes': sum(n for _, n in files),
                      'batches': [{'files': len(b), 'addBytes': n} for b, n in batches]}, indent=2), flush=True)
    if not args.execute:
        print('Plan only. Run again with --execute to add, commit and push each batch.', flush=True)
        return
    if separate_pending:
        base = publish(args.remote, branch, base, args.limit, 0, 0)
        reserve = 0
    for number, (batch, length) in enumerate(batches, 1):
        if git('diff', '--cached', '--name-only', '-z'):
            raise RuntimeError('Index changed externally. Stopping without touching it.')
        if remote_tip(args.remote, branch) != base:
            raise RuntimeError('Remote changed externally. Stopping before staging.')
        free = shutil.disk_usage(ROOT).free
        if free < length + args.min_free_mb * 1024**2:
            raise RuntimeError(f'Insufficient space to stage batch {number}: need {length:,} bytes plus reserve; free {free:,}. Earlier pushes are preserved.')
        for path, expected in batch:
            if (ROOT / path).stat().st_size != expected:
                raise RuntimeError('File changed after planning: ' + path)
        paths = b'\0'.join(os.fsencode(':(literal)' + path) for path, _ in batch) + b'\0'
        git('add', '--pathspec-from-file=-', '--pathspec-file-nul', input=paths)
        staged_names = {os.fsdecode(p) for p in git('diff', '--cached', '--name-only', '-z').split(b'\0') if p}
        if staged_names != {p for p, _ in batch}:
            raise RuntimeError('Staged paths differ from the planned batch. Stopping without committing.')
        object_ids = []
        for row in git('ls-files', '--stage', '-z').split(b'\0'):
            if row:
                metadata, path = row.split(b'\t', 1)
                if os.fsdecode(path) in staged_names:
                    object_ids.append(metadata.split()[1])
        sizes = git('cat-file', '--batch-check=%(objectsize)', input=b'\n'.join(object_ids) + b'\n')
        actual_added = sum(int(n) for n in sizes.splitlines())
        if actual_added > args.limit or actual_added != length:
            raise RuntimeError('Staged bytes differ from the plan or exceed the limit. Stopping without committing.')
        git('commit', '-m', f'Add book data batch {number}/{len(batches)} ({length:,} bytes)')
        base = publish(args.remote, branch, base, args.limit, length, len(batch))
        compact_if_room()
    if not batches and reserve:
        publish(args.remote, branch, base, args.limit, 0, 0)
    print('All planned data batches pushed successfully.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--remote', default='origin')
    parser.add_argument('--branch')
    parser.add_argument('--limit', type=int, default=1_000_000_000, help='Hard cap in bytes; default 1 decimal GB')
    parser.add_argument('--min-free-mb', type=int, default=128)
    options = parser.parse_args()
    try:
        if options.limit < 1_000_000 or options.limit > 1_000_000_000:
            raise ValueError('Limit must be between 1 MB and 1 GB.')
        if options.execute:
            with sync_lock():
                main(options)
        else:
            main(options)
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'{error}\n')
