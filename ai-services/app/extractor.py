"""
Estrazione testo grezzo da PDF e DOCX.
"""
import os


def extract_text(file_path: str) -> str:
    """
    Estrae testo da PDF (PyMuPDF) o DOCX (python-docx).
    Ritorna stringa vuota in caso di errore.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return _extract_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return _extract_docx(file_path)
    else:
        raise ValueError(f"Formato non supportato: {ext}")


def _extract_pdf(path: str) -> str:
    import fitz  # PyMuPDF
    text_parts = []
    with fitz.open(path) as doc:
        for page in doc:
            text_parts.append(page.get_text("text"))
    return "\n".join(text_parts)


def _extract_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
