# Scripts - SEC 10-K Item Extraction & Analysis

Folder chứa các tools để xử lý, phân tích và lưu trữ file báo cáo 10-K của SEC.

## 📂 Files

- **`extract_item.py`** - Script Python chiết xuất Items & metadata từ file 10-K, xuất Parquet
- **`run_test.py`** - Script xem dữ liệu Parquet dưới dạng DataFrame
- **`LOGIC_AND_DATAFLOW.md`** - Mô tả chi tiết logic xử lý & data flow (có diagram Mermaid)
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

## 📊 Output Parquet Format

**Cột (theo thứ tự)**:
1. `year` - Năm từ filed_date (ví dụ: 2024)
2. `quarter` - Quý từ folder path (ví dụ: QTR1, QTR2, QTR3, QTR4) - hoặc null nếu không trong subfolder
3. `filename` - Tên file gốc
4. `cik` - CENTRAL INDEX KEY
5. `filed_date` - FILED AS OF DATE (YYYYMMDD)
6. `form_type` - CONFORMED SUBMISSION TYPE
7. `conformed_period` - CONFORMED PERIOD OF REPORT (YYYYMMDD)
8. `item_1a` - Nội dung Item 1A (Risk Factors) - full text
9. `item_7` - Nội dung Item 7 (MD&A) - full text

**File output**:
- Lưu trong thư mục `outputs/`
- Tên file: `{year}_data.parquet` (ví dụ: `2024_data.parquet`, `2023_data.parquet`)
- Nếu có nhiều file cùng năm, dữ liệu được gộp vào cùng một parquet file

## 📖 Chi tiết

Xem **`LOGIC_AND_DATAFLOW.md`** để:
- ✅ Hiểu logic từng hàm (kể cả hàm mới: `extract_metadata`, `process_files_to_parquet`)
- 📊 Xem diagram data flow (Mermaid)
- 🔄 Theo dõi flow xử lý dữ liệu
- 🛠️ Tìm hiểu regex patterns
- 📈 Xem performance notes
