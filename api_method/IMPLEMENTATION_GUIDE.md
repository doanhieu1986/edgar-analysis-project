# Implementation Guide: Alternative SEC 10-K Extraction Methods

**Date**: 2026-04-10  
**Purpose**: Step-by-step guides for integrating alternative extraction methods

---

## 📋 Table of Contents

1. [EdgarTools Integration](#edgartools-integration)
2. [sec-api.io Integration](#sec-appio-integration)
3. [Migration Strategy](#migration-strategy)
4. [Testing & Validation](#testing--validation)

---

## EdgarTools Integration

### Installation

```bash
# Install EdgarTools
pip install edgartools

# Optional: For development
pip install -e .
```

### Setup (No API Key Required)

EdgarTools downloads filings directly from SEC EDGAR. No authentication needed.

```python
from edgar import Company

# Create company object (automatically finds latest filings)
company = Company("MSFT")

# Access 10-K filing
tenk = company.latest_10k()

# Get Item 1A
risk_factors = tenk.risk_factors
```

### Integration with Our Parquet Pipeline

```python
"""
Integration: EdgarTools + Our Parquet Export
"""

import pandas as pd
from pathlib import Path
from edgar import Company
from datetime import datetime

def extract_with_edgartools(ticker: str, years: int = 5) -> list[dict]:
    """
    Extract Item 1A using EdgarTools
    Returns format compatible with our parquet pipeline
    """
    results = []
    
    try:
        company = Company(ticker)
        filings = company.get_filings(form="10-K", limit=years)
        
        for filing in filings:
            try:
                item_1a = filing.risk_factors
                
                if item_1a:
                    row = {
                        "year": filing.filing_date.year,
                        "quarter": None,  # EdgarTools doesn't provide quarter
                        "filename": f"{ticker}_{filing.filing_date.strftime('%Y%m%d')}_10-K",
                        "cik": filing.cik,
                        "filed_date": filing.filing_date.strftime("%Y%m%d"),
                        "form_type": "10-K",
                        "conformed_period": filing.period_of_report.strftime("%Y%m%d"),
                        "item_1a": item_1a,
                    }
                    results.append(row)
            except Exception as e:
                print(f"  Error extracting {filing.filing_date}: {e}")
                continue
                
    except Exception as e:
        print(f"❌ Error with {ticker}: {e}")
    
    return results


def save_to_parquet_edgartools(tickers: list[str], output_dir: Path = Path("outputs")):
    """
    Batch extract with EdgarTools and save to parquet
    """
    data_by_year = {}
    
    for ticker in tickers:
        print(f"Extracting {ticker}...")
        rows = extract_with_edgartools(ticker)
        
        for row in rows:
            year = row["year"]
            if year not in data_by_year:
                data_by_year[year] = []
            data_by_year[year].append(row)
    
    # Save to parquet
    for year, rows in data_by_year.items():
        df = pd.DataFrame(rows)
        output_path = output_dir / f"{year}_data_edgartools.parquet"
        df.to_parquet(output_path)
        print(f"Saved {len(rows)} records to {output_path}")


# Usage
if __name__ == "__main__":
    tickers = ["MSFT", "AAPL", "GOOGL"]
    save_to_parquet_edgartools(tickers)
```

### Advantages Over Our Script

| Aspect | EdgarTools | Our Script |
|--------|-----------|-----------|
| Setup | No API key | Already working |
| Code | Simple (1 line) | Custom parsing |
| Maintenance | Maintained by community | Manual updates needed |
| Error handling | Built-in | Manual |
| Other items | Easy access | Custom parsing |

### When to Use EdgarTools

✅ **Use EdgarTools if**:
- Need to extract multiple item types (1A, 7, 9A, etc.)
- Want structured financial data (XBRL)
- Want automatic error handling & retries
- Don't need microsecond performance

❌ **Keep our script if**:
- Only need Item 1A
- Need maximum speed (25ms per file)
- Already invested in current solution
- Prefer no external dependencies

---

## sec-api.io Integration

### Installation & Setup

```bash
# Install sec-api
pip install sec-api

# Get API key
# 1. Go to https://sec-api.io/
# 2. Sign up (free tier: 100 requests/month)
# 3. Copy API key

# Set environment variable
export SEC_API_KEY="your-api-key"
```

### Basic Usage

```python
from sec_api import QueryApi, ExtractorApi

# Initialize clients
query_api = QueryApi("your-api-key")
extractor = ExtractorApi("your-api-key")

# Search for 10-K
filings = query_api.get_filings(
    query='ticker:"MSFT" AND formType:"10-K"',
    from_=0,
    size=10,
    sort=[{"filedAt": {"order": "desc"}}]
)

# Extract Item 1A from latest filing
latest_filing = filings["filings"][0]
accession = latest_filing["accessionNumber"]
filing_url = latest_filing["linkToFilingDetails"]

item_1a = extractor.get_section(
    filing_url,
    section="1A",
    return_type="text"
)
```

### Integration with Our Parquet Pipeline

```python
"""
Integration: sec-api.io + Our Parquet Export
"""

import pandas as pd
import os
from pathlib import Path
from sec_api import QueryApi, ExtractorApi

class SecApiParquetExporter:
    """Export sec-api.io Item 1A to our parquet format"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("SEC_API_KEY")
        self.query_api = QueryApi(self.api_key)
        self.extractor = ExtractorApi(self.api_key)
        self.api_calls = 0
        
    def extract_ticker(self, ticker: str, years: int = 5) -> list[dict]:
        """Extract Item 1A for a ticker"""
        results = []
        
        try:
            # Search for 10-K filings
            filings = self.query_api.get_filings(
                query=f'ticker:"{ticker}" AND formType:"10-K"',
                from_=0,
                size=years,
                sort=[{"filedAt": {"order": "desc"}}]
            )
            
            for filing in filings.get("filings", []):
                try:
                    # Extract Item 1A
                    item_1a = self.extractor.get_section(
                        filing["linkToFilingDetails"],
                        section="1A",
                        return_type="text"
                    )
                    self.api_calls += 1
                    
                    if item_1a:
                        # Parse filing date
                        filed_date = filing["filedAt"].split("T")[0].replace("-", "")
                        
                        row = {
                            "year": int(filed_date[:4]),
                            "quarter": None,
                            "filename": f"{ticker}_{filed_date}_10-K",
                            "cik": filing["cik"],
                            "filed_date": filed_date,
                            "form_type": "10-K",
                            "conformed_period": filing.get("periodOfReport", "").replace("-", ""),
                            "item_1a": item_1a,
                        }
                        results.append(row)
                        
                except Exception as e:
                    print(f"  Error extracting {filing['filedAt']}: {e}")
                    continue
                    
        except Exception as e:
            print(f"❌ Error with {ticker}: {e}")
        
        return results
    
    def export_to_parquet(self, tickers: list[str], output_dir: Path = Path("outputs")):
        """Export all results to parquet files"""
        data_by_year = {}
        
        for ticker in tickers:
            print(f"Extracting {ticker}... (API calls: {self.api_calls}/100)")
            rows = self.extract_ticker(ticker)
            
            if self.api_calls > 95:
                print("⚠️  Approaching free tier limit (100/month)")
                break
            
            for row in rows:
                year = row["year"]
                if year not in data_by_year:
                    data_by_year[year] = []
                data_by_year[year].append(row)
        
        # Save parquet files
        output_dir.mkdir(exist_ok=True)
        for year, rows in data_by_year.items():
            df = pd.DataFrame(rows)
            output_path = output_dir / f"{year}_data_secapi.parquet"
            df.to_parquet(output_path)
            print(f"Saved {len(rows)} records to {output_path}")
        
        print(f"\n📊 Stats:")
        print(f"  Total API calls: {self.api_calls}/100 (free tier)")
        print(f"  Cost estimate: ${self.api_calls * 0.005:.2f} at Pro tier rates")


# Usage
if __name__ == "__main__":
    exporter = SecApiParquetExporter()
    tickers = ["MSFT", "AAPL"]  # Free tier: ~50 calls per ticker
    exporter.export_to_parquet(tickers)
```

### Cost Considerations

```
Free Tier:
  - 100 requests/month
  - Perfect for ~50 companies
  
Pro Tier ($199/month):
  - Unlimited requests
  - Real-time stream API
  - Full-text search
  - Priority support

Enterprise:
  - Custom pricing
  - SLA guarantees
  - Dedicated support
```

### When to Use sec-api

✅ **Use sec-api if**:
- Need real-time monitoring of new filings (300ms)
- Building production SaaS application
- Need professional-grade accuracy (99.2%)
- Want audit trail for compliance
- Budget for API costs

❌ **Keep our script if**:
- Processing fixed batch of files
- Cost-sensitive (free is better than $200+/month)
- Don't need real-time capability
- Like to keep code fully self-contained

---

## Migration Strategy

### Phase 1: Parallel Testing (Low Risk)

```python
"""
Run both methods in parallel to validate accuracy
"""

def test_parallel_extraction(file_path: str):
    """Compare our script vs EdgarTools vs sec-api"""
    
    text = Path(file_path).read_text()
    
    # Method 1: Our script
    our_result = extract_item(text, "1A")
    
    # Method 2: EdgarTools (if we have ticker)
    # edgartools_result = company.latest_10k().risk_factors
    
    # Method 3: sec-api (if we have accession number)
    # secapi_result = extractor.get_section(url, "1A")
    
    # Compare lengths
    print(f"Our script:  {len(our_result or ''):,} chars")
    # print(f"EdgarTools:  {len(edgartools_result):,} chars")
    # print(f"sec-api:     {len(secapi_result):,} chars")
    
    # Measure differences
    # if our_result != edgartools_result:
    #     print("⚠️  Results differ!")
```

### Phase 2: Hybrid Approach

```python
"""
Use our script as primary, EdgarTools/sec-api as fallback
"""

def extract_item_hybrid(file_path: str, item_id: str, ticker: str = None):
    """
    Try our script first, fallback to EdgarTools if needed
    """
    
    # Try our script
    text = Path(file_path).read_text()
    result = extract_item(text, item_id)
    
    if result and len(result) > 100:  # Sufficient content
        return result, "our_script"
    
    # Fallback to EdgarTools if available
    if ticker:
        try:
            company = Company(ticker)
            tenk = company.latest_10k()
            if item_id == "1A":
                result = tenk.risk_factors
                return result, "edgartools"
        except:
            pass
    
    # No fallback succeeded
    return None, "failed"
```

### Phase 3: Full Migration (If Needed)

If deciding to fully migrate to a library:

1. **Choose library**: EdgarTools (free) or sec-api (production)
2. **Rewrite extract function** to use library API
3. **Update parquet export** to match new data format
4. **Run full test** on sample of files (100+ files)
5. **Compare metrics**: Speed, accuracy, cost
6. **Commit changes** to git
7. **Archive our_script** in git history (never delete)

---

## Testing & Validation

### Accuracy Test

```python
"""
Compare accuracy of different methods on sample files
"""

def test_accuracy(sample_files: list[str]):
    """Test all methods on sample files"""
    
    results = {}
    
    for file_path in sample_files:
        text = Path(file_path).read_text()
        
        # Our script
        our_item = extract_item(text, "1A")
        
        # Metrics
        results[Path(file_path).name] = {
            "our_script_words": len(our_item.split()) if our_item else 0,
            "our_script_chars": len(our_item or ""),
            "found": bool(our_item),
        }
    
    # Summary
    found = sum(1 for r in results.values() if r["found"])
    print(f"✅ Accuracy: {found}/{len(results)} ({100*found//len(results)}%)")
    
    return results
```

### Performance Benchmark

```python
"""
Benchmark extraction speed
"""

import time

def benchmark_extraction(file_paths: list[str], method: str = "our_script"):
    """Measure extraction speed"""
    
    start = time.perf_counter()
    
    for file_path in file_paths:
        if method == "our_script":
            text = Path(file_path).read_text()
            extract_item(text, "1A")
        # Add other methods...
    
    elapsed = time.perf_counter() - start
    per_file = elapsed / len(file_paths) * 1000
    
    print(f"{method}:")
    print(f"  Total: {elapsed:.2f}s")
    print(f"  Per file: {per_file:.1f}ms")
    print(f"  Throughput: {len(file_paths)/elapsed:.1f} files/sec")
```

---

## Recommendations Summary

| Method | Best For | Effort | Cost | Speed |
|--------|----------|--------|------|-------|
| **Our Script** | Batch processing | 0 | $0 | ⭐⭐⭐⭐⭐ |
| **EdgarTools** | Structured API | 2h | $0 | ⭐⭐⭐ |
| **sec-api** | Real-time | 3h | $200-1000 | ⭐⭐⭐⭐ |

**For now**: Keep using our optimized script. It's battle-tested on 6,878 files.

**For future expansion**: Consider EdgarTools if you need to extract multiple item types or handle error cases more gracefully.

**For production SaaS**: Use sec-api.io when you need real-time capability and have budget for it.

---

## References

- [EdgarTools Documentation](https://edgartools.readthedocs.io/)
- [sec-api.io Documentation](https://sec-api.io/docs)
- [Official SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
