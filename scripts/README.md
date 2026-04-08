# Scripts - SEC 10-K Item Extraction

Folder chứa các tools để xử lý và phân tích file báo cáo 10-K của SEC.

## 📂 Files

- **`extract_item.py`** - Script Python chiết xuất Items từ file 10-K
- **`LOGIC_AND_DATAFLOW.md`** - Mô tả chi tiết logic xử lý & data flow (có diagram Mermaid)

## 🚀 Quick Start

```bash
# Liệt kê tất cả Items
python extract_item.py <10-K file> --list

# Chiết xuất Item cụ thể
python extract_item.py <10-K file> "1A"

# Chiết xuất & lưu vào file
python extract_item.py <10-K file> "7" --output item_7.txt
```

## 📖 Chi tiết

Xem **`LOGIC_AND_DATAFLOW.md`** để:
- ✅ Hiểu logic từng hàm
- 📊 Xem diagram data flow (Mermaid)
- 🔄 Theo dõi flow xử lý dữ liệu
- 🛠️ Tìm hiểu regex patterns
- 📈 Xem performance notes
