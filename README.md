# USB PD Parser 🔌📄

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)

A lightweight tool to parse **USB Power Delivery Specification PDFs** into structured data.  
The parser extracts **sections, titles, hierarchy, page numbers, and tags**, and exports results into **Excel** and **JSON** formats for further analysis.

---

## ✨ Features
- 📑 Extracts section hierarchy (with parent-child relationships)  
- 📊 Export results to **Excel (.xlsx)** and **JSON (.json)**  
- 🏷️ Captures metadata like page numbers, titles, and tags  
- 🧪 Includes unit tests with **pytest**  
- ⚡ Simple **command-line interface (CLI)**  

---

## 📦 Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/your-username/usb-pd-parser.git
   cd usb-pd-parser
Create a virtual environment (recommended):

bash
Copy code
python -m venv venv
source venv/bin/activate   # Linux / macOS
venv\Scripts\activate      # Windows
Install dependencies:

bash
Copy code
pip install -r requirements.txt
🚀 Usage
Run the parser with a USB PD specification PDF:

bash
Copy code
python main.py --pdf "USB_PD_R3_2 V1.1 2024-10.pdf" --out results/ --format excel,json
CLI Options
Option	Description
--pdf	Input PDF file path
--out	Output directory (created if missing)
--format	Export formats (comma-separated: excel,json)

Example Output
results/usb_pd_results.xlsx

results/usb_pd_results.json

🧪 Running Tests
Run all unit tests with pytest:

bash
Copy code
pytest -q
Expected output (when all tests pass):

python-repl
Copy code
...                                                                 [100%]
3 passed in 1.20s
📂 Project Structure
bash
Copy code
usb_pd_parser_final_v2/
│── usb_pd_parser/
│   ├── exporters/        # JSON & Excel export logic
│   ├── parsers/          # Section parser implementation
│   └── utils/            # Helper utilities
│
│── tests/                # Unit tests
│── main.py               # CLI entry point
│── requirements.txt      # Dependencies
│── README.md             # Project documentation