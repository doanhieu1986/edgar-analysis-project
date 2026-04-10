"""
EdgarTools Example - Extract Item 1A from 10-K filings

EdgarTools: https://github.com/dgunning/edgartools
Docs: https://edgartools.readthedocs.io/

Features:
- Free & open-source (MIT license)
- No API key required
- Direct EDGAR access
- Structured Python objects

Install:
    pip install edgartools
"""

from edgar import Company
import pandas as pd
from datetime import datetime


def extract_item_1a_edgartools(ticker: str, year: int = None) -> dict:
    """
    Extract Item 1A (Risk Factors) using EdgarTools

    Args:
        ticker: Company ticker (e.g., "MSFT", "AAPL")
        year: Filing year (e.g., 2024). If None, gets latest 10-K

    Returns:
        dict: {cik, filed_date, item_1a_content, num_words}
    """
    try:
        print(f"📥 Loading {ticker} company data...")
        company = Company(ticker)

        print(f"🔍 Fetching 10-K filing...")
        if year:
            # Find specific year's filing
            tenk = company.get_10k_filing(year)
        else:
            # Get latest 10-K
            tenk = company.latest_10k()

        print(f"✅ Filing loaded: {tenk.filing_date}")

        # Extract Item 1A (Risk Factors)
        risk_factors = tenk.risk_factors

        if not risk_factors:
            print("⚠️  Item 1A not found in this filing")
            return None

        # Extract metadata
        metadata = {
            "ticker": ticker,
            "cik": tenk.cik,
            "filed_date": tenk.filing_date.strftime("%Y%m%d") if tenk.filing_date else "N/A",
            "form_type": "10-K",
            "conformed_period": tenk.period_of_report.strftime("%Y%m%d") if tenk.period_of_report else "N/A",
            "item_1a_content": risk_factors,
            "num_words": len(risk_factors.split()),
        }

        return metadata

    except Exception as e:
        print(f"❌ Error: {e}")
        return None


def batch_extract_edgartools(tickers: list[str]) -> pd.DataFrame:
    """
    Batch extract Item 1A from multiple companies

    Args:
        tickers: List of stock tickers

    Returns:
        DataFrame with extracted data
    """
    results = []

    for ticker in tickers:
        print(f"\n{'='*60}")
        print(f"Processing: {ticker}")
        print(f"{'='*60}")

        data = extract_item_1a_edgartools(ticker)
        if data:
            results.append(data)
            print(f"✅ Extracted {data['num_words']:,} words from Item 1A")
        else:
            print(f"⚠️  Skipped {ticker}")

    # Convert to DataFrame
    df = pd.DataFrame(results)
    return df


def compare_with_our_script(edgartools_result: dict) -> dict:
    """
    Compare EdgarTools extraction with our custom script

    Args:
        edgartools_result: Result from EdgarTools extraction

    Returns:
        Comparison metrics
    """
    if not edgartools_result:
        return None

    comparison = {
        "source": "EdgarTools",
        "cik": edgartools_result["cik"],
        "filed_date": edgartools_result["filed_date"],
        "item_1a_length": len(edgartools_result["item_1a_content"]),
        "num_words": edgartools_result["num_words"],
        "extraction_success": edgartools_result["item_1a_content"] is not None,
    }

    return comparison


# ==============================================================================
# Example Usage
# ==============================================================================

if __name__ == "__main__":
    print("🚀 EdgarTools Item 1A Extraction Example")
    print("=" * 60)

    # Single company extraction
    print("\n📊 Single Company Example:")
    print("-" * 60)
    result = extract_item_1a_edgartools("MSFT")

    if result:
        print(f"\n✅ Results:")
        print(f"  CIK: {result['cik']}")
        print(f"  Filed: {result['filed_date']}")
        print(f"  Words: {result['num_words']:,}")
        print(f"\n  Content preview (first 500 chars):")
        print(f"  {result['item_1a_content'][:500]}...")

        # Show comparison metrics
        comparison = compare_with_our_script(result)
        print(f"\n📈 Comparison Metrics:")
        for key, value in comparison.items():
            print(f"  {key}: {value}")

    # Batch extraction (commented out - takes longer)
    """
    print("\n\n📊 Batch Processing Example:")
    print("-" * 60)
    tickers = ["MSFT", "AAPL", "GOOGL", "AMZN"]
    df = batch_extract_edgartools(tickers)

    print(f"\n✅ Extracted {len(df)} filings:")
    print(df[["ticker", "cik", "filed_date", "num_words"]])

    # Save to CSV
    df.to_csv("edgartools_results.csv", index=False)
    print("\n💾 Results saved to edgartools_results.csv")
    """

    print("\n" + "=" * 60)
    print("✅ EdgarTools example complete!")
    print("\nNotes:")
    print("- EdgarTools downloads filing from EDGAR (~30s first time)")
    print("- Subsequent calls use local cache")
    print("- Risk Factors (Item 1A) accessed via tenk.risk_factors")
    print("- Other items: tenk.business, tenk.risk_factors, etc.")
