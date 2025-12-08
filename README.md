USB Power Delivery (USB-PD) Specification Parser

A **production-ready, Python-only PDF parser** designed to extract **Table of Contents (TOC), structured Sections, Tables, Figures, Images, and Validation Reports** from large technical PDF documents like the **USB PD Specification Rev 3.2 v1.1**.

This tool generates:
- ✅ Structured **JSONL datasets**
- ✅ Extracted **figure images**
- ✅ **Excel validation report**
- ✅ **Detailed runtime logs**
- ✅ **CPU & Memory performance tracking using multithreading**

---

## 🚀 Features

- ✅ TOC (Table of Contents) extraction  
- ✅ Hierarchical **section detection**
- ✅ Table detection using **Camelot**
- ✅ Figure caption detection
- ✅ Automatic **figure image extraction**
- ✅ Section → Table / Figure linking via `parent_id`
- ✅ JSONL output for:
  - Sections
  - Tables
  - Figures
  - Metadata
  - TOC
- ✅ **Excel validation report** (TOC vs extracted sections)
- ✅ **Multithreaded performance logger** (CPU & RAM)
- ✅ **Automatic log management in `/LOG` folder**
- ✅ Smart:
  - Footer removal
  - Dot-leader cleanup
  - Broken line fix
  - Orphan text filtering

---

## 🧠 Technology Stack

| Component | Library |
|----------|----------|
| PDF Text Extraction | `pdfplumber` |
| Image Extraction | `PyMuPDF (fitz)` |
| Table Extraction | `camelot` |
| Performance Monitoring | `psutil` |
| Excel Export | `pandas` |
| Image Handling | `Pillow` |
| Logging | `logging` |
| Multithreading | `threading` |

✅ **100% Python — No Java, No Tabula**

---

## 📦 Installation

### 1️⃣ Create Virtual Environment (Recommended)

```bash
python -m venv venv
source venv/bin/activate   # Linux / Mac
venv\Scripts\activate      # Windows
2️⃣ Install Required Dependencies
bash
Copy code
pip install pdfplumber pymupdf psutil pandas pillow camelot-py tqdm
⚠️ Camelot may require:

ghostscript

opencv-python

▶️ How to Run the Parser
bash
Copy code
python parser.py --pdf "USB_PD_Spec.pdf" --title "USB PD Rev 3.2 v1.1" --start-page 34 --output output
CLI Arguments
Argument	Description
--pdf	Path to PDF file
--title	Document title
--start-page	Page where specification starts (default: 34)
--output	Output folder name

📁 Output Folder Structure
lua
Copy code
output/
│
├── usb_pd_sections.jsonl
├── usb_pd_tables.jsonl
├── usb_pd_figures.jsonl
├── usb_pd_toc.jsonl
├── usb_pd_metadata.jsonl
├── Validation.xlsx
│
├── figures/
│   ├── Figure_5.2_page_87_crop.png
│   ├── Figure_6.4_page_142_crop.png
│
├── LOG/
│   ├── parser_20251208_164233.log
│   ├── performance.log
📄 Output File Descriptions
File	Purpose
usb_pd_sections.jsonl	All detected document sections
usb_pd_tables.jsonl	Extracted tables
usb_pd_figures.jsonl	Figure metadata
usb_pd_toc.jsonl	Table of contents
usb_pd_metadata.jsonl	Final summary metadata
Validation.xlsx	TOC vs Section comparison
figures/	Cropped figure images
LOG/parser_*.log	Full execution logs
LOG/performance.log	CPU & Memory usage (10s interval)

⚙️ Performance Monitoring (Multithreading)
CPU usage logged every 10 seconds

Memory usage per process

Runs in parallel without slowing extraction

Output format:

sql
Copy code
timestamp,cpu_percent,memory_mb
2025-12-08 16:40:10,27.8,192.50
📊 Validation Report (Excel)
The script automatically compares:

✅ TOC sections vs Parsed sections

Output file:

lua
Copy code
output/Validation.xlsx
Metrics:

Total TOC entries

Total extracted sections

Missing sections

Extra sections

🛡 Stability & Fault Tolerance
✔ Works even if:

camelot is unavailable

fitz is missing

psutil is missing

✔ Safe fallback handling

✔ Memory-safe streaming

✔ Crash-protected with exception logging

🧪 Tested Use Cases
USB PD Specification (2000+ pages)

Hardware Interface Standards

Semiconductor Protocol Specs

Engineering Reference Manuals