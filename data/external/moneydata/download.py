"""Download MoneyData (plan P3, task B2) and verify it against the checksum Mendeley publishes.

MoneyData: Firat, Vytia, Vasudeva, Jiang & Laramee, "MoneyVis: Open Bank Transaction Data for
Visualization and Beyond", EuroVis 2023, https://doi.org/10.2312/evs.20231052. Dataset record:
https://data.mendeley.com/datasets/dnxtg6n4rv/1 (CC BY 4.0). One real UK retail account.

    python data/external/moneydata/download.py

The file lands in `raw/` next to this script, which is gitignored. Standard library only.
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

FILE_NAME = "laramee26openBankTransactionData.xlsx"
URL = (
    "https://data.mendeley.com/public-files/datasets/dnxtg6n4rv/files/"
    "36b3d359-2491-4282-850f-3f03e00fbfe3/file_downloaded"
)
SHA256 = "716eaf9ad4a3cf60dc9c9c8a20ed9a917c545a1b5f139f40ed91d2104faa3ff7"  # from the Mendeley API
TIMEOUT_SECONDS = 120
RAW = Path(__file__).resolve().parent / "raw"


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    target = RAW / FILE_NAME
    request = urllib.request.Request(URL, headers={"User-Agent": "paysense-research-download"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SHA256:
        print(f"checksum mismatch: got {digest}, expected {SHA256}", file=sys.stderr)  # noqa: T201
        return 1
    target.write_bytes(data)
    print(f"{target.name}  {len(data)} bytes  sha256 {digest}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
