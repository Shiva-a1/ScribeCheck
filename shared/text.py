import io

from pypdf import PdfReader


def pdf_text(data):
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def chunk_text(text, words=220, overlap=40):
    tokens = text.split()
    if not tokens:
        return []
    step = words - overlap
    return [" ".join(tokens[i:i + words]) for i in range(0, max(len(tokens) - overlap, 1), step)]
