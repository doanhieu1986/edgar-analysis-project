# Scripts - SEC 10-K Item Extraction & Analysis

Folder chứa các tools để xử lý, phân tích và lưu trữ file báo cáo 10-K của SEC.

## 📂 Files

- **`extract_item.py`** - Script Python chiết xuất Items & metadata từ file 10-K, xuất Parquet (with multi-step validation)
- **`preprocess.py`** - Script tiền xử lý dữ liệu: merge, clean text cho training
- **`run_test.py`** - Script xem dữ liệu Parquet dưới dạng DataFrame
- **`LOGIC_AND_DATAFLOW.md`** - Mô tả chi tiết logic xử lý & data flow (có diagram Mermaid, validation details)
- **`README.md`** - File này

## 🚀 Quick Start

### Chế độ chiết xuất đơn lẻ (Legacy mode)
```bash
# Liệt kê tất cả Items
python extract_item.py <10-K file> --list

# Chiết xuất Item cụ thể
python extract_item.py <10-K file> "1A"

# Chiết xuất & lưu vào file text
python extract_item.py <10-K file> "7" --output item_7.txt
```

### Chế độ Parquet (Batch processing)
```bash
# Chạy mà không có argument → tự động xử lý tất cả file từ ../.sources_data
python extract_item.py

# Xử lý một file duy nhất
python extract_item.py file.txt --parquet

# Xử lý tất cả file 10-K trong thư mục
python extract_item.py /path/to/10k/files --parquet

# Kết quả: outputs/2024_data.parquet (nếu filed_date năm 2024)
```

### Xem kết quả Parquet
```bash
# Xem dữ liệu DataFrame
python run_test.py
```

### Data Preprocessing (Giai đoạn 2)
```bash
# Bước 1: Gộp tất cả {year}_data.parquet → combined_data.parquet
python preprocess.py merge

# Bước 2: Clean text item_1a → cleaned_data.parquet
python preprocess.py clean

# Chạy cả 2 bước liên tiếp
python preprocess.py all

# Tùy chỉnh min length và output path
python preprocess.py clean --min-len 500 --output outputs/cleaned_500.parquet
```

## 📊 Output Parquet Format

### Giai đoạn 1 — Extraction (`{year}_data.parquet`)
**Cột (theo thứ tự)**:
1. `year` - Năm từ filed_date (ví dụ: 2024)
2. `quarter` - Quý từ folder path (ví dụ: QTR1, QTR2, QTR3, QTR4) - hoặc null nếu không trong subfolder
3. `filename` - Tên file gốc
4. `cik` - CENTRAL INDEX KEY
5. `filed_date` - FILED AS OF DATE (YYYYMMDD)
6. `form_type` - CONFORMED SUBMISSION TYPE
7. `conformed_period` - CONFORMED PERIOD OF REPORT (YYYYMMDD)
8. `item_1a` - Nội dung Item 1A (Risk Factors) - raw text

**File output**:
- Lưu trong thư mục `outputs/`
- Tên file: `{year}_data.parquet` (ví dụ: `2024_data.parquet`, `2023_data.parquet`)
- Nếu có nhiều file cùng năm, dữ liệu được gộp vào cùng một parquet file

### Giai đoạn 2 — Preprocessing (`combined_data.parquet`, `cleaned_data.parquet`)

**`combined_data.parquet`** — Gộp tất cả năm:
- Cùng 8 cột như trên, 225,220 rows (1993–2024)

**`cleaned_data.parquet`** — Sau khi clean:
- Thêm cột `item_1a_clean` (text đã xử lý)
- Đã loại bỏ: null + texts < 200 chars (garbage extractions)
- `item_1a_clean`: stripped header + normalized whitespace
- 64,330 rows còn lại (từ 225,220 ban đầu)

## 🔧 Multi-Step Validation for Item 1A Extraction

Extract_item.py sử dụng **three-phase validation** để xử lý các edge cases:

1. **Phase 1 - Normalize Line-Wrapped Items**
   - Chuyển "Item\n1A.\nRisk" → "Item 1A. Risk"
   - Xử lý File 8 format đặc biệt
   - Hỗ trợ format "1A. Risk" không có "Item" keyword

2. **Phase 2 - Remove Table of Contents**
   - Phát hiện ToC section bằng keyword matching ("Table of Contents", "PART I")
   - Loại bỏ ToC để tránh false matches
   - Xử lý files không có ToC (optional)

3. **Phase 3 - Multi-Level Header Validation**
   - Skip matches trong ToC region
   - Skip ToC entries (có page numbers)
   - Skip Item references (in Item, See Item, Part I,...)
   - Tìm first valid Item header

**Kết quả**: ✅ 98.3% Item 1A extraction rate trên 6,878 files

## 📊 Performance Results

- **Batch Processing**: 6,878 files in ~4.5 minutes
- **Throughput**: 26.3 files/second
- **Per-file Average**: 37.3 ms
- **Success Rate**: 100% (no failures)

## 📖 Chi tiết

Xem **`LOGIC_AND_DATAFLOW.md`** để:
- ✅ Hiểu logic từng hàm (kể cả helper functions: `detect_toc_section`, `normalize_line_wrapped_items`, `is_toc_entry_not_header`, `is_reference_not_header`, `find_item_position`)
- 📊 Xem diagram data flow (Mermaid)
- 🔄 Theo dõi flow xử lý dữ liệu
- 🛠️ Tìm hiểu regex patterns
- 📈 Xem performance analysis & validation results
