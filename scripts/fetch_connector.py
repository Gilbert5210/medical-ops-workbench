"""Fetch the pinned upstream connector without overwriting a local checkout."""
from pathlib import Path
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
REVISION = "bb6fa2e208719ee634fec37881be29d3aa4699b3"
ARCHIVE_URL = f"https://codeload.github.com/xpzouying/xiaohongshu-mcp/tar.gz/{REVISION}"
DESTINATION = ROOT / "data/connector/build/source"


def main():
    if DESTINATION.exists():
        raise SystemExit("Source already exists; keep it or move it aside before fetching.")
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=DESTINATION.parent, prefix="fetch-") as temp:
        archive = Path(temp) / "source.tar.gz"
        request = urllib.request.Request(ARCHIVE_URL, headers={"User-Agent": "medical-ops-workbench"})
        with urllib.request.urlopen(request, timeout=30) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        with tarfile.open(archive) as source:
            source.extractall(Path(temp) / "unpacked", filter="data")
        checkout = Path(temp) / "unpacked" / f"xiaohongshu-mcp-{REVISION}"
        if not (checkout / "go.mod").is_file():
            raise SystemExit("Unexpected archive layout; refusing to install.")
        checkout.rename(DESTINATION)
    print(f"Pinned connector source ready: {DESTINATION}")


if __name__ == "__main__":
    main()
