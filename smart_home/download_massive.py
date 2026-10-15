"""Download Amazon's MASSIVE dataset (v1.1, CC BY 4.0) for the smart-home PoC.

Fetches the official archive from Amazon's S3 bucket, checks it against a
pinned SHA-256 so everyone works from the same data, and extracts only the two
locales the PoC uses:

  datasets/massive/en-US.jsonl   source of commands.csv
  datasets/massive/pt-PT.jsonl   optional Portuguese bonus (matching ids)

datasets/ is git-ignored. Safe to re-run: existing files are reused.

Run:  python download_massive.py
"""

from __future__ import annotations

import hashlib
import tarfile
import urllib.request
from pathlib import Path

URL = "https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz"
SHA256 = "4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577"
LOCALES = ("en-US", "pt-PT")

DATASETS_DIR = Path(__file__).parent / "datasets"
ARCHIVE = DATASETS_DIR / "amazon-massive-dataset-1.1.tar.gz"
MASSIVE_DIR = DATASETS_DIR / "massive"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download() -> None:
    if ARCHIVE.exists() and sha256(ARCHIVE) == SHA256:
        print(f"Archive already downloaded: {ARCHIVE.relative_to(DATASETS_DIR.parent)}")
        return
    DATASETS_DIR.mkdir(exist_ok=True)
    print(f"Downloading {URL} (~40 MB) ...")
    partial = ARCHIVE.with_suffix(".part")
    urllib.request.urlretrieve(URL, partial)
    if (got := sha256(partial)) != SHA256:
        partial.unlink()
        raise SystemExit(f"Checksum mismatch: expected {SHA256}, got {got}. The upstream file changed.")
    partial.rename(ARCHIVE)


def extract() -> None:
    wanted = {f"{locale}.jsonl" for locale in LOCALES}
    if all((MASSIVE_DIR / name).exists() for name in wanted):
        print(f"Locales already extracted: {', '.join(sorted(wanted))}")
        return
    MASSIVE_DIR.mkdir(parents=True, exist_ok=True)
    with tarfile.open(ARCHIVE) as tar:
        members = [m for m in tar.getmembers() if m.isfile() and Path(m.name).name in wanted]
        for m in members:
            m.name = Path(m.name).name  # flatten 1.1/data/en-US.jsonl -> en-US.jsonl
        tar.extractall(MASSIVE_DIR, members=members, filter="data")
    print(f"Extracted {', '.join(sorted(m.name for m in members))} to {MASSIVE_DIR.relative_to(DATASETS_DIR.parent)}")


def main() -> None:
    download()
    extract()
    for locale in LOCALES:
        path = MASSIVE_DIR / f"{locale}.jsonl"
        with path.open(encoding="utf-8") as f:
            print(f"  {path.relative_to(DATASETS_DIR.parent)}: {sum(1 for _ in f):,} rows")


if __name__ == "__main__":
    main()
