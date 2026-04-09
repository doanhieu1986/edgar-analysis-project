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


def detect_toc_section(text: str) -> tuple[int | None, int | None]:
    """
    Detect Table of Contents section boundaries.

    Returns: (toc_start_pos, toc_end_pos)
    - If no ToC found: (None, None)
    """
    # Find ToC start marker
    toc_keywords = ["table of contents", "PART I"]
    toc_start = None

    for keyword in toc_keywords:
        match = re.search(rf"\b{keyword}\b", text, re.IGNORECASE)
        if match:
            toc_start = match.start()
            break

    if toc_start is None:
        return None, None

    # Find ToC end marker: "Item 1." actual content (not in ToC)
    # Look for pattern after toc_start with meaningful content after Item 1.
    after_toc = text[toc_start:]

    # Find "Item 1." and check if it's followed by substantial content (not just page number)
    item1_pattern = re.search(r"Item\s+1[\.\s]+(?![\d\s]*(?:Item|PART))", after_toc, re.IGNORECASE)

    if item1_pattern:
        toc_end = toc_start + item1_pattern.start()
    else:
        # Fallback: use first "Item 1A" as ToC end
        item1a_pattern = re.search(r"Item\s+1A", after_toc, re.IGNORECASE)
        toc_end = toc_start + item1a_pattern.start() if item1a_pattern else None

    return toc_start, toc_end


def normalize_line_wrapped_items(text: str) -> str:
    """
    Normalize line-wrapped Items (File 8 format).

    Example:
      Item\n1A.\nRisk Factors → Item 1A. Risk Factors
      Item\n  1A  \nRisk → Item 1A. Risk
    """
    # Pattern: "Item" followed by newlines and whitespace, then digit+letter
    text = re.sub(
        r"Item\s*\n+\s*(\d+[A-Z]?)\s*\n+",
        r"Item \1. ",
        text,
        flags=re.IGNORECASE
    )

    # Pattern: digit+letter followed by newlines, then title
    text = re.sub(
        r"(\d+[A-Z]?)\.\s*\n+\s+([A-Z])",
        r"\1. \2",
        text,
        flags=re.IGNORECASE
    )

    return text


def is_toc_entry_not_header(text: str, match_start: int, item_id: str) -> bool:
    """
    Check if Item match is a ToC entry (with page number) vs actual header.

    ToC entries typically have:
    - Item header
    - Optional title
    - Page number (1-3 digits)
    - Followed by another Item or newline

    Returns: True if it's ToC entry (should skip), False if it's actual header
    """
    # Check context after match (next 300 chars to find page number)
    after_match = text[match_start:match_start + 300]

    # ToC pattern: Item ID, title, then page number followed by Item/newline
    # Matches patterns like:
    #   "Item 1A. Risk Factors 25 Item 1B"
    #   "Item 1A. Risk Factors\n25\n"
    #   "Item 1A.\nRisk\n25\n"
    toc_pattern = (
        r"Item\s+" + re.escape(item_id) + r"\s*\.?\s*"  # Item ID
        r"[^\n]*?"  # Optional title/text (can include newlines from line-wrap)
        r"\s+(\d{1,3})\s*"  # Page number
        r"(?:Item\s+\d+|$|\n)"  # Followed by Item or end
    )

    if re.search(toc_pattern, after_match, re.IGNORECASE | re.DOTALL):
        return True

    return False


def is_reference_not_header(text: str, match_start: int, match_text: str) -> bool:
    """
    Check if Item match is a reference in text, not an actual header.

    Returns: True if it's a reference (should skip), False if it's a header
    """
    # Check context before match
    before_text = text[max(0, match_start - 50):match_start].lower()

    # Skip if preceded by "in " or "Part I," or similar reference patterns
    reference_patterns = [
        r"in\s+Item",  # "in Item 1A. Risk Factors"
        r"Part\s+[IV]+\s*,\s*Item",  # "Part I, Item 1A"
        r"See\s+Item",  # "See Item 1A"
        r"item\s+\d+[a-z]?\s*,",  # "item 1a, described" (lowercase reference)
    ]

    for pattern in reference_patterns:
        if re.search(pattern, before_text, re.IGNORECASE):
            return True

    return False


def find_item_position(text: str, item_id: str, skip_toc: bool = True) -> int | None:
    """
    Find first valid occurrence of Item with validation.

    Multi-level validation:
    1. Skip if within ToC region (detected earlier)
    2. Skip if followed by page number (ToC entry)
    3. Skip if preceded by "in Item", "Part I," etc (reference)

    Args:
        text: Document text
        item_id: Item ID (e.g., "1A", "7")
        skip_toc: Skip matches within ToC section

    Returns: Position of Item header, or None if not found
    """
    item_id = item_id.strip().upper()

    # Determine ToC region to skip
    toc_start, toc_end = (None, None) if not skip_toc else detect_toc_section(text)

    # Regex: flexible Item pattern
    # Matches: "Item 1A", "Item 1A.", "ITEM 1A", etc.
    pattern = re.compile(
        rf"Item\s+{re.escape(item_id)}\s*\.?",
        re.IGNORECASE | re.MULTILINE
    )

    for match in pattern.finditer(text):
        match_pos = match.start()

        # Skip if within ToC section
        if toc_end and match_pos < toc_end:
            continue

        # Skip if it's a ToC entry (has page number after)
        if is_toc_entry_not_header(text, match_pos, item_id):
            continue

        # Skip if it's a reference, not a header
        if is_reference_not_header(text, match_pos, match.group()):
            continue

        # Found valid Item header
        return match_pos

    return None


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
    Extract the text block for a given Item with smart validation.

    Multi-step process:
    1. Normalize line-wrapped Items
    2. Remove Table of Contents
    3. Find Item with context validation
    4. Extract content until next Item
    """
    item_id = item_id.strip().upper()

    # Step 1: Normalize line-wrapped Items (File 8 format)
    text_normalized = normalize_line_wrapped_items(text)

    # Step 2: Remove Table of Contents section
    toc_start, toc_end = detect_toc_section(text_normalized)
    if toc_end:
        # Keep text before ToC + text after ToC
        text_clean = text_normalized[:toc_start] + " " + text_normalized[toc_end:]
    else:
        text_clean = text_normalized

    # Step 3: Find valid Item position
    item_pos = find_item_position(text_clean, item_id, skip_toc=False)

    if item_pos is None:
        return None

    # Step 4: Find content boundaries
    # Find start of Item header
    item_match = re.search(
        rf"Item\s+{re.escape(item_id)}\s*\.?",
        text_clean[item_pos:],
        re.IGNORECASE
    )

    if not item_match:
        return None

    start_pos = item_pos

    # Find end: next Item or EOF
    # Look for next Item pattern after current position
    remaining_text = text_clean[item_pos + len(item_match.group()):]
    next_item_match = re.search(r"Item\s+\d+[A-Z]?\s*[\.\-:]?", remaining_text, re.IGNORECASE)

    if next_item_match:
        end_pos = item_pos + len(item_match.group()) + next_item_match.start()
    else:
        end_pos = len(text_clean)

    return text_clean[start_pos:end_pos].strip()


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
