import re
def normalize_spaces(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).strip()

# Heading regexes
NUMBERED_RE = re.compile(r'^(?P<id>\d+(?:\.\d+)*)\s+(?P<title>.+)$')
ANNEX_RE = re.compile(r'^(?P<id>(Annex|Appendix)\s*[A-Z0-9]*)[:.\s-]*?(?P<title>.*)$', re.IGNORECASE)

def detect_heading(line: str):
    """Return (section_id, title) if line looks like a heading, else None."""
    line = normalize_spaces(line)
    m = NUMBERED_RE.match(line)
    if m:
        return m.group('id'), m.group('title').strip()
    m2 = ANNEX_RE.match(line)
    if m2:
        sid = m2.group('id').strip()
        title = m2.group('title').strip() or sid
        return sid, title
    return None
