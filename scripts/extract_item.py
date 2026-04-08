"""
Extract specific Items from SEC 10-K filing text files.

Usage:
    python extract_item.py <file_path> <item_name> [--output <output_file>]

Examples:
    python extract_item.py report.txt "1A"
    python extract_item.py report.txt "7"
    python extract_item.py report.txt "9A" --output item_9a.txt
    python extract_item.py report.txt --list
"""

import re
import sys
import argparse
from pathlib import Path


def build_item_pattern(item_id: str) -> re.Pattern:
    """Build regex pattern to match an Item header line."""
    # Normalize: "1A" -> "1A", "1a" -> "1A"
    item_id = item_id.strip().upper()
    # Match: "Item 1A." or "Item 1A " at start of line (case-insensitive)
    return re.compile(
        rf"^Item\s+{re.escape(item_id)}\s*[.\-:]?\s*\S",
        re.IGNORECASE | re.MULTILINE,
    )


def list_items(text: str) -> list[tuple[str, int, str]]:
    """Return all Items found: (item_id, line_number, header_text)."""
    pattern = re.compile(
        r"^(Item\s+(\d+[A-Z]?)\s*[.\-:]?\s*.+)$",
        re.IGNORECASE | re.MULTILINE,
    )
    results = []
    for m in pattern.finditer(text):
        item_id = m.group(2).upper()
        line_no = text[: m.start()].count("\n") + 1
        header = m.group(1).strip()
        results.append((item_id, line_no, header))
    return results


def extract_item(text: str, item_id: str) -> str | None:
    """
    Extract the text block for a given Item.
    Returns the content from the Item header up to (but not including)
    the next Item header, or end of file.
    """
    item_id = item_id.strip().upper()

    # Find all item positions
    item_pattern = re.compile(
        r"^Item\s+(\d+[A-Z]?)\s*[.\-:]?\s*.+$",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = list(item_pattern.finditer(text))

    start_match = None
    end_pos = len(text)

    for i, m in enumerate(matches):
        found_id = m.group(1).upper()
        if found_id == item_id and start_match is None:
            start_match = m
            # Next Item becomes the end boundary
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            break

    if start_match is None:
        return None

    return text[start_match.start() : end_pos].strip()


def main():
    parser = argparse.ArgumentParser(
        description="Extract Items from SEC 10-K filing text files."
    )
    parser.add_argument("file", help="Path to the 10-K text file")
    parser.add_argument(
        "item",
        nargs="?",
        help='Item to extract, e.g. "1A", "7", "9A"',
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all Items found in the file",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Save extracted text to this file instead of printing",
    )
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    text = file_path.read_text(encoding="utf-8", errors="replace")

    if args.list:
        items = list_items(text)
        print(f"{'Item':<8} {'Line':>6}  Header")
        print("-" * 70)
        for item_id, line_no, header in items:
            print(f"{'Item '+item_id:<8} {line_no:>6}  {header[:60]}")
        return

    if not args.item:
        parser.print_help()
        sys.exit(1)

    content = extract_item(text, args.item)

    if content is None:
        print(
            f"Item {args.item.upper()} not found in {file_path.name}",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(content, encoding="utf-8")
        word_count = len(content.split())
        print(
            f"Item {args.item.upper()} extracted: {word_count:,} words -> {out_path}"
        )
    else:
        print(content)


if __name__ == "__main__":
    main()
