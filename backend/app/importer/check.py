"""List reels by flag. No API calls, no database writes.

    python -m app.importer.check [file] [--flag FLAG]
"""

import argparse
import sys
from collections import defaultdict

from app.importer.flags import FLAG_DESCRIPTIONS, compute_flags
from app.importer.parse import ExportParseError, find_export_files, load_file


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", help="one export file (default: every data/reels*.json)")
    parser.add_argument("--flag", choices=sorted(FLAG_DESCRIPTIONS), help="only list reels with this flag")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252

    files = find_export_files(args.file)
    if not files:
        print("No export files found (looked for data/reels*.json).")
        return 1

    by_flag = defaultdict(list)
    total = 0
    for path in files:
        try:
            parsed = load_file(path)
        except ExportParseError as e:
            print(f"PARSE ERROR {e}")
            return 1
        total += len(parsed.reels)
        for index, reason in parsed.skipped:
            print(f"SKIPPED {path.name} item {index}: {reason}")
        for reel in parsed.reels:
            for flag in compute_flags(reel):
                by_flag[flag].append(reel)

    flags = [args.flag] if args.flag else [f for f in FLAG_DESCRIPTIONS if f in by_flag]
    print(f"{total} reels in {len(files)} file(s)\n")
    for flag in flags:
        reels = by_flag.get(flag, [])
        print(f"{flag} ({len(reels)}): {FLAG_DESCRIPTIONS[flag]}")
        for r in reels:
            print(f"  {r.source_file}#{r.index}  {r.venue or '(no venue)':40.40}  {r.post_url}")
        print()
    if not args.flag and not by_flag:
        print("No flags.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
