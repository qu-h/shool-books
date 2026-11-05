import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


spec = importlib.util.spec_from_file_location("build_pages", Path(__file__).parents[1] / "scripts/build_pages.py")
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


class PagesBuildTest(unittest.TestCase):
    def fixture(self, root):
        for directory in ("data/books", "data/assets/1", "src", "examples"):
            (root / directory).mkdir(parents=True)
        image = root / "data/assets/1/page.png"
        Image.new("RGB", (48, 64), "white").save(image)
        (root / "data/catalog.json").write_text(json.dumps([
            {"id": "1", "manifest": "books/1.json", "cover": "assets/1/page.png"}
        ]))
        (root / "data/books/1.json").write_text(json.dumps({
            "pages": [{"path": "assets/1/page.png", "bytes": 1, "sha256": "old"}],
            "covers": {"first": {"path": "assets/1/page.png"}},
            "offlineComplete": True,
        }))
        (root / "src/index.js").write_text("export {};")
        (root / "examples/index.html").write_text("demo")
        return image.read_bytes()

    def test_published_references_and_hashes_match_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = self.fixture(root)
            output = pages.build(root)
            catalog = json.loads((output / "data/catalog.json").read_text())
            book = json.loads((output / "data" / catalog[0]["manifest"]).read_text())
            asset = book["pages"][0]
            content = (output / "data" / asset["path"]).read_bytes()
            self.assertEqual(catalog[0]["cover"], asset["path"])
            self.assertEqual(book["covers"]["first"], asset)
            self.assertEqual(asset["bytes"], len(content))
            self.assertEqual(asset["sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual((root / "data/assets/1/page.png").read_bytes(), original)
            with Image.open(output / "data" / asset["path"]) as image:
                self.assertEqual(image.size, (48, 64))
                self.assertEqual(image.format, "WEBP")
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "examples/index.html").is_file())

    def test_missing_assets_and_oversize_artifacts_fail_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            with patch.object(pages, "MAX_SITE_BYTES", 1):
                with self.assertRaisesRegex(RuntimeError, "Pages artifact"):
                    pages.build(root)
            (root / "data/assets/1/page.png").unlink()
            with self.assertRaisesRegex(FileNotFoundError, "Referenced image"):
                pages.build(root)


if __name__ == "__main__":
    unittest.main()
