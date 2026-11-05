import importlib.util
from pathlib import Path
import unittest
import tempfile
import json
import hashlib
from contextlib import redirect_stdout
import io
import os
from types import SimpleNamespace
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('sync', Path(__file__).parents[1] / 'scripts/sync_olm.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

class ImporterTests(unittest.TestCase):
    def test_cards_capture_ids_title_and_cover(self):
        parser = sync.Cards()
        parser.feed('<a href="/thu-vien-so/doc-sach/toan.123"><img src="https://cdn3.olm.vn/a.png"><span title="Toán &amp; số">Toán</span></a>')
        self.assertEqual(parser.books[0]['id'], '123')
        self.assertEqual(parser.books[0]['title'], 'Toán & số')
    def test_detail_reads_json_without_evaluating_js(self):
        book = sync.parse_detail('DIGITAL_LIBRARY_READER.init({totalPages: 2, title: "Toán", download_book_pages: true, download_book_pages_urls: ["https:\\/\\/cdn3.olm.vn/a.png", "https://cdn3.olm.vn/b.png"], download_book_pages_covers: {"first":"https://cdn3.olm.vn/c.png"}})')
        self.assertEqual(book['totalPages'], 2)
        self.assertEqual(len(book['urls']), 2)
        self.assertTrue(book['downloadEnabled'])
        self.assertEqual(book['urls'][0], 'https://cdn3.olm.vn/a.png')
    def test_missing_reader_is_not_silently_complete(self):
        with self.assertRaises(ValueError): sync.parse_detail('<html>Login</html>')
    def test_fetch_rejects_foreign_hosts(self):
        with self.assertRaises(ValueError): sync.curl('https://example.com/file')

    def test_verifier_checks_scope_and_detects_corrupt_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            (data / 'page.png').write_bytes(b'original')
            manifest = {'id': '1', 'grade': 2, 'totalPages': 1, 'metadataComplete': True, 'pages': [{'sourceUrl': 'https://cdn3.olm.vn/a.png', 'path': 'page.png', 'sha256': hashlib.sha256(b'original').hexdigest()}], 'covers': {}}
            (data / 'book.json').write_text(json.dumps(manifest))
            (data / 'catalog.json').write_text(json.dumps([{'manifest': 'book.json'}]))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(sync.verify(data, [2]), 0)
                self.assertEqual(sync.verify(data, [3]), 1)
                (data / 'page.png').write_bytes(b'corrupt')
                self.assertEqual(sync.verify(data, [2]), 1)

    @unittest.skipUnless(os.name == 'posix', 'POSIX file lock test')
    def test_concurrent_importers_cannot_write_same_directory(self):
        import fcntl
        with tempfile.TemporaryDirectory() as folder:
            args = SimpleNamespace(output=Path(folder))
            with (args.output / '.sync.lock').open('a+b') as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(sync, 'sync') as download, redirect_stdout(io.StringIO()):
                    self.assertEqual(sync.run_sync(args), 2)
                    download.assert_not_called()
            with patch.object(sync, 'sync', return_value=0) as download:
                self.assertEqual(sync.run_sync(args), 0)
                download.assert_called_once_with(args)
