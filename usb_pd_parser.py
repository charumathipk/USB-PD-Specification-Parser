#!/usr/bin/env python3
import re
import os
import sys
import time
import json
import argparse
import logging
import traceback
import threading
from datetime import datetime

# third-party libs
try:
    import pdfplumber
except Exception as e:
    print("Missing pdfplumber. Install: pip install pdfplumber")
    raise

try:
    import fitz  # PyMuPDF
except Exception as e:
    fitz = None

try:
    import psutil
except Exception:
    psutil = None

try:
    import pandas as pd
except Exception:
    pd = None

try:
    from PIL import Image
except Exception:
    Image = None

# camelot might not be available on all systems - attempt to import
try:
    import camelot
except Exception:
    camelot = None

# tqdm optional
try:
    from tqdm import tqdm
except Exception:
    tqdm = None

# ----------------------------
# Configuration / Regexes
# ----------------------------
FOOTER_PATTERNS = [
    # "Page 34 Universal Serial Bus Power Delivery Specification, Revision 3.2, Version 1.1, 2024-10"
    re.compile(r"^Page\s*\d+\s+Universal Serial Bus Power Delivery Specification,.*\d{4}-\d{2}", re.I),
    # "Universal Serial Bus Power Delivery Specification, ... 2024-10 Page 53"
    re.compile(r"^Universal Serial Bus Power Delivery Specification,.*\d{4}-\d{2}\s+Page\s*\d+$", re.I),
    # fallback simple "Page 34"
    re.compile(r"^Page\s*\d+\s*$", re.I),
]

# Figure and table detection (actual figure/table lines)
FIGURE_RE = re.compile(r'^(?:Figure|Fig\.?)\s*([A-Za-z]?\d+)\.(\d+)\s*(.*)$', re.I)
TABLE_RE = re.compile(r'^(?:Table)\s*([A-Za-z]?\d+)\.(\d+)\s*(.*)$', re.I)

# Detect references: e.g. Figure 5.24, "Title..." -> comma + quoted title
FIGURE_REFERENCE_RE = re.compile(r'^(?:Figure|Fig\.?)\s*\d+\.\d+\s*,\s*["“].+["”]?', re.I)
TABLE_REFERENCE_RE = re.compile(r'^(?:Table)\s*\d+\.\d+\s*,\s*["“].+["”]?', re.I)

# Section single-line: "2.1    Title" or "2.1 Title"
SECTION_INLINE_RE = re.compile(r'^(\d{1,3}(?:\.\d{1,3}){0,6})\s{1,5}([A-Z][A-Za-z0-9 ,:/()\-\u2013\u2014]{4,})$')

# Section id only: when section id is on its own line and title on next line
ONLY_SECTION_ID_RE = re.compile(r'^(\d{1,3}(?:\.\d{1,3}){1,8})$')

# For detecting section-id-like tokens in rendered text that might be noise
SECTION_ID_STRICT_RE = re.compile(r'^\d+(\.\d+)*$')

# Paragraph detection (a longish text)
PARAGRAPH_LIKELY_RE = re.compile(r'[a-zA-Z]{6,}')


# ----------------------------
# Utilities & Logger Setup
# ----------------------------
def setup_logging(output_dir: str, level=logging.INFO):
    log_dir = os.path.join(output_dir, "Log")   # ✅ LOG folder
    os.makedirs(log_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"parser_{ts}.log")

    logger = logging.getLogger("usb_pd_parser")
    logger.setLevel(level)
    logger.handlers = []

    fmt = "%(asctime)s,%(msecs)03d [%(levelname)s] %(name)s:%(lineno)d - %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logger.addHandler(ch)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    logger.addHandler(fh)

    logger.info(f"Logging initialized. Log file: {log_path}")
    return logger, log_path

# ----------------------------
# Performance Monitoring Thread
# ----------------------------
def performance_logger(stop_event, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    perf_log_path = os.path.join(output_dir, "Performance.log")

    with open(perf_log_path, "a", encoding="utf-8") as f:
        f.write("timestamp,cpu_percent,memory_mb\n")

    while not stop_event.is_set():
        try:
            cpu = psutil.cpu_percent(interval=1) if psutil else 0.0
            mem = mem_mb()
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with open(perf_log_path, "a", encoding="utf-8") as f:
                f.write(f"{ts},{cpu},{mem:.2f}\n")

        except Exception:
            pass

        time.sleep(9)   # ✅ total 10 seconds interval

def mem_mb():
    try:
        return psutil.Process(os.getpid()).memory_info().rss / (1024 ** 2) if psutil else 0.0
    except Exception:
        return 0.0


# ----------------------------
# Section Schema (simple)
# ----------------------------
class Section:
    def __init__(self, doc_title, section_id, title, page, level, parent_id, tags=None):
        self.doc_title = doc_title
        self.section_id = section_id
        self.title = title
        self.page = page
        self.level = level
        self.parent_id = parent_id
        self.tags = tags or []
        self.paragraph = ""
        self.full_path = title

    def to_dict(self):
        return {
            "doc_title": self.doc_title,
            "section_id": self.section_id,
            "title": self.title,
            "full_path": self.full_path,
            "page": self.page,
            "level": self.level,
            "parent_id": self.parent_id,
            "tags": self.tags,
            "paragraph": self.paragraph,
        }


# ----------------------------
# Core Parser Class
# ----------------------------
class PDFParser:
    def __init__(self, pdf_path: str, doc_title: str, output_dir: str = "output", start_page: int = 34, logger=None):
        self.pdf_path = pdf_path
        self.doc_title = doc_title
        self.output_dir = output_dir
        self.start_page = start_page
        self.logger = logger or logging.getLogger("usb_pd_parser")
        self.pdf_fz = None
        self._open_pdf_fz_if_possible()

    def _open_pdf_fz_if_possible(self):
        if fitz:
            try:
                self.pdf_fz = fitz.open(self.pdf_path)
                self.logger.debug("PyMuPDF opened PDF successfully.")
            except Exception as e:
                self.logger.debug(f"PyMuPDF open failed: {e}")
                self.pdf_fz = None
        else:
            self.logger.debug("PyMuPDF not available.")

    # ---------- text helpers ----------
    def _remove_footer_line(self, line: str) -> bool:
        if not line:
            return False
        for patt in FOOTER_PATTERNS:
            if patt.search(line.strip()):
                return True
        return False

    def _clean_text(self, text: str, remove_trailing_page_like=True):
        if text is None:
            return ""

        s = text.replace('\r', '\n')

        # Fix broken hyphen line breaks
        s = re.sub(r'-\s*\n\s*', '', s)

        # Join multiline into single line
        s = re.sub(r'\n+', ' ', s)

        # ✅ FIX 1: Remove SOLID dot leaders + page number
        # Example: "Overview...................... 34"
        s = re.sub(r'\.{5,}\s*\d{1,4}\s*$', '', s)

        # ✅ FIX 2: Remove SPACED dot leaders + page number
        # Example: ". . . . . . . . . 34"
        s = re.sub(r'(?:\s*\.\s*){6,}\s*\d{1,4}\s*$', '', s)

        # Remove non-printable chars
        s = ''.join(ch for ch in s if ch.isprintable())

        # Footer-like page cleanup
        if remove_trailing_page_like:
             s = re.sub(r'\s+\d{1,4}\s*$', '', s)

        s = s.strip()
        s = re.sub(r'\s+', ' ', s)

        return s.strip()
    
    # ---------- lines extraction ----------
    def _lines_from_page(self, page):
        """
        Returns list of dicts: {'text':text, 'top':y}
        """
        try:
            words = page.extract_words(extra_attrs=['fontname', 'size'])
        except Exception:
            words = []

        if not words:
            lines = []
            raw = page.extract_text() or ""
            for ln in raw.splitlines():
                t = ln.strip()
                if t:
                    lines.append({"text": t, "top": None})
            return lines

        groups = {}
        for w in words:
            top = round(float(w.get('top', 0.0)), 1)
            groups.setdefault(top, []).append(w)
        lines = []
        for top in sorted(groups.keys()):
            ws = sorted(groups[top], key=lambda x: float(x.get('x0', 0.0)))
            text = " ".join(w['text'] for w in ws).strip()
            if text:
                lines.append({"text": text, "top": top})
        return lines

    # ---------- TOC extraction ----------
    def extract_toc(self, max_pages=10):
        start = time.time()
        toc = []
        toc_started = False
        regex = re.compile(r'^(\d+(?:\.\d+)*)(?:\s+)(.+?)(?:\s+(\d{1,4}))?$')

        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                pages_to_scan = min(max_pages, len(pdf.pages))
                for pi in range(pages_to_scan):
                    page = pdf.pages[pi]
                    txt = page.extract_text() or ""
                    if not txt.strip():
                        continue
                    for raw in txt.splitlines():
                        line = raw.strip()
                        if not line:
                            continue
                        if not toc_started:
                            if re.search(r'\bTable Of Contents\b', line, re.I):
                                toc_started = True
                                self.logger.info(f"TOC detection started on page {pi+1}")
                            continue

                        m = regex.match(line)
                        if m:
                            sec_id = m.group(1)

                            # ✅ CLEAN TITLE: remove dotted leaders + page numbers ONLY at end
                            title_raw = m.group(2)

                            # ✅ REMOVE ALL DOT LEADERS (both "....." AND ". . . . .")
                            title_clean = re.sub(r'(\.\s*){3,}.*$', '', title_raw).strip()

                            # ✅ REMOVE TRAILING PAGE NUMBER (even if stuck to dots)
                            title_clean = re.sub(r'\s*\d+\s*$', '', title_clean).strip()

                            # ✅ REMOVE ANY TRAILING DOTS OR SPACES (ALL LEVELS)
                            title_clean = title_clean.rstrip('.').strip()

                            start_page = int(m.group(3)) if m.group(3) else pi + 1
                            level = sec_id.count('.') + 1

                            toc.append({
                                "doc_title": self.doc_title,
                                "section_id": sec_id,
                                "title": title_clean,
                                "start_page": start_page,
                                "level": level,
                                "parent_id": ".".join(sec_id.split('.')[:-1]) if '.' in sec_id else None
                            })
        except Exception as e:
            self.logger.exception(f"TOC extraction failed: {e}")

        unique = []
        seen = set()
        for t in toc:
            key = t['section_id']
            if key not in seen:
                seen.add(key)
                unique.append(t)

        toc_path = os.path.join(self.output_dir, "usb_pd_toc.jsonl")
        os.makedirs(self.output_dir, exist_ok=True)
        with open(toc_path, "w", encoding="utf-8") as fh:
            for rec in unique:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

        elapsed = time.time() - start
        self.logger.info(f"TOC extracted: {len(unique)} entries in {elapsed:.2f}s | Mem {mem_mb():.1f}MB")
        return unique

    # ---------- figure image extraction ----------
    def extract_figure_image(self, page_num: int, fig_id: str, raw_line=None, page_obj=None, page_used_xrefs=None):
        """
        Try to extract embedded image by xref first; otherwise smart crop below caption.
        Returns list of image file paths.
        """
        out_dir = os.path.join(self.output_dir, "figures")
        os.makedirs(out_dir, exist_ok=True)
        saved = []

        # Method : smart crop based on words (caption top -> downward until blocker)
        if self.pdf_fz:
            try:
                pg = self.pdf_fz[page_num - 1]
                words = []
                try:
                    words = pg.get_text("words") or []
                except Exception:
                    words = []

                start_y = 0
                if raw_line and isinstance(raw_line, dict) and raw_line.get('top') is not None:
                    start_y = raw_line.get('top') + 8
                stop_y = None

                figure_ref_re = re.compile(r"^Figure\s+\d+\.\d+", re.I)
                table_ref_re = re.compile(r"^Table\s+\d+\.\d+", re.I)
                section_id_re = re.compile(r"^\d+(\.\d+)+$")
                paragraph_re = re.compile(r"[a-zA-Z]{6,}")

                for w in words:
                    y = w[1]
                    text = (w[4] or "").strip()
                    if y <= start_y:
                        continue
                    if figure_ref_re.match(text) or table_ref_re.match(text) or section_id_re.match(text):
                        stop_y = y - 6
                        break
                    if paragraph_re.search(text) and len(text) > 50:
                        stop_y = y - 6
                        break

                if not stop_y:
                    stop_y = pg.rect.height * 0.90

                stop_y = max(stop_y, start_y + 20)
                clip = fitz.Rect(0, start_y, pg.rect.width, stop_y)
                mat = fitz.Matrix(2, 2)
                pix = pg.get_pixmap(matrix=mat, clip=clip)
                fname = f"{fig_id.replace(' ', '_').replace('.', '.')}_page_{page_num}_crop.png"
                fpath = os.path.join(out_dir, fname)
                pix.save(fpath)
                saved.append(fpath)
                self.logger.info(f"Smart text-aware crop saved for {fig_id} p{page_num} -> {fpath}")
                return saved
            except Exception as e:
                self.logger.error(f"Text-aware crop failed for {fig_id} p{page_num}: {e}")

    # ---------- table extraction ----------
    def extract_tables_on_page(self, page_obj, page_num, guess_areas=None):
        """
        Tries camelot first (if available), then pdfplumber fallback.
        Returns list of cleaned table arrays.
        """
        tables = []
        # Try camelot if available
        if camelot:
            try:
                # attempt lattice and stream, prefer lattice then stream
                self.logger.debug(f"Attempting camelot extraction on page {page_num}")
                tables_c = []
                try:
                    tables_c = camelot.read_pdf(self.pdf_path, pages=str(page_num), flavor='lattice', strip_text='\n')
                except Exception:
                    tables_c = []
                if not tables_c:
                    try:
                        tables_c = camelot.read_pdf(self.pdf_path, pages=str(page_num), flavor='stream', strip_text='\n')
                    except Exception:
                        tables_c = []
                for t in tables_c:
                    df = t.df
                    # convert to list of lists
                    rows = df.fillna("").astype(str).values.tolist()
                    tables.append(rows)
                if tables:
                    self.logger.info(f"Camelot extracted {len(tables)} tables on page {page_num}")
                    return tables
            except Exception as e:
                self.logger.debug(f"Camelot extraction failed on page {page_num}: {e}")

        return tables

    # ---------- main extraction: sections, tables, figures ----------
    def extract_sections_tables_figures(self):
        start_time = time.time()
        sections_out = []
        tables_out = []
        figures_out = []

        current_section = None
        last_section_key = None

        section_para_lines = []

        skip_section_detection_lines = 0
        prev_section = None

        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                total_pages = len(pdf.pages)
                if self.start_page > total_pages:
                    self.logger.warning(f"start_page ({self.start_page}) > total_pages ({total_pages}), adjusting start_page to 1")
                    page_iter = range(1, total_pages + 1)
                else:
                    page_iter = range(self.start_page, total_pages + 1)

                for pnum in page_iter:
                    page = pdf.pages[pnum - 1]
                    raw_lines = self._lines_from_page(page)
                    idx = 0
                    page_used_xrefs = set()

                    while idx < len(raw_lines):
                        raw_line = raw_lines[idx]
                        line = raw_line.get('text', '').strip()
                        idx += 1
                        
                        if skip_section_detection_lines > 0:
                            skip_section_detection_lines -= 1
                            if current_section:
                                section_para_lines.append(line)
                            continue

                        if not line:
                            # blank line
                            if current_section:
                                section_para_lines.append('')
                            continue

                        # Skip footer/header-like lines
                        if self._remove_footer_line(line):
                            self.logger.debug(f"Footer/header skipped on p{pnum}: '{line[:60]}'")
                            continue

                        # ---------- MULTI-LINE SECTION: id-only line then title next ----------
                        m_only = ONLY_SECTION_ID_RE.match(line)
                        if m_only:
                            # look ahead for next non-empty, non-footer line
                            look_idx = idx
                            title_line = None
                            while look_idx < len(raw_lines):
                                cand = raw_lines[look_idx]['text'].strip()
                                look_idx += 1
                                if not cand:
                                    continue
                                if self._remove_footer_line(cand):
                                    continue
                                title_line = cand
                                break
                            if title_line:
                                # consume any lines we used for title
                                consumed = (look_idx - idx)
                                if consumed > 0:
                                    idx += consumed
                                sec_id = m_only.group(1)
                                title_clean = self._clean_text(title_line)
                                # finalize previous section
                                if current_section:
                                    current_section.paragraph = '\n'.join(section_para_lines).strip()
                                    sections_out.append(current_section)
                                # start a new section
                                current_section = Section(
                                    self.doc_title,
                                    sec_id,
                                    title_clean,
                                    pnum,
                                    sec_id.count('.') + 1,
                                    (".".join(sec_id.split('.')[:-1]) if '.' in sec_id else None),
                                    []
                                )
                                section_para_lines = []
                                self.logger.info(f"Section started {sec_id} '{title_clean}' p{pnum}")
                                continue
                            # else fallthrough to other checks

                        # ---------- TABLE detection ----------
                        m_tab = TABLE_RE.match(line)
                        if m_tab:
                            # if reference style -> treat as paragraph
                            if TABLE_REFERENCE_RE.match(line):
                                if current_section:
                                    section_para_lines.append(line)
                                else:
                                    self.logger.debug(f"Table reference found outside section on p{pnum}: {line}")
                                continue

                            major, minor, title = m_tab.groups()
                            table_id = f"Table {major}.{minor}"
                            self.logger.info(f"Table detected {table_id} p{pnum}")

                            # Pause section, insert placeholder
                            if current_section:
                                section_para_lines.append(f"<<TABLE_REF:{table_id}>>")
                                current_section.paragraph = '\n'.join(section_para_lines).strip()
                                sections_out.append(current_section)
                                # We'll resume same section object after table extraction: re-create current_section object later
                                # For safety, set current_section to a sentinel but keep prior info
                                prev_section = current_section
                                # reset accumulation but keep prev_section to resume later
                                section_para_lines = []
                                current_section = prev_section  # keep same object to resume after table

                            # Extract tables on this page
                            table_lists = self.extract_tables_on_page(page, pnum)
                            # If camelot/pdfplumber returned multiple, attempt to pick best (we output all)
                            if not table_lists:
                                self.logger.debug(f"No tables extracted by tools for {table_id} on p{pnum}")
                            for tcontent in table_lists:
                                tobj = {
                                    "doc_title": self.doc_title,
                                    "table_id": table_id,
                                    "title": self._clean_text(title),
                                    "page": pnum,
                                    "parent_id": prev_section.section_id if current_section else None,
                                    "full_path": f"{prev_section.section_id if prev_section else 'NA'} > {table_id} {self._clean_text(title)}",
                                    "content": tcontent
                                }
                                tables_out.append(tobj)
                                self.logger.info(f"Detected {table_id} on page {pnum} (rows:{len(tcontent)})")

                            continue

                        # ---------- FIGURE detection ----------
                        m_fig = FIGURE_RE.match(line)
                        if m_fig:
                            # if reference style -> treat as paragraph
                            if FIGURE_REFERENCE_RE.match(line):
                                if current_section:
                                    section_para_lines.append(line)
                                else:
                                    self.logger.debug(f"Figure reference found outside section on p{pnum}: {line}")
                                continue

                            major, minor, title = m_fig.groups()
                            fig_id = f"Figure {major}.{minor}"
                            self.logger.info(f"Figure detected {fig_id} p{pnum}")

                            # Pause section, insert placeholder
                            if current_section:
                                section_para_lines.append(f"<<FIGURE_REF:{fig_id}>>")
                                current_section.paragraph = '\n'.join(section_para_lines).strip()
                                sections_out.append(current_section)
                                prev_section = current_section
                                section_para_lines = []
                                current_section = prev_section

                            # Extract figure images
                            image_files = []
                            try:
                                image_files = self.extract_figure_image(page_num=pnum, fig_id=fig_id, raw_line=raw_line, page_obj=page, page_used_xrefs=page_used_xrefs) or []
                            except Exception as e:
                                self.logger.debug(f"Figure extraction error for {fig_id} p{pnum}: {e}")

                            fobj = {
                                "doc_title": self.doc_title,
                                "figure_id": fig_id,
                                "title": self._clean_text(title),
                                "page": pnum,
                                "image_files": image_files,
                                "parent_id": prev_section.section_id if current_section else None,
                                "full_path": f"{prev_section.section_id if prev_section else 'NA'} > {fig_id} {self._clean_text(title)}"
                            }
                            figures_out.append(fobj)
                            self.logger.info(f"Detected {fig_id} on page {pnum} (images:{len(image_files)})")
                            continue

                        # ---------- Inline section detection ----------
                        m_sec = SECTION_INLINE_RE.match(line)
                        if m_sec:
                            sec_id = m_sec.group(1)
                            title_raw = m_sec.group(2)
                            title_clean = self._clean_text(title_raw)

                            if not self._is_valid_section_title(title_clean):
                                continue

                            section_key = (sec_id, pnum)
                            if section_key == last_section_key:
                                continue

                            last_section_key = section_key

                            # ✅ FINALIZE PREVIOUS SECTION
                            if current_section:
                                current_section.paragraph = '\n'.join(section_para_lines).strip()
                                sections_out.append(current_section)

                            # ✅ START NEW INLINE SECTION
                            current_section = Section(
                                self.doc_title,
                                sec_id,
                                title_clean,
                                pnum,
                                sec_id.count('.') + 1,
                                (".".join(sec_id.split('.')[:-1]) if '.' in sec_id else None),
                                []
                            )

                            section_para_lines = []
                            self.logger.info(f"Section started {sec_id} '{title_clean}' p{pnum}")
                            continue


                        # ---------- Normal paragraph accumulation ----------
                        if current_section:
                            section_para_lines.append(line)
                        else:
                            # orphan line outside any section -- ignore or log
                            self.logger.debug(f"Orphan line on p{pnum}: '{line[:80]}'")
                            continue

                # end pages loop

                # finalize last open section
                if current_section:
                    current_section.paragraph = '\n'.join(section_para_lines).strip()
                    sections_out.append(current_section)

        except Exception as e:
            self.logger.exception(f"PDF parsing failed: {e}\n{traceback.format_exc()}")

        # Deduplicate sections by (id,title,page)
        final_sections = []
        seen = set()
        for s in sections_out:
            key = (s.section_id, s.title, s.page)
            if key not in seen:
                seen.add(key)
                # build full_path if missing
                if not s.full_path:
                    s.full_path = s.title
                final_sections.append(s)

        # Write out JSONL files
        os.makedirs(self.output_dir, exist_ok=True)
        sec_path = os.path.join(self.output_dir, "usb_pd_sections.jsonl")
        tab_path = os.path.join(self.output_dir, "usb_pd_tables.jsonl")
        fig_path = os.path.join(self.output_dir, "usb_pd_figures.jsonl")
        meta_path = os.path.join(self.output_dir, "usb_pd_metadata.jsonl")

        try:
            with open(sec_path, "w", encoding="utf-8") as fh:
                for s in final_sections:
                    fh.write(json.dumps(s.to_dict(), ensure_ascii=False) + "\n")
            self.logger.info(f"Wrote {len(final_sections)} records to {sec_path}")
        except Exception as e:
            self.logger.error(f"Failed writing sections jsonl: {e}")

        try:
            with open(tab_path, "w", encoding="utf-8") as fh:
                for t in tables_out:
                    fh.write(json.dumps(t, ensure_ascii=False) + "\n")
            self.logger.info(f"Wrote {len(tables_out)} records to {tab_path}")
        except Exception as e:
            self.logger.error(f"Failed writing tables jsonl: {e}")

        try:
            with open(fig_path, "w", encoding="utf-8") as fh:
                for f in figures_out:
                    fh.write(json.dumps(f, ensure_ascii=False) + "\n")
            self.logger.info(f"Wrote {len(figures_out)} records to {fig_path}")
        except Exception as e:
            self.logger.error(f"Failed writing figures jsonl: {e}")

        elapsed = time.time() - start_time
        self.logger.info(f"PDF parsed: {len(final_sections)} sections, {len(tables_out)} tables, {len(figures_out)} figures in {elapsed:.2f}s | Mem {mem_mb():.1f}MB")

        return {
            "sections": final_sections,
            "tables": tables_out,
            "figures": figures_out,
            "elapsed_s": elapsed
        }

    def _is_valid_section_title(self, title: str):
        if not title:
            return False

        t = title.strip()

        # ❌ Too short
        if len(t) < 5:
            return False

        # ❌ Binary / bit-like junk
        if re.fullmatch(r'[01\s]{6,}', t):
            return False

        # ❌ Pure numeric or numeric-dot junk
        if re.fullmatch(r'[\d\s\.]+', t):
            return False

        # ❌ Table row patterns: "1 CRC", "2 PHY"
        if re.match(r'^\d{1,3}\s+[A-Z]{2,}', t):
            return False

        # ❌ Sentence fragments
        if t[0].islower():
            return False

        # ❌ Ends like a sentence
        if t.endswith('.'):
            return False

        # ✅ Must contain at least ONE real word
        if len(re.findall(r'[A-Za-z]{3,}', t)) == 0:
            return False

        # ❌ Must NOT be a figure/table caption
        if re.match(r'^(Table|Figure|Fig\.)\b', t, re.I):
            return False

        return True


    # ---------- compare TOC vs Sections ----------
    def generate_toc_vs_sections_report(self, toc_list, sections_list):

        toc_ids = set(t.get("section_id") for t in toc_list)
        sec_ids = set(s.section_id for s in sections_list)

        total_toc = len(toc_ids)
        total_sections = len(sec_ids)

        missing = len(toc_ids - sec_ids)
        extra = len(sec_ids - toc_ids)

        rows = [
            {"Metric": "Total TOC Entries", "Count": total_toc},
            {"Metric": "Total Parsed Sections", "Count": total_sections},
            {"Metric": "Missing Sections", "Count": missing},
            {"Metric": "Extra Sections", "Count": extra},
        ]

        df = pd.DataFrame(rows) if pd else None

        if df is not None:
            out_x = os.path.join(self.output_dir, "Validation.xlsx")
            df.to_excel(out_x, index=False)
            self.logger.info(f"Wrote Excel comparison to {out_x}")

        return df


    def _normalize(self, s: str):
        return re.sub(r'\s+', ' ', (s or "").strip().lower())


# ----------------------------
# CLI / main
# ----------------------------
def parse_args():
    p = argparse.ArgumentParser(description="USB PD Spec single-file parser")
    p.add_argument("--pdf", required=True, help="Path to PDF file")
    p.add_argument("--title", required=True, help="Document title to write into records")
    p.add_argument("--start-page", type=int, default=34, help="Start extracting content from this page (default 34)")
    p.add_argument("--output", default="output", help="Output folder")
    return p.parse_args()


def main():
    args = parse_args()
    out_dir = args.output
    os.makedirs(out_dir, exist_ok=True)
    logger, log_path = setup_logging(out_dir, level=logging.INFO)
    stop_event = threading.Event()
    perf_thread = threading.Thread(
        target=performance_logger,
        args=(stop_event, out_dir),
        daemon=True
    )
    perf_thread.start()

    logger.info(f"Starting USB PD parsing... PDF: {args.pdf} | Title: {args.title}")
    try:
        pdf_size_mb = os.path.getsize(args.pdf) / (1024.0 ** 2) if os.path.exists(args.pdf) else 0.0
    except Exception:
        pdf_size_mb = 0.0
    logger.info(f"PDF size: {pdf_size_mb:.2f} MB")
    start_all = time.time()

    parser = PDFParser(pdf_path=args.pdf, doc_title=args.title, output_dir=out_dir, start_page=args.start_page, logger=logger)

    toc = parser.extract_toc(max_pages=60)
    # update metadata toc count to metadata json (if exists)
    # run main extraction
    res = parser.extract_sections_tables_figures()
    sections = res.get("sections", [])
    tables = res.get("tables", [])
    figures = res.get("figures", [])

    # write summary metadata (augment previous metadata)
    meta_path = os.path.join(out_dir, "usb_pd_metadata.jsonl")
    try:
        meta = {
            "doc_title": args.title,
            "pdf_path": args.pdf,
            "total_pages": 0,
            "total_sections": len(sections),
            "total_tables": len(tables),
            "total_figures": len(figures),
            "toc_entries": len(toc),
            "extracted_on": datetime.utcnow().isoformat() + "Z",
        }
        try:
            with pdfplumber.open(args.pdf) as pdf:
                meta["total_pages"] = len(pdf.pages)
        except Exception:
            pass
        with open(meta_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(meta, ensure_ascii=False, indent=2))
        logger.info(f"Wrote {meta_path}")
    except Exception as e:
        logger.error(f"Failed to write metadata: {e}")

    # Excel comparison
    try:
        df = parser.generate_toc_vs_sections_report(toc, sections)
        if df is None:
            logger.warning("pandas not available - skipping Excel generation")
    except Exception as e:
        logger.error(f"Failed to generate Excel comparison: {e}")

    elapsed_all = time.time() - start_all
    logger.info(f"Memory usage: {mem_mb():.2f} MB | Total runtime: {elapsed_all:.2f}s")
    logger.info(f"TOC entries: {len(toc)} | Sections: {len(sections)} | Tables: {len(tables)} | Figures: {len(figures)}")
    logger.info("✅ Completed all tasks successfully.")
    stop_event.set()
    perf_thread.join()


if __name__ == "__main__":
    main()
