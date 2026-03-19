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
    from docx.oxml.ns import qn

    doc = Document(path)
    parts = []

    # Itera i blocchi nell'ordine in cui appaiono nel documento (paragrafi + tabelle)
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "p":
            text = "".join(n.text or "" for n in child.iter(qn("w:t")))
            if text.strip():
                parts.append(text)
        elif tag == "tbl":
            # Legge ogni cella della tabella riga per riga
            for row in child.iter(qn("w:tr")):
                cells = []
                for cell in row.iter(qn("w:tc")):
                    cell_text = "".join(n.text or "" for n in cell.iter(qn("w:t"))).strip()
                    if cell_text:
                        cells.append(cell_text)
                if cells:
                    parts.append(" | ".join(cells))

    return "\n".join(parts)
