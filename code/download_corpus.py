"""Download the fixed public corpus and create its SHA-256 manifest."""

import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = REPO_ROOT / "reports" / "hw03" / "corpus"
MANIFEST_PATH = REPO_ROOT / "reports" / "hw03" / "CORPUS_MANIFEST.json"

SOURCES = [
    {
        "filename": "fra_regulated_mode_major_security_events.csv",
        "url": "https://data.transportation.gov/api/v3/views/65fa-qbkf/export.csv?accessType=DOWNLOAD",
        "description": "First 300 records from the FTA FRA Regulated Mode Major Security Events dataset, retrieved through the official Socrata API",
    },
    {
        "filename": "ntd_safety_security_overview.html",
        "url": "https://www.transit.dot.gov/ntd/accessing-national-transit-database-ntd-safety-and-security-event-data",
        "description": "FTA overview of National Transit Database safety and security event data",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "DATA260-HW3/1.0"})
    with urlopen(request, timeout=120) as response, destination.open("wb") as stream:
        while block := response.read(1024 * 1024):
            stream.write(block)


def main() -> None:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    access_date = date.today().isoformat()
    manifest = []

    for source in SOURCES:
        destination = CORPUS_DIR / source["filename"]
        print(f"Downloading {source['filename']} ...")
        download(source["url"], destination)
        manifest.append(
            {
                "filename": source["filename"],
                "url": source["url"],
                "description": source["description"],
                "access_date": access_date,
                "byte_size": destination.stat().st_size,
                "sha256": sha256(destination),
            }
        )

    total_bytes = sum(item["byte_size"] for item in manifest)
    result = {
        "corpus_name": "Municipal transit safety and security incidents",
        "access_date": access_date,
        "total_bytes": total_bytes,
        "meets_minimum_200_kb": total_bytes >= 200 * 1024,
        "files": manifest,
    }
    MANIFEST_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
