import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('batches', Path(__file__).parents[1] / 'scripts/push_data_batches.py')
batches = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batches)

class BatchTests(unittest.TestCase):
    def test_batches_reserve_space_for_unpublished_history(self):
        files = [('a', 40), ('b', 40), ('c', 60)]
        result = list(batches.partition(files, 100, 30))
        self.assertEqual(result, [([('a', 40)], 40), ([('b', 40), ('c', 60)], 100)])
        self.assertEqual([p for batch, _ in result for p, _ in batch], ['a', 'b', 'c'])
        self.assertTrue(all(n <= 100 for _, n in result))
    def test_oversized_file_refused(self):
        with self.assertRaises(ValueError): list(batches.partition([('large', 101)], 100))
    def test_empty_dataset(self):
        self.assertEqual(list(batches.partition([], 100, 20)), [])

class LocalGitIntegrationTests(unittest.TestCase):
    def test_each_local_push_is_capped_and_remote_advances_per_batch(self):
        import contextlib
        import io
        import json
        import random
        import subprocess
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            remote = root / 'remote.git'
            repo = root / 'work'
            subprocess.run(['git', 'init', '--quiet', '--bare', str(remote)], check=True)
            subprocess.run(['git', 'init', '--quiet', '-b', 'main', str(repo)], check=True)
            def command(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args])
            command('config', 'user.name', 'Batch Test')
            command('config', 'user.email', 'test@example.invalid')
            command('config', 'commit.gpgsign', 'false')
            command('remote', 'add', 'origin', str(remote))
            (repo / 'data').mkdir()
            (repo / '.gitignore').write_text('data/.sync.lock\n')
            command('add', '.gitignore')
            command('commit', '-qm', 'Initial unpublished commit')
            rng = random.Random(42)
            for i in range(3):
                (repo / 'data' / f'{i}.bin').write_bytes(rng.randbytes(600_000))
            args = SimpleNamespace(remote='origin', branch=None, execute=True, limit=1_000_000, min_free_mb=0)
            with patch.object(batches, 'ROOT', repo), contextlib.redirect_stdout(io.StringIO()):
                with batches.sync_lock():
                    batches.main(args)
            records = [json.loads(line) for line in (repo / '.git/data-push-batches.jsonl').read_text().splitlines()]
            self.assertEqual(len(records), 3)
            self.assertTrue(all(0 < item['packBytes'] <= 1_000_000 for item in records))
            self.assertTrue(all(item['addedBytes'] == 600_000 for item in records))
            self.assertEqual(command('rev-parse', 'HEAD').strip(), subprocess.check_output(['git', '--git-dir', str(remote), 'rev-parse', 'main']).strip())
            self.assertEqual(command('ls-files', '--others', '--exclude-standard'), b'')
