"""Download and validate MovieLens ml-latest-small into ../data/.

    cd backend && .venv/bin/python -m scripts.setup_data [--force]
"""

from __future__ import annotations

import argparse
import sys

from app.config import get_settings
from app.dataset import DatasetError, download_dataset, load_raw, validate_folder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="download again even if the data already exists")
    args = parser.parse_args()
    settings = get_settings()
    try:
        if not args.force:
            try:
                validate_folder(settings.dataset_dir)
                print(f"Dataset already present at {settings.dataset_dir}")
            except DatasetError:
                print("Downloading MovieLens ml-latest-small (about 1 MB)...")
                download_dataset(settings.data_dir)
        else:
            print("Downloading MovieLens ml-latest-small (about 1 MB)...")
            download_dataset(settings.data_dir)
        raw = load_raw(settings.dataset_dir)
    except DatasetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {len(raw.movies):,} movies, {len(raw.ratings):,} ratings, {raw.ratings['userId'].nunique()} users, {len(raw.tags):,} tags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
