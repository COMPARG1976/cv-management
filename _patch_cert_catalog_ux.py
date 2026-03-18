import re

path = "C:/20.PROGETTI_CLAUDE_CODE/40.CV_MANAGEMENT/frontend/src/App.jsx"
with open(path, encoding="utf-8") as f:
    src = f.read()

# ── 1. Import: add searchCertCatalog, suggestCertCodes ──────────────────────
old = 'uploadCertDoc, previewCredlyBadges, importCredlyBadges'
new = 'uploadCertDoc, previewCredlyBadges, importCredlyBadges,\n  searchCertCatalog, suggestCertCodes'
assert old in src, "IMPORT NOT FOUND"
src = src.replace(old, new, 1)
print("1. imports: OK")

# ── 2. CertificazioniTab: add catalogSuggestions state ──────────────────────
old = '  const [credlyImportResult, setCredlyImportResult] = useState(null);  // {imported, updated}'
new = (
    '  const [credlyImportResult, setCredlyImportResult] = useState(null);  // {imported, updated}\n'
    '  const [catalogSuggestions, setCatalogSuggestions] = useState({});    // {cert_id: {name, cert_code, vendor, img_url}}'
)
assert old in src, "STATE NOT FOUND"
src = src.replace(old, new, 1)
print("2. state: OK")

# ── 3. Add useEffect to load catalog suggestions for certs without cert_code ─
# Place it after the existing state declarations, before the first function
old = '    doc_attachment_type: "NONE", doc_url: "",\n    credly_badge_id: "", badge_image_url: "",\n  });'
new = (
    '    doc_attachment_type: "NONE", doc_url: "",\n'
    '    credly_badge_id: "", badge_image_url: "",\n'
    '  });\n\n'
    '  // Carica suggerimenti codice per cert senza cert_code\n'
    '  useEffect(() => {\n'
    '    const missing = {};\n'
    '    (cv?.certifications || []).forEach(c => {\n'
    '      if (!c.cert_code) missing[String(c.id)] = c.name;\n'
    '    });\n'
    '    if (Object.keys(missing).length === 0) return;\n'
    '    suggestCertCodes(token, missing)\n'
    '      .then(data => setCatalogSuggestions(data || {}))\n'
    '      .catch(() => {});\n'
    '  }, [cv?.certifications]);'
)
assert '    doc_attachment_type: "NONE", doc_url: "",\n    credly_badge_id: "", badge_image_url: "",\n  });' in src, "FORM INITIAL NOT FOUND"
src = src.replace(
    '    doc_attachment_type: "NONE", doc_url: "",\n    credly_badge_id: "", badge_image_url: "",\n  });',
    new, 1
)
print("3. useEffect suggest: OK")

# ── 4. Name field: replace plain input with AutocompleteInput ────────────────
old = (
    '          <div className="form-group">\n'
    '            <label>Nome certificazione *</label>\n'
    '            <input value={form.name} onChange={e => upd("name", e.target.value)} placeholder="es. Microsoft Azure Fundamentals" />\n'
    '          </div>'
)
new = (
    '          <div className="form-group">\n'
    '            <label>Nome certificazione *</label>\n'
    '            <AutocompleteInput\n'
    '              value={form.name}\n'
    '              onChange={v => upd("name", v)}\n'
    '              fetchSuggestions={q => searchCertCatalog(token, q)}\n'
    '              renderSuggestion={s => (\n'
    '                <>\n'
    '                  {s.img_url && <img src={s.img_url} alt="" style={{ width: 24, height: 24, objectFit: "contain", marginRight: 6, flexShrink: 0 }} />}\n'
    '                  <span style={{ flex: 1 }}>\n'
    '                    <strong>{s.name}</strong>\n'
    '                    <em style={{ marginLeft: 6, color: "var(--color-text-muted)" }}>{s.vendor}{s.cert_code ? ` · ${s.cert_code}` : ""}</em>\n'
    '                  </span>\n'
    '                </>\n'
    '              )}\n'
    '              onSelect={s => setForm(f => ({\n'
    '                ...f,\n'
    '                name:        s.name        || f.name,\n'
    '                issuing_org: s.vendor      || f.issuing_org,\n'
    '                cert_code:   s.cert_code   || f.cert_code,\n'
    '                badge_image_url: s.img_url || f.badge_image_url,\n'
    '              }))}\n'
    '              placeholder="es. SAP Certified Associate..."\n'
    '            />\n'
    '          </div>'
)
assert old in src, "NAME INPUT NOT FOUND"
src = src.replace(old, new, 1)
print("4. name autocomplete: OK")

# ── 5. Hint chip for cert_code suggestion on read-only cards ─────────────────
# Find where hints are displayed and add catalog suggestion chip
old = (
    '                {(() => {\n'
    '                  const ch = (hints.cert_hints || {})[String(c.id)];\n'
    '                  if (!ch) return null;'
)
new = (
    '                {(() => {\n'
    '                  const catSug = catalogSuggestions[String(c.id)];\n'
    '                  if (catSug && !c.cert_code) return (\n'
    '                    <div style={{ marginTop: 4 }}>\n'
    '                      <HintChip\n'
    '                        text="Codice suggerito:"\n'
    '                        value={`${catSug.cert_code || catSug.name} (${catSug.vendor})`}\n'
    '                        onApply={() => openEdit({ ...c, cert_code: catSug.cert_code || "", name: catSug.name || c.name, issuing_org: catSug.vendor || c.issuing_org })}\n'
    '                      />\n'
    '                    </div>\n'
    '                  );\n'
    '                  return null;\n'
    '                })()}\n'
    '                {(() => {\n'
    '                  const ch = (hints.cert_hints || {})[String(c.id)];\n'
    '                  if (!ch) return null;'
)
assert old in src, "HINT SECTION NOT FOUND"
src = src.replace(old, new, 1)
print("5. catalog hint chip: OK")

# ── 6. Credly modal: show cert_code badge if available on preview items ───────
# Find the badge list item in the Credly modal and add cert_code display
old = '                          <span style={{ fontWeight: 600, fontSize: 14 }}>{b.name}</span>'
new = (
    '                          <span style={{ fontWeight: 600, fontSize: 14 }}>{b.name}</span>\n'
    '                          {b.cert_code && (\n'
    '                            <span style={{ fontSize: 11, background: "#e3f2fd", color: "#1565c0", borderRadius: 3, padding: "1px 5px", marginLeft: 6 }}>\n'
    '                              {b.cert_code}\n'
    '                            </span>\n'
    '                          )}'
)
assert old in src, "CREDLY BADGE NAME NOT FOUND"
src = src.replace(old, new, 1)
print("6. credly cert_code badge: OK")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)

lines = src.count("\n") + 1
print(f"\nDone. Total lines: {lines}")
