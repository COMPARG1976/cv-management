"""Patch App.jsx: miglioramenti UX modale Credly"""

path = r'C:\20.PROGETTI_CLAUDE_CODE\40.CV_MANAGEMENT\frontend\src\App.jsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. credlyUrl → credlyUsername ──────────────────────────────────────────────

old_state = """  // Credly import state
  const [credlyModal, setCredlyModal]   = useState(false);
  const [credlyUrl, setCredlyUrl]       = useState("");
  const [credlyLoading, setCredlyLoading] = useState(false);
  const [credlyBadges, setCredlyBadges] = useState(null);  // null | []
  const [credlySelected, setCredlySelected] = useState({});
  const [credlyError, setCredlyError]   = useState("");
  const [credlyImporting, setCredlyImporting] = useState(false);"""

new_state = """  // Credly import state
  const [credlyModal, setCredlyModal]       = useState(false);
  const [credlyUsername, setCredlyUsername] = useState("");
  const [credlyLoading, setCredlyLoading]   = useState(false);
  const [credlyBadges, setCredlyBadges]     = useState(null);  // null | []
  const [credlySelected, setCredlySelected] = useState({});
  const [credlyError, setCredlyError]       = useState("");
  const [credlyImporting, setCredlyImporting] = useState(false);
  const [credlyImportResult, setCredlyImportResult] = useState(null);  // {imported, updated}"""

content = content.replace(old_state, new_state, 1)
print("state:", "OK" if "credlyUsername" in content else "FAIL")

# ── 2. loadCredlyPreview: usa username invece di URL ───────────────────────────

old_preview_fn = """  async function loadCredlyPreview() {
    if (!credlyUrl.trim()) return;
    setCredlyLoading(true);
    setCredlyError("");
    setCredlyBadges(null);
    setCredlySelected({});
    try {
      const data = await previewCredlyBadges(token, credlyUrl.trim());"""

new_preview_fn = """  async function loadCredlyPreview() {
    if (!credlyUsername.trim()) return;
    setCredlyLoading(true);
    setCredlyError("");
    setCredlyBadges(null);
    setCredlySelected({});
    setCredlyImportResult(null);
    const profileUrl = "https://www.credly.com/users/" + credlyUsername.trim().replace(/^@/, "");
    try {
      const data = await previewCredlyBadges(token, profileUrl);"""

content = content.replace(old_preview_fn, new_preview_fn, 1)
print("preview fn:", "OK" if "credlyUsername.trim()" in content else "FAIL")

# ── 3. doCredlyImport: aggiungi result feedback ────────────────────────────────

old_import_fn = """      const result = await importCredlyBadges(token, toImport);
      // Ricarica CV aggiornato
      const fresh = await getMyCV(token);
      setCV(fresh);
      setCredlyModal(false);
      setCredlyBadges(null);
      setCredlyUrl("");"""

new_import_fn = """      const result = await importCredlyBadges(token, toImport);
      // Ricarica CV aggiornato
      const fresh = await getMyCV(token);
      setCV(fresh);
      setCredlyImportResult(result);
      setCredlyBadges(null);
      setCredlySelected({});
      setCredlyUsername("");"""

content = content.replace(old_import_fn, new_import_fn, 1)
print("import fn:", "OK" if "credlyImportResult" in content else "FAIL")

# ── 4. Pulsante "Importa da Credly" → reset anche credlyImportResult ──────────

old_open_btn = """            <button className="btn btn-secondary btn-sm" onClick={() => { setCredlyModal(true); setCredlyBadges(null); setCredlyUrl(""); setCredlyError(""); }}>"""
new_open_btn = """            <button className="btn btn-secondary btn-sm" onClick={() => { setCredlyModal(true); setCredlyBadges(null); setCredlyUsername(""); setCredlyError(""); setCredlyImportResult(null); }}>"""

content = content.replace(old_open_btn, new_open_btn, 1)
print("open btn:", "OK" if "setCredlyImportResult(null)" in content else "FAIL")

# ── 5. Rewrite Credly modal body ───────────────────────────────────────────────

today = "new Date().toISOString().slice(0, 10)"  # usato inline nel JSX

old_modal = """      {/* ── Modale Credly import ──────────────────────────────────────────── */}
      {credlyModal && (
        <Modal
          title="Importa badge da Credly"
          onClose={() => setCredlyModal(false)}
          onSave={credlyBadges ? doCredlyImport : null}
          saving={credlyImporting}
          saveLabel={`Importa selezionati (${Object.values(credlySelected).filter(Boolean).length})`}
        >
          {credlyError && <div className="alert alert--error">{credlyError}</div>}

          <div className="form-group">
            <label>URL profilo Credly</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                type="url"
                value={credlyUrl}
                onChange={e => setCredlyUrl(e.target.value)}
                placeholder="https://www.credly.com/users/nome-utente"
                style={{ flex: 1 }}
                onKeyDown={e => e.key === "Enter" && loadCredlyPreview()}
              />
              <button
                className="btn btn-secondary btn-sm"
                onClick={loadCredlyPreview}
                disabled={credlyLoading || !credlyUrl.trim()}
              >
                {credlyLoading ? "Caricamento..." : "Anteprima"}
              </button>
            </div>
          </div>

          {credlyBadges !== null && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <strong>{credlyBadges.length} badge trovati</strong>
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn btn-secondary btn-sm" onClick={() => {
                    const sel = {};
                    credlyBadges.forEach(b => { sel[b.credly_badge_id] = b.status === "new"; });
                    setCredlySelected(sel);
                  }}>Solo nuovi</button>
                  <button className="btn btn-secondary btn-sm" onClick={() => {
                    const sel = {};
                    credlyBadges.forEach(b => { sel[b.credly_badge_id] = true; });
                    setCredlySelected(sel);
                  }}>Tutti</button>
                  <button className="btn btn-secondary btn-sm" onClick={() => setCredlySelected({})}>Nessuno</button>
                </div>
              </div>
              <div style={{ maxHeight: 320, overflowY: "auto", border: "1px solid var(--color-border)", borderRadius: 6 }}>
                {credlyBadges.map(b => (
                  <label key={b.credly_badge_id} style={{
                    display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 12px",
                    borderBottom: "1px solid var(--color-border)", cursor: "pointer",
                    background: credlySelected[b.credly_badge_id] ? "var(--color-bg-alt)" : "transparent",
                  }}>
                    <input
                      type="checkbox"
                      checked={!!credlySelected[b.credly_badge_id]}
                      onChange={e => setCredlySelected(prev => ({ ...prev, [b.credly_badge_id]: e.target.checked }))}
                      style={{ marginTop: 2, width: "auto", flexShrink: 0 }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 500, fontSize: 13 }}>{b.name}</div>
                      <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                        {b.issuing_org && <span>{b.issuing_org}</span>}
                        {b.year && <span> · {b.year}</span>}
                        {b.expiry_date && <span> · Scade: <DateStr value={b.expiry_date} /></span>}
                        {b.skills_csv && <span> · {b.skills_csv}</span>}
                      </div>
                    </div>
                    <span style={{
                      fontSize: 10, fontWeight: 600, padding: "2px 6px", borderRadius: 4, flexShrink: 0,
                      background: b.status === "existing" ? "#e3f2fd" : "#e8f5e9",
                      color:      b.status === "existing" ? "#1565c0" : "#2e7d32",
                    }}>
                      {b.status === "existing" ? "Già presente" : "Nuovo"}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </Modal>
      )}"""

new_modal = """      {/* ── Modale Credly import ──────────────────────────────────────────── */}
      {credlyModal && (
        <Modal
          title="Importa badge da Credly"
          onClose={() => setCredlyModal(false)}
          onSave={credlyBadges && Object.values(credlySelected).some(Boolean) ? doCredlyImport : null}
          saving={credlyImporting}
          saveLabel={`Importa selezionati (${Object.values(credlySelected).filter(Boolean).length})`}
        >
          {credlyError && <div className="alert alert--error">{credlyError}</div>}

          {credlyImportResult && (
            <div className="alert alert--success" style={{ background: "#e8f5e9", color: "#2e7d32", border: "1px solid #a5d6a7", borderRadius: 6, padding: "10px 14px", marginBottom: 12 }}>
              {credlyImportResult.imported > 0 && <span>{credlyImportResult.imported} nuove certificazioni importate. </span>}
              {credlyImportResult.updated  > 0 && <span>{credlyImportResult.updated} aggiornate. </span>}
            </div>
          )}

          <div className="form-group">
            <label>Username Credly</label>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ color: "var(--color-text-muted)", fontSize: 13, whiteSpace: "nowrap" }}>credly.com/users/</span>
              <input
                value={credlyUsername}
                onChange={e => setCredlyUsername(e.target.value.trim())}
                placeholder="giuseppe-comparetti"
                style={{ flex: 1 }}
                onKeyDown={e => e.key === "Enter" && loadCredlyPreview()}
                autoFocus
              />
              <button
                className="btn btn-secondary btn-sm"
                onClick={loadCredlyPreview}
                disabled={credlyLoading || !credlyUsername.trim()}
                style={{ whiteSpace: "nowrap" }}
              >
                {credlyLoading ? "Caricamento..." : "Cerca badge"}
              </button>
            </div>
          </div>

          {credlyBadges !== null && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <strong style={{ fontSize: 13 }}>
                  {credlyBadges.length} badge trovati &nbsp;·&nbsp;
                  <span style={{ color: "#2e7d32" }}>{credlyBadges.filter(b => b.status === "new").length} nuovi</span>
                  {credlyBadges.some(b => b.status === "existing") && (
                    <span style={{ color: "#1565c0" }}> · {credlyBadges.filter(b => b.status === "existing").length} già presenti</span>
                  )}
                </strong>
                <div style={{ display: "flex", gap: 6 }}>
                  <button className="btn btn-secondary btn-sm" onClick={() => {
                    const sel = {};
                    credlyBadges.forEach(b => { sel[b.credly_badge_id] = b.status === "new"; });
                    setCredlySelected(sel);
                  }}>Solo nuovi</button>
                  <button className="btn btn-secondary btn-sm" onClick={() => {
                    const sel = {};
                    credlyBadges.forEach(b => { sel[b.credly_badge_id] = true; });
                    setCredlySelected(sel);
                  }}>Tutti</button>
                  <button className="btn btn-secondary btn-sm" onClick={() => setCredlySelected({})}>Nessuno</button>
                </div>
              </div>
              <div style={{ maxHeight: 340, overflowY: "auto", border: "1px solid var(--color-border)", borderRadius: 6 }}>
                {credlyBadges.map(b => {
                  const isExpired = b.expiry_date && b.expiry_date < new Date().toISOString().slice(0, 10);
                  return (
                    <label key={b.credly_badge_id} style={{
                      display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
                      borderBottom: "1px solid var(--color-border)", cursor: "pointer",
                      background: credlySelected[b.credly_badge_id] ? "var(--color-bg-alt)" : "transparent",
                      opacity: isExpired ? 0.65 : 1,
                    }}>
                      <input
                        type="checkbox"
                        checked={!!credlySelected[b.credly_badge_id]}
                        onChange={e => setCredlySelected(prev => ({ ...prev, [b.credly_badge_id]: e.target.checked }))}
                        style={{ width: "auto", flexShrink: 0 }}
                      />
                      {b.badge_image_url && (
                        <img src={b.badge_image_url} alt="" style={{ width: 36, height: 36, objectFit: "contain", flexShrink: 0 }} />
                      )}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 500, fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
                          {b.name}
                          {isExpired && (
                            <span style={{ fontSize: 10, background: "#ffebee", color: "#c62828", borderRadius: 4, padding: "1px 5px", fontWeight: 600 }}>
                              Scaduta
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--color-text-muted)", marginTop: 2 }}>
                          {b.issuing_org && <span>{b.issuing_org}</span>}
                          {b.year && <span> · {b.year}</span>}
                          {b.expiry_date && !isExpired && <span> · Scade: <DateStr value={b.expiry_date} /></span>}
                          {b.expiry_date && isExpired && <span style={{ color: "#c62828" }}> · Scaduta il <DateStr value={b.expiry_date} /></span>}
                        </div>
                      </div>
                      <span style={{
                        fontSize: 10, fontWeight: 600, padding: "2px 6px", borderRadius: 4, flexShrink: 0,
                        background: b.status === "existing" ? "#e3f2fd" : "#e8f5e9",
                        color:      b.status === "existing" ? "#1565c0" : "#2e7d32",
                      }}>
                        {b.status === "existing" ? "Presente" : "Nuovo"}
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}
        </Modal>
      )}"""

if old_modal in content:
    content = content.replace(old_modal, new_modal, 1)
    print("modal body: OK")
else:
    print("modal body: NOT FOUND")
    # Try to find partial match
    idx = content.find("Modale Credly import")
    print(f"  Found 'Modale Credly import' at idx={idx}")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Done. Total lines:", content.count('\n'))
