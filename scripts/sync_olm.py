#!/usr/bin/env python3
"""Archive OLM's public textbook catalogue and explicitly published page URLs.
No authentication, URL guessing, or evaluation of upstream JavaScript.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
import gzip
import http.client
import ssl
import signal
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://olm.vn'

class Cards(HTMLParser):
    def __init__(self):
        super().__init__()
        self.books = []
        self.current = None
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'a' and '/thu-vien-so/doc-sach/' in d.get('href', ''):
            self.current = {'sourceUrl': urljoin(BASE, d['href'])}
        if self.current is not None:
            if tag == 'img' and d.get('src'):
                self.current['coverSource'] = urljoin(BASE, d['src'])
            if d.get('title'):
                self.current['title'] = d['title']
    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            if 'title' in self.current:
                self.current['id'] = self.current['sourceUrl'].rsplit('.', 1)[-1]
                if not self.current['id'].isdigit():
                    raise ValueError('Invalid book ID')
                self.books.append(self.current)
            self.current = None


def field(html, name, default=None):
    match = re.search(r'\b' + re.escape(name) + r'\s*:', html)
    if not match:
        return default
    try:
        return json.JSONDecoder().raw_decode(html[match.end():].lstrip())[0]
    except ValueError:
        return default


def parse_detail(html):
    # Scope extraction to the reader config, not unrelated scripts.
    marker = html.find('DIGITAL_LIBRARY_READER.init(')
    if marker < 0:
        raise ValueError('No public reader configuration')
    config = html[marker:]
    urls = field(config, 'download_book_pages_urls', [])
    total = field(config, 'totalPages', 0)
    if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
        raise ValueError('Invalid page URL list')
    return {'title': field(config, 'title'), 'totalPages': total,
            'urls': urls, 'covers': field(config, 'download_book_pages_covers', {}),
            'downloadEnabled': field(config, 'download_book_pages', False)}


_connections = threading.local()

def curl(url, destination=None):
    # One persistent TLS connection per worker/host keeps large archives practical.
    parsed = urlparse(url)
    host = parsed.hostname or ''
    if parsed.scheme != 'https' or not (host == 'olm.vn' or host.endswith('.olm.vn')):
        raise ValueError('Unexpected source host: ' + url)
    if not hasattr(_connections, 'hosts'):
        _connections.hosts = {}
    for attempt in range(4):
        try:
            connection = _connections.hosts.get(host)
            if connection is None:
                connection = http.client.HTTPSConnection(host, timeout=90, context=ssl.create_default_context())
                _connections.hosts[host] = connection
            path = parsed.path + ('?' + parsed.query if parsed.query else '')
            connection.request('GET', path, headers={'User-Agent': 'school-books-archive/0.1', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            payload = response.read()
            if response.status in (301, 302, 303, 307, 308):
                redirect = urljoin(url, response.getheader('Location', ''))
                if redirect == url:
                    raise ValueError('Invalid redirect')
                return curl(redirect, destination)
            if response.status != 200:
                raise ValueError(f'HTTP {response.status}: {url}')
            if destination:
                destination.write_bytes(payload)
            return payload
        except Exception:
            conn = _connections.hosts.pop(host, None)
            if conn:
                conn.close()
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.part')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def sync(args):
    data = args.output.resolve()
    data.mkdir(parents=True, exist_ok=True)
    errors = []
    stopped = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    books = {}
    listings = []
    for grade in args.grades:
        for role in ['student', 'teacher']:
            url = f'{BASE}/api/thu-vien-so/render-list-books?grade={grade}&role={role}'
            try:
                payload = json.loads(curl(url))
                parser = Cards()
                parser.feed(payload['html'])
                expected = int(payload.get('countBooks', len(parser.books)))
                if expected != len(parser.books):
                    raise ValueError(f'Catalogue count mismatch: {expected} != {len(parser.books)}')
                listings.append({'grade': grade, 'role': role, 'count': expected, 'sourceUrl': url})
                for book in parser.books:
                    book.update(grade=grade, role=role)
                    books[book['id']] = book
                print(f'Catalogue: grade {grade}, {role}: {len(parser.books)}', flush=True)
            except Exception as error:
                errors.append({'url': url, 'error': str(error)})
    def detail(book):
        path = data / 'books' / (book['id'] + '.json')
        # Keep raw source separately so an interrupted asset run can resume without more HTML requests.
        cache = data / 'sources' / (book['id'] + '.html.gz')
        cache.parent.mkdir(parents=True, exist_ok=True)
        if not cache.exists() or args.refresh:
            raw = curl(book['sourceUrl'])
            temporary = cache.with_suffix('.part')
            temporary.write_bytes(gzip.compress(raw))
            temporary.replace(cache)
        details = parse_detail(gzip.decompress(cache.read_bytes()).decode())
        book['title'] = details['title'] or book['title']
        book['totalPages'] = details['totalPages']
        book['downloadEnabled'] = details['downloadEnabled']
        book['pages'] = [{'number': i + 1, 'sourceUrl': u} for i, u in enumerate(details['urls'])]
        book['covers'] = {k: {'sourceUrl': v} for k, v in details['covers'].items() if v}
        if not book['covers'] and book.get('coverSource'):
            book['covers'] = {'first': {'sourceUrl': book['coverSource']}}
        book['metadataComplete'] = len(book['pages']) == book['totalPages'] and book['totalPages'] > 0
        if path.exists():
            previous = json.loads(path.read_text())
            previous_assets = {item['sourceUrl']: item for item in [*previous.get('pages', []), *previous.get('covers', {}).values()]}
            for item in [*book['pages'], *book['covers'].values()]:
                old = previous_assets.get(item['sourceUrl'], {})
                if old.get('path') and (data / old['path']).is_file():
                    item.update({key: old[key] for key in ['path', 'bytes', 'sha256'] if key in old})
        write_json(path, book)
        return book
    detailed = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(detail, b): b for b in books.values()}
        for future in as_completed(futures):
            book = futures[future]
            try:
                detailed.append(future.result())
            except Exception as error:
                errors.append({'id': book['id'], 'error': str(error)})
                old_path = data / 'books' / (book['id'] + '.json')
                if old_path.exists():
                    book = json.loads(old_path.read_text())
                else:
                    book.update(pages=[], covers={}, metadataComplete=False, totalPages=0)
                    write_json(old_path, book)
                detailed.append(book)
    detailed.sort(key=lambda b: (args.grades.index(b['grade']), b['role'], b['title']))
    asset_lock = threading.Lock()
    disk_full = threading.Event()
    completed = 0
    def asset(item, book_id, label):
        nonlocal completed
        url = item['sourceUrl']
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix not in ['.png', '.jpg', '.jpeg', '.webp', '.pdf', '.svg']:
            raise ValueError('Unknown asset format: ' + url)
        fingerprint = hashlib.sha256(url.encode()).hexdigest()[:12]
        relative = f'assets/{book_id}/{label}-{fingerprint}{suffix}'
        path = data / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        # Migrate prior filenames only when metadata proves the source URL matches.
        old_path = data / item['path'] if item.get('path') else None
        if old_path and old_path != path and old_path.is_file() and not path.exists():
            old_path.replace(path)
        if not path.exists() or path.stat().st_size == 0:
            if disk_full.is_set() or stopped.is_set():
                return
            if shutil.disk_usage(data).free < args.min_free_mb * 1024 * 1024:
                disk_full.set()
                return
            temp = path.with_suffix('.part')
            try:
                curl(url, temp)
                if temp.stat().st_size == 0:
                    raise ValueError('Empty asset')
                # Reject HTML error/login responses returned with HTTP 200.
                with temp.open('rb') as stream:
                    magic = stream.read(16)
                valid = (magic.startswith(b'\x89PNG\r\n\x1a\n') or magic.startswith(b'\xff\xd8\xff')
                         or (magic.startswith(b'RIFF') and magic[8:12] == b'WEBP')
                         or magic.startswith(b'%PDF') or b'<svg' in magic)
                if not valid:
                    raise ValueError('Response is not an image/document')
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
        item.update(path=relative, bytes=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        with asset_lock:
            completed += 1
            if completed % 250 == 0:
                print(f'Assets stored: {completed}', flush=True)
    if not args.metadata_only:
        jobs = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for book in detailed:
                for name, item in book['covers'].items():
                    jobs.append(pool.submit(asset, item, book['id'], 'cover-' + name))
                if args.asset_grades and book['grade'] not in args.asset_grades:
                    continue
                for page in book['pages']:
                    jobs.append(pool.submit(asset, page, book['id'], f"page-{page['number']:04}"))
            for future in as_completed(jobs):
                try:
                    future.result()
                except Exception as error:
                    errors.append({'error': str(error)})
        if stopped.is_set():
            errors.append({'error': 'Interrupted; downloaded files are preserved. Rerun to resume.'})
        if disk_full.is_set():
            errors.append({'error': f'Disk reserve reached ({args.min_free_mb} MiB); rerun to resume.'})
    catalog = []
    for book in detailed:
        all_assets = [*book['pages'], *book['covers'].values()]
        book['offlineComplete'] = bool(book['metadataComplete'] and all_assets and all(a.get('path') for a in all_assets))
        write_json(data / 'books' / (book['id'] + '.json'), book)
        catalog.append({k: v for k, v in book.items() if k not in ['pages', 'covers']})
        catalog[-1].update(manifest=f"books/{book['id']}.json", cover=book['covers'].get('first', {}).get('path'))
    write_json(data / 'catalog.json', catalog)
    report = {'source': f'{BASE}/thu-vien-so/sach-giao-khoa', 'syncedAt': datetime.now(timezone.utc).isoformat(),
              'grades': args.grades, 'assetGrades': args.asset_grades or args.grades, 'listings': listings, 'books': len(catalog),
              'pages': sum(len(b['pages']) for b in detailed),
              'offlineCompleteBooks': sum(b['offlineComplete'] for b in detailed),
              'downloadedPages': sum(bool(p.get('path')) for b in detailed for p in b['pages']),
              'storedAssets': sum(bool(p.get('path')) for b in detailed for p in [*b['pages'], *b['covers'].values()]),
              'storedBytes': sum(p.get('bytes', 0) for b in detailed for p in [*b['pages'], *b['covers'].values()]),
              'unavailableBooks': [{'id': b['id'], 'title': b['title'], 'grade': b['grade']} for b in detailed if not b['metadataComplete']],
              'metadataOnly': args.metadata_only, 'errors': errors}
    write_json(data / 'sync-report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'listings'}, ensure_ascii=False), flush=True)
    scoped = [b for b in detailed if not args.asset_grades or b['grade'] in args.asset_grades]
    return int(bool(errors) or (any(not b['offlineComplete'] for b in scoped) and not args.metadata_only))


def verify(data, grades=None):
    errors = []
    catalog = json.loads((data / 'catalog.json').read_text())
    count = 0
    verified_books = 0
    for entry in catalog:
        book = json.loads((data / entry['manifest']).read_text())
        if grades and book['grade'] not in grades:
            continue
        verified_books += 1
        if not book['metadataComplete'] or len(book['pages']) != book['totalPages'] or book['totalPages'] <= 0:
            errors.append(f"{book['id']}: incomplete metadata")
        for item in [*book['pages'], *book['covers'].values()]:
            path = data / item.get('path', '__missing__')
            if not path.is_file():
                errors.append(f"{book['id']}: missing {item['sourceUrl']}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != item.get('sha256'):
                errors.append(f'{path}: checksum mismatch')
            count += 1
    print(json.dumps({'catalogBooks': len(catalog), 'verifiedBooks': verified_books, 'verifiedGrades': grades or list(range(1, 13)), 'assets': count, 'errors': len(errors), 'examples': errors[:10]}, ensure_ascii=False))
    return int(bool(errors) or not verified_books)

def run_sync(args):
    # OS file locks are released even when a process crashes. Prevent two importers
    # from racing over the same temporary files or overwriting each other's index.
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / '.sync.lock').open('a+b') as lock:
        try:
            if os.name == 'posix':
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                import msvcrt
                if lock.tell() == 0:
                    lock.write(b'0')
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('Another sync is already using this data directory.', flush=True)
            return 2
        return sync(args)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grades', type=int, nargs='+', default=list(range(1, 13)), choices=range(1, 13))
    parser.add_argument('--asset-grades', type=int, nargs='+', choices=range(1, 13), help='Download pages for these grades; keep catalogue and covers for all grades')
    parser.add_argument('--workers', type=int, default=4, choices=range(1, 9))
    parser.add_argument('--output', type=Path, default=ROOT / 'data')
    parser.add_argument('--metadata-only', action='store_true')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--min-free-mb', type=int, default=1024)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    raise SystemExit(verify(args.output, args.asset_grades) if args.verify else run_sync(args))
