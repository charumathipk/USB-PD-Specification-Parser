import re
from typing import List, Dict
from PyPDF2 import PdfReader
from ..utils.text_helpers import normalize_spaces, detect_heading

class SectionParser:
    """Parse PDF into hierarchical sections (numbered and unnumbered headings)."""

    def __init__(self, pdf_path: str, doc_title: str = 'USB Power Delivery Specification') -> None:
        self.pdf_path = pdf_path
        self.doc_title = doc_title

    def parse(self) -> List[Dict]:
        reader = PdfReader(self.pdf_path)
        sections = []
        current = None

        # iterate pages and lines
        for pindex, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ''
            lines = [normalize_spaces(l) for l in text.splitlines() if normalize_spaces(l)]
            i = 0
            while i < len(lines):
                line = lines[i]
                hd = detect_heading(line)
                if hd:
                    # start new section
                    sid, title = hd
                    # finish previous
                    if current is not None:
                        sections.append(current)
                    current = {
                        'doc_title': self.doc_title,
                        'section_id': sid,
                        'title': title,
                        'full_path': f"{sid} {title}".strip(),
                        'page': pindex,
                        'level': 1 if '.' not in sid else len(sid.split('.')),
                        'parent_id': None,
                        'tags': [],
                        'content': ''
                    }
                    i += 1
                    # gather immediate following short lines that may be part of title (rare)
                    continue
                else:
                    # no heading: append to current content or hold as orphan until a heading appears
                    if current is None:
                        # create a generic top-level section to hold preface text (if any)
                        current = {
                            'doc_title': self.doc_title,
                            'section_id': f'pre.{pindex}',
                            'title': f'Page {pindex} (preface)',
                            'full_path': f'pre.{pindex} Page {pindex}',
                            'page': pindex,
                            'level': 1,
                            'parent_id': None,
                            'tags': [],
                            'content': ''
                        }
                    # append this line to content
                    if current['content']:
                        current['content'] += '\n' + line
                    else:
                        current['content'] = line
                    i += 1
            # end of page loop
        # append last
        if current is not None:
            sections.append(current)

        # post-process: infer parent_id by numeric truncation
        id_map = {s['section_id']: s for s in sections if s['section_id']}
        for s in sections:
            sid = s['section_id']
            if '.' in sid:
                parent = '.'.join(sid.split('.')[:-1])
                if parent in id_map:
                    s['parent_id'] = parent
                else:
                    s['parent_id'] = None
            else:
                s['parent_id'] = None

        # normalize level based on dots for numbered ids, leave annex as 1 if not dotted
        for s in sections:
            sid = s['section_id']
            s['level'] = 1 if '.' not in sid else len(sid.split('.'))

        return sections
