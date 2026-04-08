"""
View parquet file as DataFrame using Polars
"""

import polars as pl
from pathlib import Path

# Get the outputs directory relative to script location
script_dir = Path(__file__).parent
outputs_dir = script_dir.parent / "outputs"

# Find all parquet files
parquet_files = sorted(outputs_dir.glob("*_data.parquet"), reverse=True)

if not parquet_files:
    print(f"No parquet files found in {outputs_dir}")
    exit(1)

# Read the latest parquet file
file_path = parquet_files[0]
print(f"Reading: {file_path.name}\n")

# Read file using Polars
df = pl.read_parquet(file_path)

# Display data
print(df)
print(f"\nShape: {df.shape[0]} rows × {df.shape[1]} columns")
