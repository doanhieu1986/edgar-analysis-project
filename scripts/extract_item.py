"""
Extract specific Items from SEC 10-K filing text files.
Support extracting metadata and saving to Parquet format.

Usage:
    python extract_item.py <file_path> <item_name> [--output <output_file>]
    python extract_item.py <file_or_dir> --parquet

Examples:
    python extract_item.py report.txt "1A"
    python extract_item.py report.txt "7"
    python extract_item.py report.txt "9A" --output item_9a.txt
    python extract_item.py report.txt --list
    python extract_item.py /path/to/10k/files --parquet
"""

import re
import sys
import argparse
from pathlib import Path
from typing import Optional, Dict, Any
import pandas as pd
from tqdm import tqdm


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


def extract_metadata(text: str) -> Dict[str, Any]:
    """
    Extract metadata from SEC 10-K header section.
    Returns dict with: cik, filed_date, form_type, conformed_period
    """
    metadata = {}

    # Extract CENTRAL INDEX KEY
    cik_match = re.search(r"CENTRAL INDEX KEY:\s*(\d+)", text, re.IGNORECASE)
    metadata["cik"] = cik_match.group(1) if cik_match else None

    # Extract FILED AS OF DATE (YYYYMMDD)
    filed_match = re.search(r"FILED AS OF DATE:\s*(\d{8})", text, re.IGNORECASE)
    metadata["filed_date"] = filed_match.group(1) if filed_match else None

    # Extract CONFORMED SUBMISSION TYPE
    form_match = re.search(r"CONFORMED SUBMISSION TYPE:\s*(\S+)", text, re.IGNORECASE)
    metadata["form_type"] = form_match.group(1) if form_match else None

    # Extract CONFORMED PERIOD OF REPORT (to get the year)
    period_match = re.search(r"CONFORMED PERIOD OF REPORT:\s*(\d{8})", text, re.IGNORECASE)
    if period_match:
        period_str = period_match.group(1)
        metadata["year"] = period_str[:4]  # Extract year from YYYYMMDD
        metadata["conformed_period"] = period_str
    else:
        metadata["year"] = None
        metadata["conformed_period"] = None

    return metadata


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


def process_files_to_parquet(file_or_dir: Path) -> None:
    """
    Process 10-K files and extract metadata + items, save to parquet by year.
    """
    # Get list of files
    if file_or_dir.is_file():
        files = [file_or_dir]
    elif file_or_dir.is_dir():
        # Recursively find all 10-K files in directory and subdirectories
        files = list(file_or_dir.rglob("*_10-K_*.txt"))
    else:
        print(f"Error: {file_or_dir} not found", file=sys.stderr)
        sys.exit(1)

    if not files:
        print(f"No 10-K files found in {file_or_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(files)} 10-K files to process")

    # Create outputs directory
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    # Collect data by year
    data_by_year: Dict[str, list] = {}

    # Process files with progress bar
    for file_path in tqdm(files, desc="Processing files"):
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")

            # Extract metadata
            metadata = extract_metadata(text)
            filed_date = metadata.get("filed_date")

            if not filed_date:
                print(f"  Warning: Could not extract filed_date from {file_path.name}", file=sys.stderr)
                continue

            # Extract year from filed_date (YYYYMMDD -> YYYY)
            year = filed_date[:4]

            # Extract quarter from file path (e.g., QTR1, QTR2, QTR3, QTR4)
            quarter = None
            parts = file_path.parts
            for part in parts:
                if part.startswith("QTR") and len(part) == 4 and part[3].isdigit():
                    quarter = part
                    break

            # Extract items
            item_1a = extract_item(text, "1A")
            item_7 = extract_item(text, "7")

            # Create data row with year and quarter at the beginning
            row = {
                "year": year,
                "quarter": quarter,
                "filename": file_path.name,
                "cik": metadata.get("cik"),
                "filed_date": metadata.get("filed_date"),
                "form_type": metadata.get("form_type"),
                "conformed_period": metadata.get("conformed_period"),
                "item_1a": item_1a,
                "item_7": item_7,
            }

            # Add to year bucket
            if year not in data_by_year:
                data_by_year[year] = []
            data_by_year[year].append(row)

        except Exception as e:
            print(f"  Error processing {file_path.name}: {e}", file=sys.stderr)

    # Save parquet files by year
    for year, records in sorted(data_by_year.items()):
        df = pd.DataFrame(records)
        output_file = output_dir / f"{year}_data.parquet"
        df.to_parquet(output_file, index=False)
        print(f"Saved: {output_file} ({len(records)} records)")


def main():
    parser = argparse.ArgumentParser(
        description="Extract Items from SEC 10-K filing text files."
    )

    # Calculate default path relative to script location
    script_dir = Path(__file__).parent
    default_source_dir = script_dir.parent / ".sources_data"

    parser.add_argument(
        "file",
        nargs="?",
        default=str(default_source_dir),
        help=f"Path to the 10-K text file or directory (default: {default_source_dir})",
    )
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
        "--parquet",
        action="store_true",
        help="Extract metadata and items, save to parquet files by year",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Save extracted text to this file instead of printing",
    )
    args = parser.parse_args()

    file_path = Path(args.file)

    # If no parquet flag and no item specified, default to parquet mode
    if not args.parquet and not args.item and not args.list:
        args.parquet = True

    # Handle parquet mode
    if args.parquet:
        process_files_to_parquet(file_path)
        return

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
