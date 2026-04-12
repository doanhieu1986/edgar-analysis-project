import re
import sys
import argparse
import pandas as pd
from pathlib import Path

OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"
COMBINED_FILE = OUTPUTS_DIR / "combined_data.parquet"
CLEANED_FILE = OUTPUTS_DIR / "cleaned_data.parquet"

# Minimum character length for item_1a to be considered valid content
MIN_ITEM_LEN = 200

# Regex to strip "Item 1A..." header at start of text (various formats)
_HEADER_RE = re.compile(
    r"^[\s\n]*item\s*1a[\s\n]*[.\-:]?[\s\n]*(?:risk\s+factors)?[\s\n]*",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Step 1: Merge
# ---------------------------------------------------------------------------

def merge_parquet_files(outputs_dir: Path = OUTPUTS_DIR) -> pd.DataFrame:
    """Merge all {year}_data.parquet files into one combined DataFrame."""
    parquet_files = sorted(outputs_dir.glob("[0-9][0-9][0-9][0-9]_data.parquet"))

    if not parquet_files:
        print(f"No parquet files found in {outputs_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(parquet_files)} parquet files ({parquet_files[0].stem[:4]}–{parquet_files[-1].stem[:4]})")

    dfs = []
    for fpath in parquet_files:
        df = pd.read_parquet(fpath)
        dfs.append(df)
        print(f"  {fpath.name}: {len(df):,} rows")

    combined = pd.concat(dfs, ignore_index=True)
    print(f"\nTotal: {len(combined):,} rows, {len(combined.columns)} columns")
    return combined


def save_parquet(df: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"Saved → {out_path}  ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# Step 2: Clean
# ---------------------------------------------------------------------------

def strip_item_header(text: str) -> str:
    """Remove 'Item 1A. Risk Factors' header at the start of the text."""
    return _HEADER_RE.sub("", text).strip()


def normalize_whitespace(text: str) -> str:
    """Replace newlines and multiple spaces with a single space."""
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def clean_item_1a(text: str) -> str:
    """Full cleaning pipeline for a single item_1a string."""
    text = strip_item_header(text)
    text = normalize_whitespace(text)
    return text


def clean_dataframe(df: pd.DataFrame, min_len: int = MIN_ITEM_LEN) -> pd.DataFrame:
    """
    Clean item_1a column:
      1. Drop rows where item_1a is null or too short (garbage extractions)
      2. Strip 'Item 1A. Risk Factors' header
      3. Normalize whitespace (newlines → space, collapse multi-space)
    Returns a new DataFrame with an added 'item_1a_clean' column.
    """
    total = len(df)

    # Step 2a: drop nulls and short texts
    df_valid = df[df["item_1a"].notna() & (df["item_1a"].str.len() >= min_len)].copy()
    dropped_null = total - len(df_valid)
    print(f"  Dropped (null or < {min_len} chars): {dropped_null:,} rows")

    # Step 2b & 2c: strip header + normalize whitespace
    df_valid["item_1a_clean"] = df_valid["item_1a"].apply(clean_item_1a)

    # Drop rows that became empty after cleaning
    before = len(df_valid)
    df_valid = df_valid[df_valid["item_1a_clean"].str.len() >= min_len]
    dropped_after = before - len(df_valid)
    if dropped_after:
        print(f"  Dropped (empty after cleaning): {dropped_after:,} rows")

    print(f"  Remaining: {len(df_valid):,} rows")
    return df_valid.reset_index(drop=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Preprocess SEC 10-K extracted data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Step 1: merge
    merge_parser = subparsers.add_parser(
        "merge", help="Merge all year parquet files into combined_data.parquet"
    )
    merge_parser.add_argument(
        "--output", type=Path, default=COMBINED_FILE,
        help=f"Output path (default: {COMBINED_FILE})",
    )

    # Step 2: clean
    clean_parser = subparsers.add_parser(
        "clean", help="Clean item_1a text: drop garbage, strip header, normalize whitespace"
    )
    clean_parser.add_argument(
        "--input", type=Path, default=COMBINED_FILE,
        help=f"Input parquet (default: {COMBINED_FILE})",
    )
    clean_parser.add_argument(
        "--output", type=Path, default=CLEANED_FILE,
        help=f"Output parquet (default: {CLEANED_FILE})",
    )
    clean_parser.add_argument(
        "--min-len", type=int, default=MIN_ITEM_LEN,
        help=f"Minimum chars for item_1a to keep (default: {MIN_ITEM_LEN})",
    )

    # Run all steps sequentially
    subparsers.add_parser(
        "all", help="Run all preprocessing steps: merge → clean"
    )

    args = parser.parse_args()

    if args.command == "merge":
        df = merge_parquet_files()
        save_parquet(df, args.output)

    elif args.command == "clean":
        if not args.input.exists():
            print(f"Input file not found: {args.input}", file=sys.stderr)
            print("Run 'merge' step first.", file=sys.stderr)
            sys.exit(1)
        print(f"Reading {args.input} ...")
        df = pd.read_parquet(args.input)
        print(f"Loaded {len(df):,} rows. Cleaning ...")
        df_clean = clean_dataframe(df, min_len=args.min_len)
        save_parquet(df_clean, args.output)

    elif args.command == "all":
        print("=== Step 1: Merge ===")
        df = merge_parquet_files()
        save_parquet(df, COMBINED_FILE)

        print("\n=== Step 2: Clean ===")
        df_clean = clean_dataframe(df)
        save_parquet(df_clean, CLEANED_FILE)


if __name__ == "__main__":
    main()
