"""Download the source PDFs listed in sources.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def download_sources(manifest_path: Path, output_dir: Path) -> None:
    sources = json.loads(manifest_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)

    for source in sources:
        destination = output_dir / source["filename"]
        request = Request(
            source["url"],
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        print(f"Downloading {source['document_title']}...")
        try:
            with urlopen(request, timeout=60) as response:
                payload = response.read()
        except (HTTPError, URLError, TimeoutError) as error:
            print(f"  failed {source['filename']}: {error}")
            continue
        if not payload.startswith(b"%PDF"):
            print(f"  skipped {source['filename']}: response was not a PDF ({len(payload):,} bytes)")
            continue
        destination.write_bytes(payload)
        print(f"  saved {destination} ({destination.stat().st_size:,} bytes)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("sources.json"))
    parser.add_argument("--output", type=Path, default=Path("data/policy_pdfs"))
    args = parser.parse_args()
    download_sources(args.manifest, args.output)
