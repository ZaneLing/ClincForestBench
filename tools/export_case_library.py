"""Export the current case library to local review files."""
import argparse
from pathlib import Path

from backend.app.services.case_library_service import CaseLibraryService, excel_bytes, json_bytes
from backend.app.services.case_service import CaseService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", choices=["en", "zh-CN"], default="zh-CN")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = CaseService()
    directory = args.output or cases.root / "data/exports/case_library"
    directory.mkdir(parents=True, exist_ok=True)
    document = CaseLibraryService(cases).export(args.locale)
    for suffix, renderer in (("json", json_bytes), ("xlsx", excel_bytes)):
        path = directory / f"case_library_{args.locale}.{suffix}"
        path.write_bytes(renderer(document))
        print(f"{path}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
