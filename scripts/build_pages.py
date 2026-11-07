"""Build a self-contained Pages artifact without changing source data."""

import hashlib
import argparse
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageFile, ImageOps

ImageFile.LOAD_TRUNCATED_IMAGES = True


ROOT = Path(__file__).resolve().parents[1]
MAX_SITE_BYTES = 900 * 1024 * 1024  # Leave headroom below the Pages 1 GB limit.


def build(root=ROOT, output=None):
    root = Path(root)
    output = Path(output) if output is not None else root / "dist"
    if output.exists():
        if output.resolve() != (root / "dist").resolve():
            raise FileExistsError(f"Custom output must not already exist: {output}")
        shutil.rmtree(output)
    (output / "data" / "books").mkdir(parents=True)

    catalog = json.loads((root / "data/catalog.json").read_text())
    manifests = {
        entry["manifest"]: json.loads((root / "data" / entry["manifest"]).read_text())
        for entry in catalog
    }
    paths = set()

    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ("path", "cover") and isinstance(item, str) and item.startswith("assets/"):
                    paths.add(item)
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(catalog)
    collect(manifests)

    def convert(relative):
        source = root / "data" / relative
        if not source.is_file():
            raise FileNotFoundError(f"Referenced image is missing: {source}")
        # Keep the original extension in the stem to avoid png/jpg collisions.
        target_relative = relative + ".webp"
        target = output / "data" / target_relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(source) as image:
                image = ImageOps.exif_transpose(image)
                image.convert("RGBA" if "A" in image.getbands() else "RGB").save(
                    target, "WEBP", quality=85, method=4
                )
        except Exception as error:
            raise RuntimeError(f"Cannot publish image {source}: {error}") from error
        content = target.read_bytes()
        return relative, {
            "path": target_relative,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    with ThreadPoolExecutor(max_workers=4) as executor:
        converted = {}
        for index, (relative, asset) in enumerate(executor.map(convert, sorted(paths)), 1):
            converted[relative] = asset
            if index % 250 == 0:
                print(f"Optimized {index}/{len(paths)} images", flush=True)

    def rewrite(value):
        if isinstance(value, dict):
            result = {key: rewrite(item) for key, item in value.items()}
            if value.get("path") in converted:
                result.update(converted[value["path"]])
            if value.get("cover") in converted:
                result["cover"] = converted[value["cover"]]["path"]
            return result
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        return value

    def write_json(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    write_json(output / "data/catalog.json", rewrite(catalog))
    for relative, manifest in manifests.items():
        write_json(output / "data" / relative, rewrite(manifest))
    shutil.copytree(root / "src", output / "src")
    shutil.copytree(root / "examples", output / "examples")
    (output / ".nojekyll").touch()
    (output / "index.html").write_text(
        '<!doctype html><html lang="vi"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="refresh" content="0;url=./examples/">'
        '<title>Thư viện sách</title><a href="./examples/">Mở thư viện sách</a></html>',
        encoding="utf-8",
    )
    size = sum(path.stat().st_size for path in output.rglob("*") if path.is_file())
    if size > MAX_SITE_BYTES:
        raise RuntimeError(f"Pages artifact is {size / 1024**2:.1f} MiB; limit is 900 MiB. Reduce image quality or split the library before deploying.")
    print(f"Built {len(catalog)} books, {len(paths)} images: {size / 1024**2:.1f} MiB in {output}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New output directory (default: dist)")
    build(output=parser.parse_args().output)
