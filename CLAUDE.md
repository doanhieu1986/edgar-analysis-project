# CLAUDE.md - Project Collaboration Guide

## 📌 Project Overview

**edgar-analysis-project** - SEC 10-K Form Analysis & Data Extraction

Tool để chiết xuất, phân tích, và lưu trữ dữ liệu từ file báo cáo 10-K của SEC (US Securities and Exchange Commission).

---

## 📂 Project Structure

```
edgar-analysis-project/
├── CLAUDE.md                           # This file - collaboration guidelines
├── .gitignore                          # Ignore all dot-prefixed folders (.*/）
├── scripts/
│   ├── extract_item.py                 # Main script - Item extraction & Parquet export
│   ├── run_test.py                     # Utility - View Parquet DataFrame
│   ├── README.md                       # Scripts usage guide
│   └── LOGIC_AND_DATAFLOW.md           # Detailed logic & data flow documentation
├── outputs/                            # Output directory (auto-created)
│   ├── 2024_data.parquet              # Example: Year-grouped parquet files
│   └── 2023_data.parquet
├── 20240102_10-K_edgar_data_*.txt     # Sample 10-K files (for testing)
└── [input files...]
```

---

## 🎯 Core Functionality

### Extract Item Mode
- Extract specific Items (1A, 7, 9A, etc.) from 10-K text files
- List all Items in a file
- Save extracted content as text files
- Command: `python scripts/extract_item.py <file> <item_id> [--output]`

### Parquet Mode (Batch Processing)
- Process single file or directory of 10-K files
- Extract metadata: CIK, filed_date, form_type, conformed_period
- Extract Items 1A and 7 content
- Save to Parquet format, organized by year (from filed_date)
- Command: `python scripts/extract_item.py <file_or_dir> --parquet`

### View Results
- Display Parquet data as DataFrame
- Command: `python scripts/run_test.py`

---

## 🔑 Key Files & Responsibilities

| File | Purpose | Modify When |
|------|---------|-------------|
| `scripts/extract_item.py` | Main extraction logic | Adding features, fixing bugs, improving regex patterns |
| `scripts/run_test.py` | Data visualization | Changing output format, adding new views |
| `scripts/LOGIC_AND_DATAFLOW.md` | Documentation | Logic changes, new functions, flow updates |
| `scripts/README.md` | Usage guide | Adding commands, new features |
| `.gitignore` | Version control rules | Changing what files to ignore |

---

## ⚙️ Development Guidelines

### Code Style
- **Language**: Python 3.9+
- **Type hints**: Use `str | None` for union types (Python 3.10+ syntax)
- **Imports**: Group as imports, datetime, pathlib, then 3rd party (pandas), then local
- **Naming**: Snake_case for functions/variables, UPPER_CASE for constants
- **Comments**: Only for non-obvious logic, not for every line

### Key Functions

#### `extract_item(text: str, item_id: str) -> str | None`
- Finds Item by ID, returns content from Item header to next Item (or EOF)
- Used for both single extraction and batch processing
- **Don't change**: Core regex pattern without testing against sample files

#### `extract_metadata(text: str) -> Dict[str, Any]`
- Extracts SEC header fields: cik, filed_date, form_type, conformed_period
- **Year extraction**: Always from filed_date (first 4 chars), not conformed_period
- Returns dict with keys: cik, filed_date, form_type, conformed_period, year

#### `process_files_to_parquet(file_or_dir: Path) -> None`
- Batch processes 10-K files
- Groups by year (from filed_date)
- Saves as `outputs/{year}_data.parquet`
- **Important**: One file per year (multiple records if needed)

### Regular Expressions
- Item pattern: `^Item\s+(\d+[A-Z]?)\s*[.\-:]?\s*.+$` (MULTILINE)
- SEC header patterns: Case-insensitive, match after colon
- Always test against actual 10-K files before deploying

### Output Format (Parquet)
**Column order** (DO NOT change):
1. year
2. filename
3. cik
4. filed_date
5. form_type
6. conformed_period
7. item_1a
8. item_7

**Naming**: `{year}_data.parquet` (e.g., 2024_data.parquet)

---

## 📊 Data Flow Summary

```
Input File (10-K text)
    ↓
extract_metadata() → {cik, filed_date, year, ...}
    ↓
extract_item(text, "1A") → Item 1A content
extract_item(text, "7") → Item 7 content
    ↓
DataFrame row: {year, filename, cik, ..., item_1a, item_7}
    ↓
process_files_to_parquet() → Group by year
    ↓
outputs/{year}_data.parquet
```

---

## 🧪 Testing & Validation

### Sample Files
- File: `20240102_10-K_edgar_data_90168_0000090168-23-000083.txt`
- Company: SIFCO INDUSTRIES INC
- CIK: 0000090168
- Filed Date: 20240102 (Year: 2024)
- Conformed Period: 20230930

### Test Commands
```bash
# List all Items
python scripts/extract_item.py 20240102_10-K_edgar_data_90168_0000090168-23-000083.txt --list

# Extract Item 1A
python scripts/extract_item.py 20240102_10-K_edgar_data_90168_0000090168-23-000083.txt "1A"

# Batch process to Parquet
python scripts/extract_item.py . --parquet

# View Parquet results
python scripts/run_test.py
```

### Expected Behavior
- ✅ Item 1A: ~50K characters (Risk Factors)
- ✅ Item 7: ~47K characters (MD&A)
- ✅ Parquet file: ~50 KB (with full text content)
- ✅ Year extracted: 2024 (from filed_date 20240102)

---

## 📚 Dependencies

### Required
- `pandas` - DataFrame operations, Parquet I/O
- `pyarrow` - Parquet backend

### Built-in
- `re` - Regular expressions
- `sys` - System utilities
- `argparse` - CLI argument parsing
- `pathlib` - File path operations

### Installation
```bash
pip install pandas pyarrow
```

---

## 🚫 What NOT to Do

1. **Don't change parquet column order** - Output stability depends on this
2. **Don't use conformed_period for year** - Always extract from filed_date
3. **Don't remove regex MULTILINE flag** - Item detection breaks without it
4. **Don't hardcode file paths** - Use Path() and arguments
5. **Don't commit parquet files** - They're in .gitignore (use --parquet to regenerate)
6. **Don't change regex patterns without testing** - Test on actual 10-K files

---

## ✅ Common Tasks

### Add Support for New Item
1. Update `extract_item()` logic if needed (usually no change required)
2. In `process_files_to_parquet()`, add new line:
   ```python
   "item_X": extract_item(text, "X"),
   ```
3. Update parquet column order in documentation
4. Update LOGIC_AND_DATAFLOW.md with new field

### Add New CLI Flag
1. Add to argparse in `main()`
2. Implement corresponding logic
3. Update README.md with examples
4. Update LOGIC_AND_DATAFLOW.md scenarios

### Fix Metadata Extraction
1. Check regex pattern in `extract_metadata()`
2. Test with actual SEC header samples
3. Verify output dict structure
4. Update documentation if pattern changes

---

## 🔍 Debugging Tips

### Item Not Found
- Run `--list` to verify Item exists in file
- Check Item ID capitalization (1A vs 1a)
- Verify file encoding (should be UTF-8)

### Wrong Year in Parquet
- Check filed_date extraction in `extract_metadata()`
- Verify filed_date is YYYYMMDD format
- Year should be filed_date[:4], not conformed_period[:4]

### Parquet File Corrupt
- Delete outputs/ and regenerate with `--parquet`
- Check for file I/O errors during writing
- Verify pandas/pyarrow installed correctly

---

## 📖 Documentation

- **README.md** - Quick start & usage examples
- **LOGIC_AND_DATAFLOW.md** - Detailed function documentation, data flow diagrams, regex patterns
- **This file (CLAUDE.md)** - Collaboration guidelines & project context

When updating code:
1. Keep LOGIC_AND_DATAFLOW.md in sync with function logic
2. Update README.md with new CLI commands/features
3. Add/update docstrings in code for complex functions

---

## 🎯 Current Status (as of 2026-04-08)

### Completed Features
- ✅ Extract specific Items from 10-K files
- ✅ List all Items in a file
- ✅ Extract & save Item as text file
- ✅ Extract metadata from SEC header (CIK, filed_date, form_type)
- ✅ Batch process multiple 10-K files
- ✅ Export to Parquet format
- ✅ Organize output by year (from filed_date)
- ✅ View Parquet data as DataFrame

### Next Potential Enhancements
- [ ] Add support for other form types (10-Q, 8-K, etc.)
- [ ] Add Item filtering/search functionality
- [ ] Add CSV export option
- [ ] Add data validation/cleanup
- [ ] Add performance metrics

---

## 📞 Questions?

Refer to:
- `scripts/LOGIC_AND_DATAFLOW.md` for technical details
- `scripts/README.md` for usage examples
- Test with sample 10-K file in project root
