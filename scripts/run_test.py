"""
View parquet file as DataFrame
"""

import pandas as pd
from pathlib import Path


def view_parquet(file_path: str) -> None:
    """Read and display parquet file as DataFrame"""
    path = Path(file_path)

    if not path.exists():
        print(f"Error: File not found: {file_path}")
        return

    # Read parquet file
    df = pd.read_parquet(file_path)

    # Set pandas display options for better readability
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_rows', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', 80)

    # Display DataFrame
    print(df)


if __name__ == "__main__":
    view_parquet("outputs/2024_data.parquet")
