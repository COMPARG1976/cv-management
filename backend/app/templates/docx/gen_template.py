"""
Genera cv_standard.docx — template docxtpl per CV Management.
Layout basato su CV_CM_Comparetti.docx.

Campi evidenziati in GIALLO = aggiunti rispetto al CV originale.
Eseguire con: python gen_template.py
"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os

BLUE  = RGBColor(0x1F, 0x4E, 0x79)
GRAY  = RGBColor(0x60, 0x60, 0x60)
BLACK = RGBColor(0x00, 0x00, 0x00)


def _run(para, text, bold=False, italic=False, size=10,
         color=BLACK, highlight=False):
    """Aggiunge un run a un paragrafo con stile."""
    r = para.add_run(text)
    r.bold   = bold
    r.italic = italic
    r.font.size  = Pt(size)
    r.font.color.rgb = color
    if highlight:
        r.font.highlight_color = WD_COLOR_INDEX.YELLOW
    return r


def _hr(doc, thickness=4, color="1F4E79"):
    """Aggiunge una riga orizzontale colorata sotto il paragrafo."""
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"),   "single")
    bottom.set(qn("w:sz"),    str(thickness))
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), color)
    pBdr.append(bottom)
    pPr.append(pBdr)
    return p


def section_heading(doc, text):
    """Heading 1 stile CV originale."""
    p = _hr(doc)
    p.text = ""
    h = doc.add_heading(text, level=1)
    for run in h.runs:
        run.font.color.rgb = BLUE
        run.font.size = Pt(13)
        run.bold = True
    return h


# ─────────────────────────────────────────────
doc = Document()

sec = doc.sections[0]
sec.page_width    = Cm(21)
sec.page_height   = Cm(29.7)
sec.left_margin   = sec.right_margin = Cm(2)
sec.top_margin    = Cm(2)
sec.bottom_margin = Cm(2)

# ══════════════════════════════════════════════
# INTESTAZIONE — Nome + Titolo + Contatti
# ══════════════════════════════════════════════
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
_run(p, "{{ full_name }}", bold=True, size=20, color=BLUE)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
_run(p, "{{ job_title }}", italic=True, size=12, color=GRAY)

# Contatti inline — questi campi NON erano nel CV originale → GIALLO
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
_run(p, "{{ email }}", size=9, highlight=True)
_run(p, "  |  ", size=9, color=GRAY)
_run(p, "{{ phone }}", size=9, highlight=True)
_run(p, "  |  ", size=9, color=GRAY)
_run(p, "{{ location }}", size=9, highlight=True)
_run(p, "  |  ", size=9, color=GRAY)
_run(p, "{{ linkedin_url }}", size=9, highlight=True)

doc.add_paragraph()

# ══════════════════════════════════════════════
# RIEPILOGO PROFESSIONALE
# ══════════════════════════════════════════════
section_heading(doc, "RIEPILOGO PROFESSIONALE")
p = doc.add_paragraph()
_run(p, "{{ summary }}", size=10)
doc.add_paragraph()

# ══════════════════════════════════════════════
# ESPERIENZA PROFESSIONALE ATTUALE
# ══════════════════════════════════════════════
section_heading(doc, "ESPERIENZA PROFESSIONALE ATTUALE")

# Solo le esperienze con end_date nullo (In corso)
doc.add_paragraph("{%p for ref in experiences if not ref.end_date %}")

p = doc.add_paragraph()
_run(p, "{{ ref.role }}", bold=True, size=11, color=BLUE)
_run(p, "  —  {{ ref.company }}", bold=False, size=11)

p = doc.add_paragraph()
_run(p, "{{ ref.client_name }}", bold=True, size=10)

p = doc.add_paragraph()
_run(p, "{{ ref.start_date }} — Presente", italic=True, size=9, color=GRAY)

p = doc.add_paragraph()
_run(p, "{{ ref.project_description }}", size=10)

p = doc.add_paragraph()
_run(p, "Competenze: ", bold=True, size=9)
_run(p, "{{ ref.skills_acquired | join(', ') }}", size=9, color=GRAY)

doc.add_paragraph("{%p endfor %}")
doc.add_paragraph()

# ══════════════════════════════════════════════
# ESPERIENZE PROFESSIONALI PREGRESSE
# ══════════════════════════════════════════════
section_heading(doc, "ESPERIENZE PROFESSIONALI PREGRESSE")

# Solo le esperienze con end_date valorizzato
doc.add_paragraph("{%p for ref in experiences if ref.end_date %}")

p = doc.add_paragraph()
_run(p, "{{ ref.role }}", bold=True, size=11, color=BLUE)
_run(p, "  —  {{ ref.company }}", bold=False, size=11)

p = doc.add_paragraph()
_run(p, "{{ ref.client_name }}", bold=True, size=10)

p = doc.add_paragraph()
_run(p, "{{ ref.start_date }} — {{ ref.end_date }}", italic=True, size=9, color=GRAY)

p = doc.add_paragraph()
_run(p, "{{ ref.project_description }}", size=10)

p = doc.add_paragraph()
_run(p, "Competenze: ", bold=True, size=9)
_run(p, "{{ ref.skills_acquired | join(', ') }}", size=9, color=GRAY)

# Separatore tra esperienze
p = doc.add_paragraph()
_run(p, " ", size=6)

doc.add_paragraph("{%p endfor %}")
doc.add_paragraph()

# ══════════════════════════════════════════════
# FORMAZIONE
# ══════════════════════════════════════════════
section_heading(doc, "FORMAZIONE")

doc.add_paragraph("{%p for edu in educations %}")

p = doc.add_paragraph()
_run(p, "{{ edu.degree_type }}", bold=True, size=10)
_run(p, " in {{ edu.field_of_study }}", size=10)

p = doc.add_paragraph()
_run(p, "{{ edu.institution }}", size=10, color=GRAY)

p = doc.add_paragraph()
_run(p, "{{ edu.start_year }} — {{ edu.end_year }}", italic=True, size=9, color=GRAY)

doc.add_paragraph("{%p endfor %}")

# Certificazioni
doc.add_paragraph()
p = doc.add_paragraph()
_run(p, "CERTIFICAZIONI:", bold=True, size=10)

doc.add_paragraph("{%p for cert in certifications %}")

p = doc.add_paragraph(style="List Paragraph")
_run(p, "{{ cert.issue_date }}  ", size=9, color=GRAY)
_run(p, "{{ cert.name }}", bold=True, size=9)
_run(p, "  —  {{ cert.issuing_org }}", size=9)
# cert_code e doc_url non erano nel CV originale → GIALLO
_run(p, "  [{{ cert.cert_code }}]", size=9, highlight=True)
_run(p, "  {{ cert.doc_url }}", size=9, highlight=True)

doc.add_paragraph("{%p endfor %}")
doc.add_paragraph()

# ══════════════════════════════════════════════
# COMPETENZE TECNICHE
# ══════════════════════════════════════════════
section_heading(doc, "COMPETENZE TECNICHE")

# Raggruppa per categoria con groupby Jinja2
doc.add_paragraph("{%p for category, group in skills | groupby('category') %}")

p = doc.add_paragraph(style="List Paragraph")
_run(p, "{{ category }}: ", bold=True, size=9)
_run(p, "{{ group | map(attribute='name') | join(', ') }}", size=9)

doc.add_paragraph("{%p endfor %}")
doc.add_paragraph()

# ══════════════════════════════════════════════
# LINGUE
# ══════════════════════════════════════════════
section_heading(doc, "LINGUE")

doc.add_paragraph("{%p for lang in languages %}")

p = doc.add_paragraph(style="List Paragraph")
_run(p, "{{ lang.language }}", bold=True, size=9)
_run(p, "  {{ lang.level }}", size=9)
_run(p, "  {{ lang.notes }}", size=9, color=GRAY)

doc.add_paragraph("{%p endfor %}")
doc.add_paragraph()

# ══════════════════════════════════════════════
# INFO MASHFROG (aggiunte — GIALLO)
# ══════════════════════════════════════════════
section_heading(doc, "DATI MASHFROG")
p = doc.add_paragraph()
_run(p, "Data assunzione: ", bold=True, size=9)
_run(p, "{{ hire_date_mashfrog }}", size=9, highlight=True)
_run(p, "   Sede: ", bold=True, size=9)
_run(p, "{{ mashfrog_office }}", size=9, highlight=True)
_run(p, "   BU: ", bold=True, size=9)
_run(p, "{{ bu_mashfrog }}", size=9, highlight=True)
doc.add_paragraph()

# ══════════════════════════════════════════════
# PRIVACY
# ══════════════════════════════════════════════
p = doc.add_paragraph()
_run(p, "Autorizzo il trattamento dei miei dati personali presenti nel curriculum vitae "
        "ai sensi del Decreto Legislativo 30 giugno 2003, n. 196 e del GDPR (Regolamento UE 2016/679).",
        size=8, color=GRAY, italic=True)

# ─────────────────────────────────────────────
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cv_standard_new.docx")
doc.save(out)
print(f"Salvato: {out}")
print()
print("Campi in GIALLO (aggiunti rispetto al CV originale):")
print("  - email, phone, location, linkedin_url")
print("  - cert_code, doc_url")
print("  - hire_date_mashfrog, mashfrog_office, bu_mashfrog")
