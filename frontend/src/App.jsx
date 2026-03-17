/**
 * CV Management System — App principale
 * Sprint 2+: global edit mode, autocomplete skills/cert, user fields, last-modified.
 */
import { useState, useEffect, useRef } from "react";
import {
  login, entraExchange, getAuthConfig,
  getMyCV, updateMyCV,
  addSkill, updateSkill, deleteSkill,
  addEducation, updateEducation, deleteEducation,
  addLanguage, updateLanguage, deleteLanguage,
  addReference, updateReference, deleteReference,
  addCertification, updateCertification, deleteCertification,
  uploadCertDoc, previewCredlyBadges, importCredlyBadges,
  searchCertCatalog, suggestCertCodes,
  getSkillSuggestions, getCertSuggestions,
  uploadCV, applyDiff, getCVHints,
  listExportTemplates, exportCVDocx,
} from "./api.js";

// ── Costanti ──────────────────────────────────────────────────────────────────
const VIEWS = {
  HOME:         "HOME",
  MY_CV:        "MY_CV",
  ADMIN_USERS:  "ADMIN_USERS",
  ADMIN_SEARCH: "ADMIN_SEARCH",
  ADMIN_STATS:  "ADMIN_STATS",
};

const SKILL_CATEGORIES = ["HARD", "SOFT"];
const DEGREE_LEVELS    = ["DIPLOMA", "TRIENNALE", "MAGISTRALE", "DOTTORATO", "MASTER", "CORSO"];
const LANGUAGE_LEVELS  = ["A1", "A2", "B1", "B2", "C1", "C2", "MADRELINGUA"];
const AVAIL_OPTIONS    = ["DISPONIBILE", "OCCUPATO", "IN_USCITA"];

// ── Helper Components ─────────────────────────────────────────────────────────

function Stars({ value, onChange, max = 5 }) {
  return (
    <span style={{ display: "inline-flex", gap: 2 }}>
      {Array.from({ length: max }, (_, i) => i + 1).map(n => (
        <span
          key={n}
          style={{ cursor: onChange ? "pointer" : "default", fontSize: 16, color: n <= (value || 0) ? "#f59e0b" : "#d1d5db" }}
          onClick={() => onChange && onChange(n)}
        >★</span>
      ))}
    </span>
  );
}

function DateStr({ value, withTime = false }) {
  if (!value) return <span>—</span>;
  const d = new Date(value);
  if (isNaN(d.getTime())) return <span>{value}</span>;
  if (withTime) {
    return <span>{d.toLocaleString("it-IT", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}</span>;
  }
  return <span>{d.toLocaleDateString("it-IT", { year: "numeric", month: "short" })}</span>;
}

function Modal({ title, onClose, onSave, saving, saveLabel, children }) {
  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal__header">
          <span className="modal__title">{title}</span>
          <button className="modal__close" onClick={onClose}>✕</button>
        </div>
        {children}
        <div className="modal__footer">
          <button className="btn btn-secondary" onClick={onClose}>Annulla</button>
          {onSave && (
            <button className="btn btn-primary" onClick={onSave} disabled={saving}>
              {saving ? "Salvo..." : (saveLabel || "Salva")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Autocomplete generico con debounce 300ms
function AutocompleteInput({ value, onChange, fetchSuggestions, renderSuggestion, onSelect, placeholder, autoFocus }) {
  const [suggestions, setSuggestions] = useState([]);
  const [showList, setShowList]       = useState(false);
  const timerRef = useRef(null);

  function handleChange(e) {
    const v = e.target.value;
    onChange(v);
    clearTimeout(timerRef.current);
    if (!v.trim()) { setSuggestions([]); setShowList(false); return; }
    timerRef.current = setTimeout(async () => {
      try {
        const data = await fetchSuggestions(v);
        setSuggestions(data || []);
        setShowList((data || []).length > 0);
      } catch (_) {}
    }, 300);
  }

  function handleSelect(item) {
    onSelect(item);
    setShowList(false);
    setSuggestions([]);
  }

  return (
    <div className="autocomplete-wrap">
      <input
        value={value}
        onChange={handleChange}
        placeholder={placeholder}
        autoFocus={autoFocus}
        onBlur={() => setTimeout(() => setShowList(false), 150)}
        onFocus={() => value && suggestions.length > 0 && setShowList(true)}
      />
      {showList && (
        <ul className="autocomplete-list">
          {suggestions.map((s, i) => (
            <li key={i} className="autocomplete-item" onMouseDown={() => handleSelect(s)}>
              {renderSuggestion(s)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const [token, setToken]             = useState(() => sessionStorage.getItem("cv_token"));
  const [currentUser, setCurrentUser] = useState(() => {
    const u = sessionStorage.getItem("cv_user");
    return u ? JSON.parse(u) : null;
  });
  const [view, setView]           = useState(VIEWS.HOME);
  const [entraLoading, setEntraLoading] = useState(false);
  const [entraError,   setEntraError]   = useState("");

  // Intercetta il callback Entra ID (?code=...&state=...)
  useEffect(() => {
    const params  = new URLSearchParams(window.location.search);
    const code    = params.get("code");
    const errParam = params.get("error");

    if (errParam) {
      const desc = params.get("error_description") || errParam;
      setEntraError(`Accesso Microsoft negato: ${desc}`);
      window.history.replaceState({}, "", window.location.pathname);
      return;
    }

    if (!code) return;

    // Verifica CSRF state
    const savedState    = sessionStorage.getItem("entra_state");
    const returnedState = params.get("state");
    window.history.replaceState({}, "", window.location.pathname);

    if (savedState && returnedState !== savedState) {
      setEntraError("Errore di sicurezza: state non valido. Riprovare.");
      return;
    }

    const redirectUri = sessionStorage.getItem("entra_redirect_uri")
      || `${window.location.origin}/auth/callback`;
    sessionStorage.removeItem("entra_state");
    sessionStorage.removeItem("entra_redirect_uri");

    setEntraLoading(true);
    entraExchange(code, redirectUri)
      .then(data => {
        sessionStorage.setItem("cv_token", data.access_token);
        const user = { email: data.email, role: data.role, full_name: data.full_name };
        sessionStorage.setItem("cv_user", JSON.stringify(user));
        setToken(data.access_token);
        setCurrentUser(user);
      })
      .catch(err => setEntraError(err.message))
      .finally(() => setEntraLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleLogout() {
    sessionStorage.removeItem("cv_token");
    sessionStorage.removeItem("cv_user");
    setToken(null);
    setCurrentUser(null);
    setView(VIEWS.HOME);
  }

  if (entraLoading) {
    return (
      <div className="login-wrapper">
        <div className="login-card" style={{ textAlign: "center" }}>
          <div style={{ fontSize: 32, marginBottom: 16 }}>⏳</div>
          <h2>Autenticazione Microsoft in corso...</h2>
          <p style={{ color: "var(--color-text-muted)", marginTop: 8 }}>
            Verifica del token Entra ID
          </p>
        </div>
      </div>
    );
  }

  if (!token) {
    return <LoginPage
      onLogin={(tok, user) => {
        sessionStorage.setItem("cv_token", tok);
        sessionStorage.setItem("cv_user", JSON.stringify(user));
        setToken(tok);
        setCurrentUser(user);
      }}
      entraError={entraError}
    />;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="topbar__title">CV Management</span>
        <div className="topbar__user">
          <span>{currentUser?.full_name}</span>
          <span className={`badge badge--${currentUser?.role?.toLowerCase()}`}>{currentUser?.role}</span>
          <button className="btn btn-secondary btn-sm" onClick={handleLogout}>Esci</button>
        </div>
      </header>

      <main className="main-content">
        {view === VIEWS.HOME         && <HomeView currentUser={currentUser} setView={setView} />}
        {view === VIEWS.MY_CV        && <MyCVView token={token} currentUser={currentUser} onBack={() => setView(VIEWS.HOME)} />}
        {view === VIEWS.ADMIN_USERS  && <PlaceholderView title="Gestione Utenti"       onBack={() => setView(VIEWS.HOME)} sprint="Sprint 4" />}
        {view === VIEWS.ADMIN_SEARCH && <PlaceholderView title="Ricerca per Skill"     onBack={() => setView(VIEWS.HOME)} sprint="Sprint 4" />}
        {view === VIEWS.ADMIN_STATS  && <PlaceholderView title="Analytics & Dashboard" onBack={() => setView(VIEWS.HOME)} sprint="Sprint 5" />}
      </main>
    </div>
  );
}

// Icona Microsoft 4-quadrati (logo ufficiale)
function MicrosoftIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 21 21" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="0"  y="0"  width="10" height="10" fill="#F25022"/>
      <rect x="11" y="0"  width="10" height="10" fill="#7FBA00"/>
      <rect x="0"  y="11" width="10" height="10" fill="#00A4EF"/>
      <rect x="11" y="11" width="10" height="10" fill="#FFB900"/>
    </svg>
  );
}

// ── Login Page ────────────────────────────────────────────────────────────────
function LoginPage({ onLogin, entraError }) {
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const [authConfig, setAuthConfig] = useState(null);

  // Carica configurazione auth (per sapere se Entra è abilitato)
  useEffect(() => {
    getAuthConfig()
      .then(cfg => setAuthConfig(cfg))
      .catch(() => {}); // Silenzioso: se fallisce si usa solo il login locale
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await login(email, password);
      onLogin(data.access_token, { email: data.email, role: data.role, full_name: data.full_name });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleEntraLogin() {
    if (!authConfig?.entra_enabled) return;

    // Genera CSRF state casuale
    const state       = Math.random().toString(36).substring(2) + Date.now().toString(36);
    const redirectUri = authConfig.entra_redirect_uri
      || `${window.location.origin}/auth/callback`;

    sessionStorage.setItem("entra_state",        state);
    sessionStorage.setItem("entra_redirect_uri", redirectUri);

    const url = new URL(
      `https://login.microsoftonline.com/${authConfig.entra_tenant_id}/oauth2/v2.0/authorize`
    );
    url.searchParams.set("client_id",      authConfig.entra_client_id);
    url.searchParams.set("response_type",  "code");
    url.searchParams.set("redirect_uri",   redirectUri);
    url.searchParams.set("scope",          "openid email profile");
    url.searchParams.set("state",          state);
    url.searchParams.set("response_mode",  "query");
    url.searchParams.set("prompt",         "select_account");

    window.location.href = url.toString();
  }

  const entraEnabled = authConfig?.entra_enabled;

  return (
    <div className="login-wrapper">
      <div className="login-card">
        <h1>CV Management</h1>
        <p>Accedi con le credenziali aziendali</p>

        {(entraError || error) && (
          <div className="alert alert--error">{entraError || error}</div>
        )}

        {/* Bottone Entra ID — mostrato solo se configurato */}
        {entraEnabled && (
          <>
            <button
              type="button"
              className="btn-microsoft"
              onClick={handleEntraLogin}
            >
              <MicrosoftIcon />
              Entra con Autenticazione Aziendale
            </button>
            <div className="login-divider">
              <span>oppure accedi con password locale</span>
            </div>
          </>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoFocus={!entraEnabled} />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} required />
          </div>
          <button type="submit" className="btn btn-primary" style={{ width: "100%" }} disabled={loading}>
            {loading ? "Accesso in corso..." : "Accedi"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Home View ─────────────────────────────────────────────────────────────────
function HomeView({ currentUser, setView }) {
  const isAdmin = currentUser?.role === "ADMIN";

  const tiles = isAdmin ? [
    { icon: "👥", label: "Utenti",        view: VIEWS.ADMIN_USERS },
    { icon: "🔍", label: "Ricerca Skill", view: VIEWS.ADMIN_SEARCH },
    { icon: "📊", label: "Analytics",     view: VIEWS.ADMIN_STATS },
    { icon: "📄", label: "Il Mio CV",     view: VIEWS.MY_CV },
  ] : [
    { icon: "📄", label: "Il Mio CV",     view: VIEWS.MY_CV },
  ];

  return (
    <>
      <h2 style={{ marginBottom: 24 }}>
        Benvenuto{currentUser?.full_name ? `, ${currentUser.full_name}` : ""}
      </h2>
      <div className="tiles">
        {tiles.map(t => (
          <div key={t.view} className="tile" onClick={() => setView(t.view)}>
            <span className="tile__icon">{t.icon}</span>
            <span className="tile__label">{t.label}</span>
          </div>
        ))}
      </div>
    </>
  );
}

// ── My CV View ────────────────────────────────────────────────────────────────
function MyCVView({ token, currentUser, onBack }) {
  const [cv, setCV]               = useState(null);
  const [hints, setHints]         = useState({});
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState("");
  const [activeTab, setActiveTab] = useState("anagrafica");

  useEffect(() => {
    // HINTS DISABILITATI — per riattivare: .then(data => { setCV(data); return getCVHints(token); }).then(h => setHints(h))
    getMyCV(token)
      .then(data => setCV(data))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) return <div className="loading-center"><div className="spinner" /></div>;

  const tabProps = { token, cv, setCV, hints };

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <button className="btn btn-secondary btn-sm" onClick={onBack}>← Indietro</button>
        <div style={{ flex: 1 }}>
          <h2 style={{ margin: 0 }}>{cv?.full_name || currentUser?.full_name}</h2>
          {cv?.updated_at && (
            <div className="cv-header__meta">
              Ultima modifica: <DateStr value={cv.updated_at} withTime />
            </div>
          )}
        </div>
      </div>

      {error && <div className="alert alert--error">{error}</div>}

      {cv && (
        <div className="card" style={{ marginBottom: 20, padding: "16px 24px" }}>
          <div className="completeness__label">
            Completezza CV: {Math.round((cv.completeness_score || 0) * 100)}%
          </div>
          <div className="progress-bar">
            <div className="progress-bar__fill" style={{ width: `${(cv.completeness_score || 0) * 100}%` }} />
          </div>
        </div>
      )}

      <div className="tabs">
        {[
          ["anagrafica", "👤 Anagrafica"],
          ["formazione", "🎓 Formazione"],
          ["skill",      "🛠 Competenze"],
          ["esperienze", "💼 Esperienze"],
          ["cert",       "🏅 Certificazioni"],
          ["lingue",     "🌍 Lingue"],
          ["upload",     "📤 Carica CV"],
          ["export",     "⬇️ Esporta CV"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={`tab-btn ${activeTab === key ? "tab-btn--active" : ""}`}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {!cv && <div className="alert alert--warning">Nessun CV trovato.</div>}
      {cv && activeTab === "anagrafica"  && <AnagraficaTab    {...tabProps} />}
      {cv && activeTab === "formazione"  && <FormazioneTab    {...tabProps} />}
      {cv && activeTab === "skill"       && <CompetenzeTab    {...tabProps} />}
      {cv && activeTab === "esperienze"  && <EsperienzeTab    {...tabProps} />}
      {cv && activeTab === "cert"        && <CertificazioniTab {...tabProps} />}
      {cv && activeTab === "lingue"      && <LingueTab        {...tabProps} />}
      {cv && activeTab === "upload"      && <UploadTab {...tabProps} />}
      {cv && activeTab === "export"     && <ExportTab token={token} />}
    </>
  );
}

// ── Anagrafica Tab ────────────────────────────────────────────────────────────
function AnagraficaTab({ token, cv, setCV, hints = {} }) {
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState("");

  const buildForm = () => ({
    title:                 cv.title                || "",
    summary:               cv.summary              || "",
    phone:                 cv.phone                || "",
    linkedin_url:          cv.linkedin_url         || "",
    birth_date:            cv.birth_date           || "",
    birth_place:           cv.birth_place          || "",
    residence_city:        cv.residence_city       || "",
    first_employment_date: cv.first_employment_date || "",
    availability_status:   cv.availability_status  || "DISPONIBILE",
    hire_date_mashfrog:    cv.hire_date_mashfrog   || "",
    mashfrog_office:       cv.mashfrog_office      || "",
    bu_mashfrog:           cv.bu_mashfrog          || "",
  });

  const [form, setForm] = useState(buildForm);
  function upd(k, v) { setForm(f => ({ ...f, [k]: v })); }

  function openModal() {
    setForm(buildForm());
    setError("");
    setShowModal(true);
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const payload = { ...form };
      // Null out empty string date fields
      ["birth_date", "first_employment_date", "hire_date_mashfrog"].forEach(k => {
        if (!payload[k]) payload[k] = null;
      });
      const updated = await updateMyCV(token, payload);
      setCV(prev => ({ ...prev, ...updated }));
      setShowModal(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  const dt = { color: "var(--color-text-muted)" };

  return (
    <>
      <div className="card">
        <div className="card__header">
          <span className="card__title">Dati Personali</span>
          <button className="btn btn-primary btn-sm" onClick={openModal}>✏ Modifica</button>
        </div>
        {/* Hint profilo: campi mancanti */}
        {(hints.profile_hints || []).length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
            {hints.profile_hints.map(h => (
              <HintChip key={h.field} text={h.label} onApply={openModal} />
            ))}
          </div>
        )}
        <dl style={{ display: "grid", gridTemplateColumns: "220px 1fr", rowGap: 12, fontSize: 13 }}>
          <dt style={dt}>Titolo / Ruolo</dt>
          <dd>{cv.title || "—"}</dd>

          <dt style={dt}>Telefono</dt>
          <dd>{cv.phone || "—"}</dd>

          <dt style={dt}>LinkedIn</dt>
          <dd>
            {cv.linkedin_url
              ? <a href={cv.linkedin_url} target="_blank" rel="noopener noreferrer">{cv.linkedin_url}</a>
              : "—"}
          </dd>

          <dt style={dt}>Data di nascita</dt>
          <dd><DateStr value={cv.birth_date} /></dd>

          <dt style={dt}>Luogo di nascita</dt>
          <dd>{cv.birth_place || "—"}</dd>

          <dt style={dt}>Città di residenza</dt>
          <dd>{cv.residence_city || "—"}</dd>

          <dt style={dt}>Prima occupazione</dt>
          <dd><DateStr value={cv.first_employment_date} /></dd>

          <dt style={dt}>Assunzione Mashfrog</dt>
          <dd><DateStr value={cv.hire_date_mashfrog} /></dd>

          <dt style={dt}>Sede Mashfrog</dt>
          <dd>{cv.mashfrog_office || "—"}</dd>

          <dt style={dt}>Business Unit</dt>
          <dd>{cv.bu_mashfrog || "—"}</dd>

          <dt style={dt}>Disponibilità</dt>
          <dd>
            <span className={`badge badge--${cv.availability_status?.toLowerCase()}`}>
              {cv.availability_status}
            </span>
          </dd>

          <dt style={{ ...dt, alignSelf: "start" }}>Sommario</dt>
          <dd style={{ whiteSpace: "pre-wrap" }}>{cv.summary || "—"}</dd>
        </dl>
      </div>

      {showModal && (
        <Modal title="Modifica Dati Personali" onClose={() => setShowModal(false)} onSave={save} saving={saving}>
          {error && <div className="alert alert--error">{error}</div>}
          <div className="form-row">
            <div className="form-group">
              <label>Titolo / Ruolo</label>
              <input autoFocus value={form.title} onChange={e => upd("title", e.target.value)} />
            </div>
            <div className="form-group">
              <label>Telefono</label>
              <input value={form.phone} onChange={e => upd("phone", e.target.value)} />
            </div>
          </div>
          <div className="form-group">
            <label>LinkedIn URL</label>
            <input value={form.linkedin_url} onChange={e => upd("linkedin_url", e.target.value)} />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Data di nascita</label>
              <input type="date" value={form.birth_date} onChange={e => upd("birth_date", e.target.value)} />
            </div>
            <div className="form-group">
              <label>Luogo di nascita</label>
              <input value={form.birth_place} onChange={e => upd("birth_place", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Città di residenza</label>
              <input value={form.residence_city} onChange={e => upd("residence_city", e.target.value)} />
            </div>
            <div className="form-group">
              <label>Prima occupazione</label>
              <input type="date" value={form.first_employment_date} onChange={e => upd("first_employment_date", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Assunzione Mashfrog</label>
              <input type="date" value={form.hire_date_mashfrog} onChange={e => upd("hire_date_mashfrog", e.target.value)} />
            </div>
            <div className="form-group">
              <label>Sede Mashfrog</label>
              <input value={form.mashfrog_office} onChange={e => upd("mashfrog_office", e.target.value)} placeholder="Roma, Milano..." />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Business Unit</label>
              <input value={form.bu_mashfrog} onChange={e => upd("bu_mashfrog", e.target.value)} placeholder="Digital, SAP..." />
            </div>
            <div className="form-group">
              <label>Disponibilità</label>
              <select value={form.availability_status} onChange={e => upd("availability_status", e.target.value)}>
                {AVAIL_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          </div>
          <div className="form-group">
            <label>Sommario professionale</label>
            <textarea rows={4} value={form.summary} onChange={e => upd("summary", e.target.value)} />
          </div>
        </Modal>
      )}
    </>
  );
}

// ── Competenze Tab ────────────────────────────────────────────────────────────
function CompetenzeTab({ token, cv, setCV, hints = {} }) {
  const [modal, setModal]   = useState(null); // null | { mode:"add"|"edit", item? }
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState("");
  const [form, setForm]     = useState({ skill_name: "", category: "HARD", rating: 3, notes: "" });

  function upd(k, v) { setForm(f => ({ ...f, [k]: v })); }

  function openAdd(category) {
    setForm({ skill_name: "", category, rating: 3, notes: "" });
    setError("");
    setModal({ mode: "add" });
  }

  function openEdit(sk) {
    setForm({ skill_name: sk.skill_name, category: sk.category, rating: sk.rating || 3, notes: sk.notes || "" });
    setError("");
    setModal({ mode: "edit", item: sk });
  }

  async function saveSkill() {
    if (!form.skill_name.trim()) return;
    setSaving(true);
    setError("");
    try {
      const payload = { ...form, rating: Number(form.rating) };
      if (modal.mode === "add") {
        const sk = await addSkill(token, payload);
        setCV(prev => ({ ...prev, skills: [...prev.skills, sk] }));
      } else {
        const sk = await updateSkill(token, modal.item.id, payload);
        setCV(prev => ({ ...prev, skills: prev.skills.map(s => s.id === sk.id ? sk : s) }));
      }
      setModal(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeSkill(id) {
    try {
      await deleteSkill(token, id);
      setCV(prev => ({ ...prev, skills: prev.skills.filter(s => s.id !== id) }));
    } catch (e) {
      setError(e.message);
    }
  }

  const hard = (cv.skills || []).filter(s => s.category === "HARD").sort((a, b) => a.skill_name.localeCompare(b.skill_name));
  const soft = (cv.skills || []).filter(s => s.category === "SOFT").sort((a, b) => a.skill_name.localeCompare(b.skill_name));

  return (
    <>
      {error && !modal && <div className="alert alert--error">{error}</div>}

      {/* Skill suggerite dalle esperienze */}
      {(hints.skill_hints || []).length > 0 && (
        <div style={{ background: "#fffbeb", border: "1px solid #fde68a", borderRadius: 8, padding: "12px 16px", marginBottom: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#92400e", marginBottom: 8 }}>
            💡 Competenze rilevate dalle tue esperienze non ancora nel profilo:
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {hints.skill_hints.map(sk => (
              <button
                key={sk}
                onClick={() => { setForm({ skill_name: sk, category: "HARD", rating: 3, notes: "" }); setModal({ mode: "add" }); }}
                style={{ background: "#f59e0b", color: "#fff", border: "none", borderRadius: 6, padding: "3px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
              >
                + {sk}
              </button>
            ))}
          </div>
        </div>
      )}

      {[{ cat: "HARD", label: "Competenze Tecniche", items: hard },
        { cat: "SOFT", label: "Soft Skills",         items: soft }].map(({ cat, label, items }) => (
        <div key={cat} className="card">
          <div className="card__header">
            <span className="card__title">{label} ({items.length})</span>
            <button className="btn btn-primary btn-sm" onClick={() => openAdd(cat)}>+ Aggiungi</button>
          </div>
          {items.length === 0 ? (
            <p style={{ color: "var(--color-text-muted)", fontSize: 13 }}>Nessuna competenza aggiunta.</p>
          ) : (
            items.map(sk => (
              <div key={sk.id} className="section-item">
                <div className="section-item__body">
                  <div className="section-item__title">{sk.skill_name}</div>
                  <div className="section-item__sub">
                    <Stars value={sk.rating} />
                    {sk.notes && <span style={{ marginLeft: 8 }}>{sk.notes}</span>}
                  </div>
                </div>
                <div className="section-item__actions">
                  <button className="btn btn-secondary btn-sm" onClick={() => openEdit(sk)}>✏</button>
                  <button className="btn btn-danger btn-sm" onClick={() => removeSkill(sk.id)}>Elimina</button>
                </div>
              </div>
            ))
          )}
        </div>
      ))}

      {modal && (
        <Modal
          title={modal.mode === "add"
            ? `Aggiungi ${form.category === "HARD" ? "Competenza Tecnica" : "Soft Skill"}`
            : "Modifica Competenza"}
          onClose={() => setModal(null)}
          onSave={saveSkill}
          saving={saving}
        >
          {error && <div className="alert alert--error">{error}</div>}
          <div className="form-group">
            <label>Nome competenza *</label>
            <AutocompleteInput
              value={form.skill_name}
              onChange={v => upd("skill_name", v)}
              fetchSuggestions={q => getSkillSuggestions(token, q)}
              renderSuggestion={s => (
                <>
                  <strong>{s.skill_name}</strong>
                  <em>{s.count}× in altri CV</em>
                </>
              )}
              onSelect={s => upd("skill_name", s.skill_name)}
              placeholder="es. Python, SAP ABAP..."
              autoFocus
            />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Categoria</label>
              <select value={form.category} onChange={e => upd("category", e.target.value)}>
                {SKILL_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>Rating</label>
              <div style={{ paddingTop: 8 }}>
                <Stars value={form.rating} onChange={v => upd("rating", v)} />
              </div>
            </div>
          </div>
          <div className="form-group">
            <label>Note</label>
            <input value={form.notes} onChange={e => upd("notes", e.target.value)} />
          </div>
        </Modal>
      )}
    </>
  );
}

// ── Esperienze Tab ────────────────────────────────────────────────────────────
function EsperienzeTab({ token, cv, setCV, hints = {} }) {
  const [modal, setModal]   = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState("");

  const emptyForm = () => ({
    company_name: "", client_name: "", role: "",
    start_date: "", end_date: "", is_current: false,
    project_description: "", activities: "",
  });
  const [form, setForm] = useState(emptyForm());
  function upd(k, v) { setForm(f => ({ ...f, [k]: v })); }

  function openAdd() {
    setForm(emptyForm());
    setError("");
    setModal({ mode: "add" });
  }

  function openEdit(r) {
    setForm({
      company_name:        r.company_name        || "",
      client_name:         r.client_name         || "",
      role:                r.role                || "",
      start_date:          (r.start_date || "").slice(0, 7),
      end_date:            (r.end_date   || "").slice(0, 7),
      is_current:          r.is_current          || false,
      project_description: r.project_description || "",
      activities:          r.activities          || "",
    });
    setError("");
    setModal({ mode: "edit", item: r });
  }

  async function saveRef() {
    setSaving(true);
    setError("");
    try {
      const payload = { ...form };
      if (!payload.start_date) payload.start_date = null;
      if (!payload.end_date || payload.is_current) payload.end_date = null;
      if (modal.mode === "add") {
        const ref = await addReference(token, payload);
        setCV(prev => ({ ...prev, references: [...prev.references, ref] }));
      } else {
        const ref = await updateReference(token, modal.item.id, payload);
        setCV(prev => ({ ...prev, references: prev.references.map(r => r.id === ref.id ? ref : r) }));
      }
      setModal(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeRef(id) {
    try {
      await deleteReference(token, id);
      setCV(prev => ({ ...prev, references: prev.references.filter(r => r.id !== id) }));
    } catch (e) {
      setError(e.message);
    }
  }

  const refs = [...(cv.references || [])].sort((a, b) => {
    // "In corso" (end_date null) → considera come futuro lontano per venire prima
    const endA = a.end_date || "9999-99";
    const endB = b.end_date || "9999-99";
    if (endB !== endA) return endB.localeCompare(endA);
    // parità su end_date: ordina per start_date DESC
    const startA = a.start_date || "";
    const startB = b.start_date || "";
    return startB.localeCompare(startA);
  });

  const RefForm = () => (
    <>
      {error && <div className="alert alert--error">{error}</div>}
      <div className="form-row">
        <div className="form-group">
          <label>Azienda</label>
          <input value={form.company_name} onChange={e => upd("company_name", e.target.value)} />
        </div>
        <div className="form-group">
          <label>Cliente</label>
          <input value={form.client_name} onChange={e => upd("client_name", e.target.value)} />
        </div>
      </div>
      <div className="form-group">
        <label>Ruolo / Posizione</label>
        <input autoFocus={modal?.mode === "add"} value={form.role} onChange={e => upd("role", e.target.value)} />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>Data inizio (mese/anno)</label>
          <input type="month" value={form.start_date} onChange={e => upd("start_date", e.target.value)} />
        </div>
        <div className="form-group">
          <label>Data fine (mese/anno)</label>
          <input type="month" value={form.end_date} disabled={form.is_current} onChange={e => upd("end_date", e.target.value)} />
        </div>
      </div>
      <div className="form-group">
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={form.is_current} onChange={e => upd("is_current", e.target.checked)} style={{ width: "auto" }} />
          Esperienza in corso
        </label>
      </div>
      <div className="form-group">
        <label>Descrizione progetto</label>
        <textarea rows={3} value={form.project_description} onChange={e => upd("project_description", e.target.value)} />
      </div>
      <div className="form-group">
        <label>Attività svolte</label>
        <textarea rows={2} value={form.activities} onChange={e => upd("activities", e.target.value)} />
      </div>
    </>
  );

  return (
    <>
      {error && !modal && <div className="alert alert--error">{error}</div>}
      <div className="card">
        <div className="card__header">
          <span className="card__title">Esperienze Professionali ({refs.length})</span>
          <button className="btn btn-primary btn-sm" onClick={openAdd}>+ Aggiungi</button>
        </div>
        {refs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state__icon">💼</div>
            <h3>Nessuna esperienza</h3>
            <p>Aggiungi le tue esperienze professionali</p>
          </div>
        ) : (
          refs.map(r => (
            <div key={r.id} className="section-item">
              <div className="section-item__body">
                <div className="section-item__title">
                  {r.role || "—"}
                  {r.company_name ? ` @ ${r.company_name}` : ""}
                  {r.client_name  ? ` (cliente: ${r.client_name})` : ""}
                </div>
                <div className="section-item__sub">
                  <DateStr value={r.start_date} /> {" – "}
                  {r.is_current ? "In corso" : <DateStr value={r.end_date} />}
                </div>
                {r.project_description && (
                  <div style={{ fontSize: 12, marginTop: 4, color: "var(--color-text-muted)" }}>
                    <strong>Progetto:</strong> {r.project_description}
                  </div>
                )}
                {r.activities && (
                  <div style={{ fontSize: 12, marginTop: 2, color: "var(--color-text-muted)" }}>
                    <strong>Attività:</strong> {r.activities}
                  </div>
                )}
                {/* Hint inline per campi mancanti */}
                {(() => {
                  const eh = (hints.experience_hints || {})[String(r.id)];
                  if (!eh) return null;
                  return (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
                      {eh.project_description && <HintChip text={eh.project_description.note} onApply={() => openEdit(r)} />}
                      {eh.role               && <HintChip text={eh.role.note} onApply={() => openEdit(r)} />}
                      {eh.client_name        && <HintChip text={eh.client_name.note} onApply={() => openEdit(r)} />}
                      {eh.skills_acquired    && <HintChip text={eh.skills_acquired.note} onApply={() => openEdit(r)} />}
                      {eh.start_date         && <HintChip text={eh.start_date.note} onApply={() => openEdit(r)} />}
                    </div>
                  );
                })()}
              </div>
              <div className="section-item__actions">
                <button className="btn btn-secondary btn-sm" onClick={() => openEdit(r)}>✏</button>
                <button className="btn btn-danger btn-sm" onClick={() => removeRef(r.id)}>Elimina</button>
              </div>
            </div>
          ))
        )}
      </div>

      {modal && (
        <Modal
          title={modal.mode === "add" ? "Aggiungi Esperienza" : "Modifica Esperienza"}
          onClose={() => setModal(null)}
          onSave={saveRef}
          saving={saving}
        >
          <RefForm />
        </Modal>
      )}
    </>
  );
}

// ── Formazione Tab ────────────────────────────────────────────────────────────
function FormazioneTab({ token, cv, setCV }) {
  const [modal, setModal]   = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState("");

  const emptyForm = () => ({
    institution: "", degree_level: "TRIENNALE", field_of_study: "",
    graduation_year: "", grade: "", notes: "",
  });
  const [form, setForm] = useState(emptyForm());
  function upd(k, v) { setForm(f => ({ ...f, [k]: v })); }

  function openAdd() {
    setForm(emptyForm());
    setError("");
    setModal({ mode: "add" });
  }

  function openEdit(e) {
    setForm({
      institution:     e.institution     || "",
      degree_level:    e.degree_level    || "TRIENNALE",
      field_of_study:  e.field_of_study  || "",
      graduation_year: e.graduation_year || "",
      grade:           e.grade           || "",
      notes:           e.notes           || "",
    });
    setError("");
    setModal({ mode: "edit", item: e });
  }

  async function saveEdu() {
    if (!form.institution.trim()) return;
    setSaving(true);
    setError("");
    try {
      const payload = { ...form, graduation_year: form.graduation_year ? Number(form.graduation_year) : null };
      if (modal.mode === "add") {
        const edu = await addEducation(token, payload);
        setCV(prev => ({ ...prev, educations: [...prev.educations, edu] }));
      } else {
        const edu = await updateEducation(token, modal.item.id, payload);
        setCV(prev => ({ ...prev, educations: prev.educations.map(e => e.id === edu.id ? edu : e) }));
      }
      setModal(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeEdu(id) {
    try {
      await deleteEducation(token, id);
      setCV(prev => ({ ...prev, educations: prev.educations.filter(e => e.id !== id) }));
    } catch (e) {
      setError(e.message);
    }
  }

  const LEVEL_ORDER = ["DOTTORATO", "MAGISTRALE", "MASTER", "TRIENNALE", "DIPLOMA", "CORSO"];
  const edus = [...(cv.educations || [])].sort((a, b) =>
    LEVEL_ORDER.indexOf(a.degree_level) - LEVEL_ORDER.indexOf(b.degree_level)
  );

  return (
    <>
      {error && !modal && <div className="alert alert--error">{error}</div>}
      <div className="card">
        <div className="card__header">
          <span className="card__title">Formazione ({edus.length})</span>
          <button className="btn btn-primary btn-sm" onClick={openAdd}>+ Aggiungi</button>
        </div>
        {edus.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state__icon">🎓</div>
            <h3>Nessun titolo di studio</h3>
          </div>
        ) : (
          edus.map(e => (
            <div key={e.id} className="section-item">
              <div className="section-item__body">
                <div className="section-item__title">{e.institution}</div>
                <div className="section-item__sub">
                  {e.degree_level && <span>{e.degree_level}</span>}
                  {e.field_of_study && <span> — {e.field_of_study}</span>}
                  {e.graduation_year && <span> ({e.graduation_year})</span>}
                  {e.grade && <span> · Voto: {e.grade}</span>}
                </div>
                {e.notes && <div style={{ fontSize: 12, marginTop: 2, color: "var(--color-text-muted)" }}>{e.notes}</div>}
              </div>
              <div className="section-item__actions">
                <button className="btn btn-secondary btn-sm" onClick={() => openEdit(e)}>✏</button>
                <button className="btn btn-danger btn-sm" onClick={() => removeEdu(e.id)}>Elimina</button>
              </div>
            </div>
          ))
        )}
      </div>

      {modal && (
        <Modal
          title={modal.mode === "add" ? "Aggiungi Formazione" : "Modifica Formazione"}
          onClose={() => setModal(null)}
          onSave={saveEdu}
          saving={saving}
        >
          {error && <div className="alert alert--error">{error}</div>}
          <div className="form-group">
            <label>Istituto / Università *</label>
            <input autoFocus value={form.institution} onChange={e => upd("institution", e.target.value)} />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Tipo titolo</label>
              <select value={form.degree_level} onChange={e => upd("degree_level", e.target.value)}>
                {DEGREE_LEVELS.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>Anno conseguimento</label>
              <input type="number" min="1950" max="2030" value={form.graduation_year} onChange={e => upd("graduation_year", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Indirizzo / Materia</label>
              <input value={form.field_of_study} onChange={e => upd("field_of_study", e.target.value)} />
            </div>
            <div className="form-group">
              <label>Voto</label>
              <input value={form.grade} onChange={e => upd("grade", e.target.value)} placeholder="es. 110/110 con lode" />
            </div>
          </div>
          <div className="form-group">
            <label>Note</label>
            <input value={form.notes} onChange={e => upd("notes", e.target.value)} />
          </div>
        </Modal>
      )}
    </>
  );
}

// ── Certificazioni Tab ────────────────────────────────────────────────────────
function CertificazioniTab({ token, cv, setCV, hints = {} }) {
  const [modal, setModal]         = useState(null);  // null | {mode:"add"|"edit", item?}
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState("");
  const [uploadFile, setUploadFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  // Credly import state
  const [credlyModal, setCredlyModal]       = useState(false);
  const [credlyUsername, setCredlyUsername] = useState("");
  const [credlyLoading, setCredlyLoading]   = useState(false);
  const [credlyBadges, setCredlyBadges]     = useState(null);  // null | []
  const [credlySelected, setCredlySelected] = useState({});
  const [credlyError, setCredlyError]       = useState("");
  const [credlyImporting, setCredlyImporting] = useState(false);
  const [credlyImportResult, setCredlyImportResult] = useState(null);  // {imported, updated}
  const [catalogSuggestions, setCatalogSuggestions] = useState({});    // {cert_id: {name,cert_code,vendor}}

  const emptyForm = () => ({
    cert_code: "", name: "", issuing_org: "", year: "",
    version: "", expiry_date: "", notes: "", has_formal_cert: true,
    doc_attachment_type: "NONE", doc_url: "",
    credly_badge_id: "", badge_image_url: "",
  });
  const [form, setForm] = useState(emptyForm());

  useEffect(() => {
    const missing = {};
    (cv?.certifications || []).forEach(c => {
      if (!c.cert_code) missing[String(c.id)] = c.name;
    });
    if (Object.keys(missing).length === 0) { setCatalogSuggestions({}); return; }
    suggestCertCodes(token, missing)
      .then(data => setCatalogSuggestions(data || {}))
      .catch(() => {});
  }, [cv?.certifications]);
  function upd(k, v) { setForm(f => ({ ...f, [k]: v })); }

  function openAdd() {
    setForm(emptyForm());
    setUploadFile(null);
    setError("");
    setModal({ mode: "add" });
  }

  function openEdit(c) {
    setForm({
      cert_code:           c.cert_code           || "",
      name:                c.name                || "",
      issuing_org:         c.issuing_org         || "",
      year:                c.year                || "",
      version:             c.version             || "",
      expiry_date:         c.expiry_date         || "",
      notes:               c.notes               || "",
      has_formal_cert:     c.has_formal_cert     !== false,
      doc_attachment_type: c.doc_attachment_type || "NONE",
      doc_url:             c.doc_url             || "",
      credly_badge_id:     c.credly_badge_id     || "",
      badge_image_url:     c.badge_image_url     || "",
    });
    setUploadFile(null);
    setError("");
    setModal({ mode: "edit", item: c });
  }

  async function saveCert() {
    if (!form.name.trim()) { setError("Il nome certificazione è obbligatorio"); return; }
    setSaving(true);
    setError("");
    try {
      const payload = {
        ...form,
        year:             form.year        ? Number(form.year) : null,
        expiry_date:      form.expiry_date || null,
        cert_code:        form.cert_code   || null,
        credly_badge_id:  form.credly_badge_id  || null,
        badge_image_url:  form.badge_image_url  || null,
        // Se SHAREPOINT con file, il doc_url verrà sovrascritto dall'upload
        doc_url: (form.doc_attachment_type === "SHAREPOINT" && uploadFile)
          ? null
          : (form.doc_url || null),
      };

      let cert;
      if (modal.mode === "add") {
        cert = await addCertification(token, payload);
        setCV(prev => ({ ...prev, certifications: [...prev.certifications, cert] }));
      } else {
        cert = await updateCertification(token, modal.item.id, payload);
        setCV(prev => ({ ...prev, certifications: prev.certifications.map(c => c.id === cert.id ? cert : c) }));
      }

      // Se SHAREPOINT e file selezionato → upload
      if (form.doc_attachment_type === "SHAREPOINT" && uploadFile) {
        setUploading(true);
        try {
          const updatedCert = await uploadCertDoc(token, cert.id, uploadFile);
          setCV(prev => ({
            ...prev,
            certifications: prev.certifications.map(c => c.id === updatedCert.id ? updatedCert : c),
          }));
        } catch (ue) {
          // Upload fallito ma cert salvata — mostra warning non bloccante
          setError(`Certificazione salvata, ma upload documento fallito: ${ue.message}`);
          setModal(null);
          return;
        } finally {
          setUploading(false);
        }
      }

      setModal(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeCert(id) {
    try {
      await deleteCertification(token, id);
      setCV(prev => ({ ...prev, certifications: prev.certifications.filter(c => c.id !== id) }));
    } catch (e) {
      setError(e.message);
    }
  }

  // ── Credly ──────────────────────────────────────────────────────────────────

  async function loadCredlyPreview() {
    if (!credlyUsername.trim()) return;
    setCredlyLoading(true);
    setCredlyError("");
    setCredlyBadges(null);
    setCredlySelected({});
    setCredlyImportResult(null);
    const profileUrl = "https://www.credly.com/users/" + credlyUsername.trim().replace(/^@/, "");
    try {
      const data = await previewCredlyBadges(token, profileUrl);
      setCredlyBadges(data.badges || []);
      // Pre-seleziona solo i badge "new"
      const sel = {};
      (data.badges || []).forEach(b => { if (b.status === "new") sel[b.credly_badge_id] = true; });
      setCredlySelected(sel);
    } catch (e) {
      setCredlyError(e.message);
    } finally {
      setCredlyLoading(false);
    }
  }

  async function doCredlyImport() {
    const toImport = (credlyBadges || []).filter(b => credlySelected[b.credly_badge_id]);
    if (!toImport.length) return;
    setCredlyImporting(true);
    setCredlyError("");
    try {
      const result = await importCredlyBadges(token, toImport);
      // Ricarica CV aggiornato
      const fresh = await getMyCV(token);
      setCV(fresh);
      setCredlyImportResult(result);
      setCredlyBadges(null);
      setCredlySelected({});
      setCredlyUsername("");
    } catch (e) {
      setCredlyError(e.message);
    } finally {
      setCredlyImporting(false);
    }
  }

  const certs = [...(cv.certifications || [])].sort((a, b) => (b.year || 0) - (a.year || 0));

  return (
    <>
      {error && !modal && <div className="alert alert--error">{error}</div>}
      <div className="card">
        <div className="card__header">
          <span className="card__title">Certificazioni ({certs.length})</span>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => { setCredlyModal(true); setCredlyBadges(null); setCredlyUsername(""); setCredlyError(""); setCredlyImportResult(null); }}>
              Importa da Credly
            </button>
            <button className="btn btn-primary btn-sm" onClick={openAdd}>+ Aggiungi</button>
          </div>
        </div>
        {certs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state__icon">🏆</div>
            <h3>Nessuna certificazione</h3>
          </div>
        ) : (
          certs.map(c => (
            <div key={c.id} className="section-item">
              <div className="section-item__body">
                <div className="section-item__title">
                  {c.name}
                  {c.version && <span style={{ fontWeight: 400, color: "var(--color-text-muted)" }}> v{c.version}</span>}
                  {c.doc_attachment_type === "CREDLY" && (
                    <span style={{ marginLeft: 8, fontSize: 11, background: "#ff6b35", color: "#fff", borderRadius: 4, padding: "2px 6px" }}>Credly</span>
                  )}
                  {c.doc_attachment_type === "SHAREPOINT" && (
                    <span style={{ marginLeft: 8, fontSize: 11, background: "#0078d4", color: "#fff", borderRadius: 4, padding: "2px 6px" }}>SharePoint</span>
                  )}
                </div>
                <div className="section-item__sub">
                  {c.issuing_org && <span>{c.issuing_org}</span>}
                  {c.year       && <span> · {c.year}</span>}
                  {c.cert_code  && <span> · {c.cert_code}</span>}
                  {c.expiry_date && <span> · Scade: <DateStr value={c.expiry_date} /></span>}
                  {c.doc_url && (
                    <span> · <a href={c.doc_url} target="_blank" rel="noopener noreferrer">
                      {c.doc_attachment_type === "SHAREPOINT" ? "Documento" :
                       c.doc_attachment_type === "CREDLY"     ? "Verifica badge" :
                                                                "Verifica"}
                    </a></span>
                  )}
                </div>
                {(() => {
                  const sug = catalogSuggestions[String(c.id)];
                  if (sug && sug.cert_code && !c.cert_code) return (
                    <div style={{ marginTop: 4 }}>
                      <HintChip
                        text="Codice esame:"
                        value={`${sug.cert_code} · ${sug.vendor}`}
                        onApply={() => openEdit({
                          ...c,
                          cert_code:   sug.cert_code,
                          issuing_org: sug.vendor || c.issuing_org,
                        })}
                      />
                    </div>
                  );
                  return null;
                })()}
                {(() => {
                  const ch = (hints.cert_hints || {})[String(c.id)];
                  if (!ch) return null;
                  return (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
                      {ch.cert_code && (
                        <HintChip
                          text="Codice cert. suggerito:"
                          value={`${ch.cert_code.value} (da ${ch.cert_code.count} CV)`}
                          onApply={() => openEdit({ ...c, cert_code: ch.cert_code.value })}
                        />
                      )}
                      {ch.issuing_org && (
                        <HintChip
                          text="Ente emittente suggerito:"
                          value={ch.issuing_org.value}
                          onApply={() => openEdit({ ...c, issuing_org: ch.issuing_org.value })}
                        />
                      )}
                      {ch.doc_url && (
                        <HintChip
                          text="URL verifica trovato in altri CV"
                          onApply={() => openEdit({ ...c, doc_url: ch.doc_url.value, doc_attachment_type: ch.doc_url.attachment_type || "URL" })}
                        />
                      )}
                      {ch.expiry_date && <HintChip text={ch.expiry_date.note} />}
                    </div>
                  );
                })()}
              </div>
              <div className="section-item__actions">
                <button className="btn btn-secondary btn-sm" onClick={() => openEdit(c)}>✏</button>
                <button className="btn btn-danger btn-sm" onClick={() => removeCert(c.id)}>Elimina</button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* ── Modale Add/Edit cert ───────────────────────────────────────────── */}
      {modal && (
        <Modal
          title={modal.mode === "add" ? "Aggiungi Certificazione" : "Modifica Certificazione"}
          onClose={() => setModal(null)}
          onSave={saveCert}
          saving={saving || uploading}
        >
          {error && <div className="alert alert--error">{error}</div>}

          <div className="form-group">
            <label>Codice certificazione (es. AZ-900, AWS-SAA-C03)</label>
            <AutocompleteInput
              value={form.cert_code}
              onChange={v => upd("cert_code", v)}
              fetchSuggestions={q => getCertSuggestions(token, q)}
              renderSuggestion={s => (
                <>
                  <strong>{s.cert_code}</strong>
                  <em>{s.name}{s.issuing_org ? ` · ${s.issuing_org}` : ""}</em>
                </>
              )}
              onSelect={s => setForm(f => ({
                ...f,
                cert_code:   s.cert_code,
                name:        s.name        || f.name,
                issuing_org: s.issuing_org || f.issuing_org,
                version:     s.version     || f.version,
              }))}
              placeholder="Cerca per codice o nome..."
              autoFocus
            />
          </div>

          <div className="form-group">
            <label>Nome certificazione *</label>
            <AutocompleteInput
              value={form.name}
              onChange={v => upd("name", v)}
              fetchSuggestions={q => searchCertCatalog(token, q)}
              renderSuggestion={s => (
                <>
                  {s.img_url && <img src={s.img_url} alt="" style={{ width: 24, height: 24, objectFit: "contain", marginRight: 6, flexShrink: 0 }} />}
                  <span style={{ flex: 1 }}>
                    <strong>{s.name}</strong>
                    <em style={{ marginLeft: 6, color: "var(--color-text-muted)", fontSize: 12 }}>
                      {s.vendor}{s.cert_code ? ` · ${s.cert_code}` : ""}
                    </em>
                  </span>
                </>
              )}
              onSelect={s => setForm(f => ({
                ...f,
                name:            s.name        || f.name,
                issuing_org:     s.vendor      || f.issuing_org,
                cert_code:       s.cert_code   || f.cert_code,
                badge_image_url: s.img_url     || f.badge_image_url,
              }))}
              placeholder="es. SAP Certified Associate..."
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Ente emittente</label>
              <input value={form.issuing_org} onChange={e => upd("issuing_org", e.target.value)} placeholder="Microsoft, AWS, Google..." />
            </div>
            <div className="form-group">
              <label>Versione</label>
              <input value={form.version} onChange={e => upd("version", e.target.value)} placeholder="es. 2024" />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Anno conseguimento</label>
              <input type="number" min="1990" max="2030" value={form.year} onChange={e => upd("year", e.target.value)} />
            </div>
            <div className="form-group">
              <label>Data scadenza</label>
              <input type="date" value={form.expiry_date} onChange={e => upd("expiry_date", e.target.value)} />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Tipo documento/badge</label>
              <select value={form.doc_attachment_type} onChange={e => { upd("doc_attachment_type", e.target.value); setUploadFile(null); }}>
                <option value="NONE">Nessuno</option>
                <option value="CREDLY">Credly / Badge digitale</option>
                <option value="URL">URL pubblico</option>
                <option value="SHAREPOINT">SharePoint aziendale</option>
              </select>
            </div>
            <div className="form-group" style={{ paddingTop: 24 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={form.has_formal_cert}
                  onChange={e => upd("has_formal_cert", e.target.checked)}
                  style={{ width: "auto" }}
                />
                Certificato formale (con esame)
              </label>
            </div>
          </div>

          {/* URL field per CREDLY e URL */}
          {(form.doc_attachment_type === "CREDLY" || form.doc_attachment_type === "URL") && (
            <div className="form-group">
              <label>
                {form.doc_attachment_type === "CREDLY" ? "URL badge Credly" : "URL documento pubblico"}
              </label>
              <input
                type="url"
                value={form.doc_url}
                onChange={e => upd("doc_url", e.target.value)}
                placeholder="https://..."
              />
            </div>
          )}

          {/* File upload per SHAREPOINT */}
          {form.doc_attachment_type === "SHAREPOINT" && (
            <div className="form-group">
              <label>Documento da allegare (SharePoint)</label>
              {form.doc_url && !uploadFile && (
                <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginBottom: 4 }}>
                  Documento attuale: <em>{form.doc_url.split("/").pop()}</em>
                  {" — "}carica un nuovo file per sostituirlo
                </div>
              )}
              <input
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,.docx,.doc"
                style={{ padding: "4px 0" }}
                onChange={e => setUploadFile(e.target.files[0] || null)}
              />
              {uploadFile && (
                <div style={{ fontSize: 12, color: "var(--color-success)", marginTop: 4 }}>
                  Pronto: {uploadFile.name} ({(uploadFile.size / 1024).toFixed(0)} KB)
                </div>
              )}
              {uploading && <div style={{ fontSize: 12, color: "var(--color-primary)" }}>Caricamento in corso...</div>}
            </div>
          )}

          {/* File locale solo per NONE */}
          {form.doc_attachment_type === "NONE" && (
            <div className="form-group">
              <label>Carica certificato (anteprima locale, non salvato)</label>
              <input type="file" accept=".pdf,.jpg,.png" style={{ padding: "4px 0" }} />
            </div>
          )}

          <div className="form-group">
            <label>Note</label>
            <input value={form.notes} onChange={e => upd("notes", e.target.value)} />
          </div>
        </Modal>
      )}

      {/* ── Modale Credly import ──────────────────────────────────────────── */}
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
                          {b.cert_code && (
                            <span style={{ fontSize: 10, background: "#e3f2fd", color: "#1565c0", borderRadius: 4, padding: "1px 5px", fontWeight: 600 }}>
                              {b.cert_code}
                            </span>
                          )}
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
      )}
    </>
  );
}

// ── Lingue Tab ────────────────────────────────────────────────────────────────
function LingueTab({ token, cv, setCV }) {
  const [modal, setModal]   = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState("");
  const [form, setForm]     = useState({ language_name: "", level: "B2" });

  function upd(k, v) { setForm(f => ({ ...f, [k]: v })); }

  function openAdd() {
    setForm({ language_name: "", level: "B2" });
    setError("");
    setModal({ mode: "add" });
  }

  function openEdit(l) {
    setForm({ language_name: l.language_name || "", level: l.level || "B2" });
    setError("");
    setModal({ mode: "edit", item: l });
  }

  async function saveLang() {
    if (!form.language_name.trim()) return;
    setSaving(true);
    setError("");
    try {
      if (modal.mode === "add") {
        const lang = await addLanguage(token, form);
        setCV(prev => ({ ...prev, languages: [...prev.languages, lang] }));
      } else {
        const lang = await updateLanguage(token, modal.item.id, form);
        setCV(prev => ({ ...prev, languages: prev.languages.map(l => l.id === lang.id ? lang : l) }));
      }
      setModal(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function removeLang(id) {
    try {
      await deleteLanguage(token, id);
      setCV(prev => ({ ...prev, languages: prev.languages.filter(l => l.id !== id) }));
    } catch (e) {
      setError(e.message);
    }
  }

  const LEVEL_ORDER = ["MADRELINGUA", "C2", "C1", "B2", "B1", "A2", "A1"];
  const langs = [...(cv.languages || [])].sort((a, b) =>
    LEVEL_ORDER.indexOf(a.level) - LEVEL_ORDER.indexOf(b.level)
  );

  return (
    <>
      {error && !modal && <div className="alert alert--error">{error}</div>}
      <div className="card">
        <div className="card__header">
          <span className="card__title">Lingue ({langs.length})</span>
          <button className="btn btn-primary btn-sm" onClick={openAdd}>+ Aggiungi</button>
        </div>
        {langs.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state__icon">🌍</div>
            <h3>Nessuna lingua aggiunta</h3>
          </div>
        ) : (
          langs.map(l => (
            <div key={l.id} className="section-item">
              <div className="section-item__body">
                <div className="section-item__title">{l.language_name}</div>
                {l.level && <div className="section-item__sub">{l.level}</div>}
              </div>
              <div className="section-item__actions">
                <button className="btn btn-secondary btn-sm" onClick={() => openEdit(l)}>✏</button>
                <button className="btn btn-danger btn-sm" onClick={() => removeLang(l.id)}>Elimina</button>
              </div>
            </div>
          ))
        )}
      </div>

      {modal && (
        <Modal
          title={modal.mode === "add" ? "Aggiungi Lingua" : "Modifica Lingua"}
          onClose={() => setModal(null)}
          onSave={saveLang}
          saving={saving}
        >
          {error && <div className="alert alert--error">{error}</div>}
          <div className="form-group">
            <label>Lingua *</label>
            <input autoFocus value={form.language_name} onChange={e => upd("language_name", e.target.value)} placeholder="es. Inglese" />
          </div>
          <div className="form-group">
            <label>Livello CEFR</label>
            <select value={form.level} onChange={e => upd("level", e.target.value)}>
              {LANGUAGE_LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
        </Modal>
      )}
    </>
  );
}

// ── Upload Tab ────────────────────────────────────────────────────────────────

// Init selections from diff result (default: conservative — mantieni DB)
function initSelections(diff) {
  const profileSel = {};
  for (const fd of (diff.profile?.field_diffs || [])) {
    profileSel[fd.field] = { source: fd.status === "new_ai" ? "ai" : "db", manual: "" };
  }
  function initItems(items) {
    return (items || []).map(item => {
      if (item.status === "new") return { action: "add" };
      if (item.status === "changed") {
        const fieldSrc = {};
        for (const fd of (item.field_diffs || [])) {
          if (fd.status !== "unchanged") fieldSrc[fd.field] = "db";
        }
        return { action: "update", field_sources: fieldSrc, manuals: {} };
      }
      return { action: "skip" };
    });
  }
  return {
    profile:        profileSel,
    skills:         initItems(diff.skills?.items),
    references:     initItems(diff.references?.items),
    educations:     initItems(diff.educations?.items),
    certifications: initItems(diff.certifications?.items),
    languages:      initItems(diff.languages?.items),
  };
}

// Build the apply request payload from selections
function buildApplyRequest(diff, selections) {
  const req = {
    document_id:     diff.document_id,
    profile_updates: {},
    skills:         { add: [], update: [] },
    references:     { add: [], update: [] },
    educations:     { add: [], update: [] },
    certifications: { add: [], update: [] },
    languages:      { add: [], update: [] },
  };
  for (const fd of (diff.profile?.field_diffs || [])) {
    const sel = selections.profile[fd.field];
    if (!sel) continue;
    if (sel.source === "ai" && fd.status !== "unchanged") {
      req.profile_updates[fd.field] = fd.ai_value;
    } else if (sel.source === "manual" && sel.manual !== "") {
      req.profile_updates[fd.field] = sel.manual;
    }
  }
  function buildSection(diffItems, selItems, key) {
    (diffItems || []).forEach((item, i) => {
      const sel = selItems?.[i];
      if (!sel || sel.action === "skip") return;
      if (sel.action === "add" && item.status === "new") {
        req[key].add.push(item.ai_data);
      } else if (sel.action === "update" && item.db_id) {
        const upd = { db_id: item.db_id };
        for (const fd of (item.field_diffs || [])) {
          if (fd.status === "unchanged") continue;
          const src = sel.field_sources?.[fd.field] || "db";
          if (src === "ai") upd[fd.field] = fd.ai_value;
          else if (src === "manual") upd[fd.field] = sel.manuals?.[fd.field] ?? fd.db_value;
        }
        if (Object.keys(upd).length > 1) req[key].update.push(upd);
      }
    });
  }
  buildSection(diff.skills?.items,         selections.skills,         "skills");
  buildSection(diff.references?.items,     selections.references,     "references");
  buildSection(diff.educations?.items,     selections.educations,     "educations");
  buildSection(diff.certifications?.items, selections.certifications, "certifications");
  buildSection(diff.languages?.items,      selections.languages,      "languages");
  return req;
}

function countChanges(diff, selections) {
  let n = 0;
  for (const fd of (diff.profile?.field_diffs || [])) {
    const sel = selections.profile[fd.field];
    if (sel && sel.source !== "db" && fd.status !== "unchanged") n++;
  }
  const secs = ["skills","references","educations","certifications","languages"];
  for (const sec of secs) {
    (diff[sec]?.items || []).forEach((item, i) => {
      const sel = selections[sec]?.[i];
      if (!sel) return;
      if (item.status === "new" && sel.action === "add") n++;
      else if (item.status === "changed" && sel.action === "update") {
        if (Object.values(sel.field_sources || {}).some(s => s !== "db")) n++;
      }
    });
  }
  return n;
}

// ── Upload sub-components ─────────────────────────────────────────────────────

function UploadDropZone({ onFile, error }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef(null);
  function handleDrop(e) {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onFile(f);
  }
  return (
    <div>
      <div
        className={"upload-zone" + (dragging ? " upload-zone--drag" : "")}
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <div style={{fontSize:48,marginBottom:12}}>📄</div>
        <p style={{fontWeight:600,marginBottom:4}}>Trascina il CV qui oppure clicca per scegliere</p>
        <p style={{fontSize:13,color:"var(--color-text-muted)"}}>PDF o DOCX · max 10 MB</p>
        <input ref={inputRef} type="file" accept=".pdf,.docx,.doc" style={{display:"none"}}
          onChange={e => e.target.files?.[0] && onFile(e.target.files[0])} />
      </div>
      {error && <div className="alert alert--danger" style={{marginTop:12}}>{error}</div>}
    </div>
  );
}

function ProcessingStep() {
  const steps = ["Estrazione testo...", "Analisi sezioni...", "Mappatura dati...", "Calcolo differenze..."];
  const [current, setCurrent] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setCurrent(p => Math.min(p + 1, steps.length - 1)), 5000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="card" style={{textAlign:"center",padding:"48px 32px"}}>
      <div style={{fontSize:48,marginBottom:16}}>⏳</div>
      <h3 style={{marginBottom:24}}>Analisi AI in corso...</h3>
      <div style={{background:"var(--color-border)",borderRadius:8,height:8,maxWidth:400,margin:"0 auto 24px"}}>
        <div style={{height:8,borderRadius:8,background:"var(--color-primary)",
          width:`${((current+1)/steps.length)*100}%`,transition:"width 0.8s ease"}} />
      </div>
      <div style={{display:"flex",flexDirection:"column",gap:8,maxWidth:300,margin:"0 auto",textAlign:"left"}}>
        {steps.map((s, i) => (
          <div key={i} style={{display:"flex",alignItems:"center",gap:8,opacity:i<=current?1:0.35}}>
            <span>{i < current ? "✓" : i === current ? "⏳" : "○"}</span>
            <span style={{fontSize:13}}>{s}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    new:       { label:"NUOVO",     bg:"#dcfce7", color:"#166534" },
    changed:   { label:"MODIFICA",  bg:"#fef9c3", color:"#854d0e" },
    unchanged: { label:"INVARIATO", bg:"#f1f5f9", color:"#475569" },
    db_only:   { label:"SOLO DB",   bg:"#eff6ff", color:"#1e40af" },
  };
  const { label, bg, color } = map[status] || { label:status, bg:"#f1f5f9", color:"#475569" };
  return (
    <span style={{fontSize:11,fontWeight:700,padding:"2px 8px",borderRadius:12,
      background:bg,color,whiteSpace:"nowrap"}}>{label}</span>
  );
}

function FieldControl({ fd, source, manual, onSource, onManual }) {
  if (!fd || fd.status === "unchanged" || fd.status === "db_only") return null;
  return (
    <div style={{background:"#f8fafc",borderRadius:6,padding:"10px 12px",marginBottom:8}}>
      <div style={{fontWeight:600,fontSize:12,marginBottom:8,color:"var(--color-text-muted)",textTransform:"uppercase"}}>{fd.label}</div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:8}}>
        <div style={{background:"#fff",border:"1px solid var(--color-border)",borderRadius:4,padding:"6px 10px",fontSize:13}}>
          <div style={{fontSize:10,color:"var(--color-text-muted)",marginBottom:2}}>DB ATTUALE</div>
          <div>{fd.db_value != null ? String(fd.db_value) : <em style={{color:"var(--color-text-muted)"}}>—</em>}</div>
        </div>
        <div style={{background:"#eff6ff",border:"1px solid #bfdbfe",borderRadius:4,padding:"6px 10px",fontSize:13}}>
          <div style={{fontSize:10,color:"#1e40af",marginBottom:2}}>AI ESTRATTO</div>
          <div>{fd.ai_value != null ? String(fd.ai_value) : <em style={{color:"var(--color-text-muted)"}}>—</em>}</div>
        </div>
      </div>
      <div style={{display:"flex",gap:16}}>
        {["db","ai","manual"].map(s => (
          <label key={s} style={{display:"flex",alignItems:"center",gap:4,cursor:"pointer",fontSize:13}}>
            <input type="radio" checked={source === s} onChange={() => onSource(s)} />
            {s === "db" ? "Mantieni DB" : s === "ai" ? "Usa AI" : "Modifica manuale"}
          </label>
        ))}
      </div>
      {source === "manual" && (
        <input className="form-control" style={{marginTop:8}}
          value={manual || ""} placeholder="Inserisci valore..."
          onChange={e => onManual(e.target.value)} />
      )}
    </div>
  );
}

function ProfileSection({ diff, selections, setSelections }) {
  const allFds    = diff.profile?.field_diffs || [];
  const activeFds = allFds.filter(fd => fd.status !== "unchanged" && fd.status !== "db_only");
  if (activeFds.length === 0) return (
    <div style={{background:"#fff",border:"1px solid var(--color-border)",borderRadius:8,padding:"16px 20px",marginBottom:16}}>
      <div style={{display:"flex",alignItems:"center",gap:8}}>
        <span style={{fontWeight:600}}>👤 Anagrafica</span>
        <StatusBadge status="unchanged" />
        <span style={{fontSize:12,color:"var(--color-text-muted)"}}>Nessuna modifica trovata</span>
      </div>
    </div>
  );
  function upd(field, key, val) {
    setSelections(prev => ({...prev, profile: {...prev.profile, [field]: {...prev.profile[field], [key]: val}}}));
  }
  return (
    <div style={{background:"#fff",border:"1px solid var(--color-border)",borderRadius:8,padding:"16px 20px",marginBottom:16}}>
      <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:12,flexWrap:"wrap"}}>
        <span style={{fontWeight:600}}>👤 Anagrafica</span>
        <span style={{fontSize:12,color:"var(--color-text-muted)"}}>
          Confidenza: {Math.round((diff.profile?.confidence||0)*100)}% · {activeFds.length} campo/i da rivedere
        </span>
        <button className="btn btn-sm btn-secondary" style={{marginLeft:"auto"}}
          onClick={() => {
            const p = {...selections.profile};
            activeFds.forEach(fd => { p[fd.field] = {source:"ai",manual:""}; });
            setSelections(prev => ({...prev, profile: p}));
          }}>Accetta tutto AI</button>
      </div>
      {activeFds.map(fd => (
        <FieldControl key={fd.field} fd={fd}
          source={selections.profile[fd.field]?.source || "db"}
          manual={selections.profile[fd.field]?.manual || ""}
          onSource={s => upd(fd.field, "source", s)}
          onManual={v => upd(fd.field, "manual", v)} />
      ))}
    </div>
  );
}

const TAB_LABELS = {
  skills: "Competenze",
  references: "Esperienze",
  educations: "Formazione",
  certifications: "Certificazioni",
  languages: "Lingue",
};

function ItemsSection({ icon, title, sectionKey, diff, selections, setSelections }) {
  const sec   = diff[sectionKey] || {};
  const items = sec.items || [];
  const [showUnchanged, setShowUnchanged] = useState(false);
  const [showDbOnly,    setShowDbOnly]    = useState(false);

  const activeItems   = items.filter(i => i.status === "new" || i.status === "changed");
  const unchangedItems= items.filter(i => i.status === "unchanged");
  const dbOnlyItems   = items.filter(i => i.status === "db_only");

  function updSel(idx, patch) {
    setSelections(prev => {
      const arr = [...(prev[sectionKey] || [])];
      arr[idx] = { ...arr[idx], ...patch };
      return { ...prev, [sectionKey]: arr };
    });
  }
  function updFieldSrc(idx, field, src) {
    setSelections(prev => {
      const arr = [...(prev[sectionKey] || [])];
      arr[idx] = { ...arr[idx], field_sources: { ...(arr[idx].field_sources || {}), [field]: src } };
      return { ...prev, [sectionKey]: arr };
    });
  }
  function updManual(idx, field, val) {
    setSelections(prev => {
      const arr = [...(prev[sectionKey] || [])];
      arr[idx] = { ...arr[idx], manuals: { ...(arr[idx].manuals || {}), [field]: val } };
      return { ...prev, [sectionKey]: arr };
    });
  }
  function acceptAll() {
    setSelections(prev => {
      const arr = [...(prev[sectionKey] || [])].map((sel, i) => {
        const item = items[i];
        if (!item) return sel;
        if (item.status === "new") return { action: "add" };
        if (item.status === "changed") {
          const fs = {};
          (item.field_diffs || []).filter(fd => fd.status !== "unchanged").forEach(fd => { fs[fd.field] = "ai"; });
          return { action: "update", field_sources: fs, manuals: {} };
        }
        return sel;
      });
      return { ...prev, [sectionKey]: arr };
    });
  }

  if (items.length === 0) return null;

  function getSummary(item) {
    const d = item.ai_data || item.db_data || {};
    return d.skill_name || d.company_name || d.institution || d.name || d.language_name || "—";
  }

  function renderItem(item, idx) {
    const sel = selections[sectionKey]?.[idx];
    const d   = item.ai_data || {};

    if (item.status === "new") {
      const rows = Object.entries(d).filter(([k,v]) => v !== null && v !== undefined && v !== "" && !["level_label","years_experience","degree_type_raw","client_name","activities"].includes(k));
      return (
        <div key={idx} style={{border:"1px solid #86efac",borderRadius:6,padding:"12px 14px",marginBottom:8,background:"#f0fdf4"}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
            <StatusBadge status="new" />
            <span style={{fontWeight:600,fontSize:14}}>{getSummary(item)}</span>
            {d.level_label && <span style={{fontSize:12,color:"#166534"}}>· {d.level_label}{d.years_experience ? ` · ${d.years_experience} anni` : ""}</span>}
            <label style={{marginLeft:"auto",display:"flex",alignItems:"center",gap:4,cursor:"pointer",fontSize:13}}>
              <input type="checkbox" checked={sel?.action === "add"}
                onChange={e => updSel(idx, { action: e.target.checked ? "add" : "skip" })} />
              Aggiungi
            </label>
          </div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"4px 12px"}}>
            {rows.slice(0,6).map(([k,v]) => (
              <div key={k} style={{fontSize:12,color:"#166534"}}>
                <span style={{fontWeight:600}}>{k.replace(/_/g," ")}: </span>
                <span>{Array.isArray(v) ? v.join(", ") : String(v)}</span>
              </div>
            ))}
          </div>
        </div>
      );
    }

    if (item.status === "changed") {
      const changedFds = (item.field_diffs || []).filter(fd => fd.status !== "unchanged" && fd.status !== "db_only");
      return (
        <div key={idx} style={{border:"1px solid #fde68a",borderRadius:6,padding:"12px 14px",marginBottom:8,background:"#fffbeb"}}>
          <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:changedFds.length>0?12:0}}>
            <StatusBadge status="changed" />
            <span style={{fontWeight:600,fontSize:14}}>{getSummary(item)}</span>
            <label style={{marginLeft:"auto",display:"flex",alignItems:"center",gap:4,cursor:"pointer",fontSize:13}}>
              <input type="checkbox" checked={sel?.action === "update"}
                onChange={e => updSel(idx, { action: e.target.checked ? "update" : "skip" })} />
              Aggiorna
            </label>
          </div>
          {changedFds.map(fd => (
            <FieldControl key={fd.field} fd={fd}
              source={sel?.field_sources?.[fd.field] || "db"}
              manual={sel?.manuals?.[fd.field] || ""}
              onSource={s => updFieldSrc(idx, fd.field, s)}
              onManual={v => updManual(idx, fd.field, v)} />
          ))}
        </div>
      );
    }
    return null;
  }

  const hasChanges = sec.count_new > 0 || sec.count_changed > 0;

  return (
    <div style={{background:"#fff",border:"1px solid var(--color-border)",borderRadius:8,padding:"16px 20px",marginBottom:16}}>
      <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:12,flexWrap:"wrap"}}>
        <span style={{fontWeight:600}}>{icon} {title}</span>
        <span style={{fontSize:12,color:"var(--color-text-muted)"}}>
          Confidenza: {Math.round((sec.confidence||0)*100)}%
          {sec.count_new>0      && ` · ${sec.count_new} nuovi`}
          {sec.count_changed>0  && ` · ${sec.count_changed} modificati`}
          {sec.count_unchanged>0 && ` · ${sec.count_unchanged} invariati`}
        </span>
        {hasChanges && (
          <button className="btn btn-sm btn-secondary" style={{marginLeft:"auto"}} onClick={acceptAll}>
            Accetta tutto AI
          </button>
        )}
      </div>

      {activeItems.length === 0 && (
        <p style={{fontSize:13,color:"var(--color-text-muted)"}}>Nessuna aggiunta o modifica trovata.</p>
      )}
      {items.map((item, idx) => renderItem(item, idx)).filter(Boolean)}

      {unchangedItems.length > 0 && (
        <div style={{marginTop:8}}>
          <button className="btn btn-sm btn-secondary" onClick={() => setShowUnchanged(p=>!p)}>
            {showUnchanged ? "Nascondi" : "Mostra"} {unchangedItems.length} invariati
          </button>
          {showUnchanged && unchangedItems.map((item, i) => (
            <div key={i} style={{display:"flex",alignItems:"center",gap:8,padding:"6px 0",fontSize:13,borderBottom:"1px solid var(--color-border)"}}>
              <StatusBadge status="unchanged" /><span>{getSummary(item)}</span>
            </div>
          ))}
        </div>
      )}

      {dbOnlyItems.length > 0 && (
        <div style={{marginTop:8}}>
          <button className="btn btn-sm btn-secondary" onClick={() => setShowDbOnly(p=>!p)}>
            {showDbOnly ? "Nascondi" : "Mostra"} {dbOnlyItems.length} {dbOnlyItems.length === 1 ? "voce presente" : "voci presenti"} nel profilo, non {dbOnlyItems.length === 1 ? "trovata" : "trovate"} nel CV
          </button>
          {showDbOnly && (
            <div style={{marginTop:8,padding:"10px 14px",background:"#fefce8",border:"1px solid #fde047",borderRadius:6,fontSize:13}}>
              <p style={{marginBottom:10,color:"#854d0e",fontWeight:500}}>
                Queste voci sono presenti nel profilo ma non sono state trovate nel CV caricato.
                Rimangono invariate — per modificarle o eliminarle usa la tab <strong>{TAB_LABELS[sectionKey] || title}</strong>.
              </p>
              {dbOnlyItems.map((item, i) => (
                <div key={i} style={{display:"flex",alignItems:"center",gap:8,padding:"6px 10px",marginBottom:4,background:"#fff",borderRadius:4,border:"1px solid #fde047"}}>
                  <StatusBadge status="db_only" />
                  <span style={{fontWeight:500}}>{getSummary(item)}</span>
                  <span style={{fontSize:11,color:"#92400e",fontStyle:"italic",marginLeft:"auto"}}>
                    non trovato nel CV — gestiscilo dalla tab {TAB_LABELS[sectionKey] || title}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ReviewStep({ diff, selections, setSelections, onApply, onCancel, applying, error }) {
  const nChanges = countChanges(diff, selections);
  const conf = Math.round((diff.overall_confidence || 0) * 100);

  function acceptAll() {
    const fresh = initSelections(diff);
    for (const k of Object.keys(fresh.profile)) {
      const fd = (diff.profile?.field_diffs||[]).find(f => f.field === k);
      if (fd && fd.status !== "unchanged") fresh.profile[k].source = "ai";
    }
    ["skills","references","educations","certifications","languages"].forEach(sec => {
      fresh[sec] = fresh[sec].map((sel, i) => {
        const item = diff[sec]?.items?.[i];
        if (!item) return sel;
        if (item.status === "new") return { action: "add" };
        if (item.status === "changed") {
          const fs = {};
          (item.field_diffs||[]).filter(fd=>fd.status!=="unchanged").forEach(fd=>{fs[fd.field]="ai";});
          return { action:"update", field_sources:fs, manuals:{} };
        }
        return sel;
      });
    });
    setSelections(fresh);
  }

  return (
    <div>
      {/* Riepilogo header */}
      <div style={{background:"#fff",border:"1px solid var(--color-border)",borderRadius:8,padding:"16px 20px",marginBottom:16,display:"flex",alignItems:"center",gap:16,flexWrap:"wrap"}}>
        <span style={{fontWeight:700,fontSize:16}}>Revisione modifiche estratte</span>
        <span style={{fontSize:13,color:"var(--color-text-muted)"}}>Confidenza AI: <strong>{conf}%</strong></span>
        <div style={{marginLeft:"auto",display:"flex",gap:8}}>
          <button className="btn btn-sm btn-secondary" onClick={() => setSelections(initSelections(diff))}>Deseleziona tutto</button>
          <button className="btn btn-sm btn-primary"   onClick={acceptAll}>Accetta tutto AI</button>
        </div>
      </div>
      <p style={{fontSize:12,color:"var(--color-text-muted)",marginBottom:16}}>
        Legenda: <strong style={{color:"#166534"}}>NUOVO</strong> = aggiunta · <strong style={{color:"#854d0e"}}>MODIFICA</strong> = da rivedere · INVARIATO = nessuna azione · SOLO DB = non nel CV
      </p>

      <ProfileSection diff={diff} selections={selections} setSelections={setSelections} />
      <ItemsSection icon="🛠" title="Competenze"     sectionKey="skills"         diff={diff} selections={selections} setSelections={setSelections} />
      <ItemsSection icon="💼" title="Esperienze"     sectionKey="references"     diff={diff} selections={selections} setSelections={setSelections} />
      <ItemsSection icon="🎓" title="Formazione"     sectionKey="educations"     diff={diff} selections={selections} setSelections={setSelections} />
      <ItemsSection icon="🏅" title="Certificazioni" sectionKey="certifications" diff={diff} selections={selections} setSelections={setSelections} />
      <ItemsSection icon="🌍" title="Lingue"         sectionKey="languages"      diff={diff} selections={selections} setSelections={setSelections} />

      {error && <div className="alert alert--danger" style={{marginBottom:12}}>{error}</div>}

      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",
        padding:"16px 0",borderTop:"1px solid var(--color-border)",marginTop:8}}>
        <button className="btn btn-secondary" onClick={onCancel}>Annulla</button>
        <button className="btn btn-primary" onClick={onApply}
          disabled={applying || nChanges === 0}>
          {applying ? "Applicando..." : nChanges === 0 ? "Nessuna modifica selezionata" : `Applica ${nChanges} modifica/e`}
        </button>
      </div>
    </div>
  );
}

function SuccessStep({ result, onReset }) {
  const { sections = {}, applied_count = 0 } = result || {};
  const labels = { profile:"Anagrafica", skills:"Competenze", references:"Esperienze",
    educations:"Formazione", certifications:"Certificazioni", languages:"Lingue" };
  return (
    <div className="card" style={{textAlign:"center",padding:"48px 32px"}}>
      <div style={{fontSize:56,marginBottom:12}}>✅</div>
      <h3 style={{marginBottom:8}}>{applied_count} modifiche applicate</h3>
      <p style={{color:"var(--color-text-muted)",marginBottom:24}}>
        Il profilo CV è stato aggiornato con i dati estratti.
      </p>
      <div style={{display:"flex",flexWrap:"wrap",justifyContent:"center",gap:8,marginBottom:32}}>
        {Object.entries(sections).filter(([,v])=>v>0).map(([k,v])=>(
          <span key={k} style={{background:"#dcfce7",color:"#166534",fontSize:13,fontWeight:600,padding:"4px 12px",borderRadius:12}}>
            {labels[k]||k}: +{v}
          </span>
        ))}
      </div>
      <div style={{display:"flex",gap:12,justifyContent:"center"}}>
        <button className="btn btn-secondary" onClick={onReset}>Carica altro CV</button>
      </div>
    </div>
  );
}

// ── Export Tab ────────────────────────────────────────────────────────────────
function ExportTab({ token }) {
  const [templates, setTemplates] = useState([]);
  const [loadingTmpls, setLoadingTmpls] = useState(true);
  const [error, setError]         = useState("");
  const [downloading, setDownloading] = useState(null);

  useEffect(() => {
    listExportTemplates(token)
      .then(data => setTemplates(data.templates || []))
      .catch(err  => setError(err.message))
      .finally(()  => setLoadingTmpls(false));
  }, [token]);

  async function handleDownload(tmpl) {
    setDownloading(tmpl.filename);
    setError("");
    try {
      const blob = await exportCVDocx(token, tmpl.filename);
      const url  = window.URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = tmpl.filename.replace("Template_IT_", "CV_").replace("Template_EN_", "CV_EN_");
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div className="tab-content">
      <h2 className="section-title">Esporta CV</h2>

      {error && <div className="alert alert--danger">{error}</div>}

      {loadingTmpls ? (
        <div className="loading">Caricamento template...</div>
      ) : templates.length === 0 ? (
        <div className="alert alert--warning">Nessun template disponibile.</div>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginTop: 16 }}>
          {templates.map(tmpl => (
            <div key={tmpl.filename} style={{
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              padding: "16px 20px",
              minWidth: 230,
              background: "var(--color-bg-card)",
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{
                  background:   tmpl.language === "EN" ? "#3b82f6" : "#10b981",
                  color:        "#fff",
                  borderRadius: 4,
                  padding:      "2px 8px",
                  fontSize:     11,
                  fontWeight:   700,
                  letterSpacing: 0.5,
                }}>{tmpl.language}</span>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{tmpl.display_name}</span>
              </div>

              {tmpl.language === "EN" && (
                <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                  Traduzione automatica via AI
                </div>
              )}

              <button
                className="btn btn-primary btn-sm"
                disabled={!!downloading}
                onClick={() => handleDownload(tmpl)}
                style={{ marginTop: 4 }}
              >
                {downloading === tmpl.filename ? "Generazione..." : "Scarica DOCX"}
              </button>
            </div>
          ))}
        </div>
      )}

      <div style={{
        marginTop: 24, padding: 12,
        background: "#f8fafc", borderRadius: 6,
        fontSize: 12, color: "var(--color-text-muted)",
        border: "1px solid var(--color-border)",
      }}>
        {/* TODO Admin: aggiungere upload template dalla sezione Admin */}
        I template disponibili sono quelli caricati dall'amministratore nella directory templates.
      </div>
    </div>
  );
}

function UploadTab({ token, cv, setCV }) {
  const [step, setStep]               = useState("upload");
  const [diff, setDiff]               = useState(null);
  const [selections, setSelections]   = useState(null);
  const [applying, setApplying]       = useState(false);
  const [error, setError]             = useState(null);
  const [applyResult, setApplyResult] = useState(null);

  async function handleFile(file) {
    setError(null);
    setStep("processing");
    try {
      const result = await uploadCV(token, file);
      setDiff(result);
      setSelections(initSelections(result));
      setStep("review");
    } catch (e) {
      setError(e.message);
      setStep("upload");
    }
  }

  async function handleApply() {
    setApplying(true);
    setError(null);
    try {
      const req = buildApplyRequest(diff, selections);
      const res = await applyDiff(token, req);
      setApplyResult(res);
      const fresh = await getMyCV(token);
      setCV(fresh);
      setStep("success");
    } catch (e) {
      setError(e.message);
    } finally {
      setApplying(false);
    }
  }

  function reset() {
    setStep("upload"); setDiff(null); setSelections(null);
    setApplyResult(null); setError(null);
  }

  if (step === "processing") return <ProcessingStep />;
  if (step === "success")    return <SuccessStep result={applyResult} onReset={reset} />;
  if (step === "review" && diff && selections) {
    return <ReviewStep diff={diff} selections={selections} setSelections={setSelections}
      onApply={handleApply} onCancel={reset} applying={applying} error={error} />;
  }

  return (
    <div className="card">
      <h3 style={{marginBottom:8}}>Carica CV</h3>
      <p style={{color:"var(--color-text-muted)",marginBottom:24}}>
        Carica il tuo CV (PDF o DOCX). L'AI estrarrà i dati e potrai scegliere
        campo per campo cosa aggiornare nel profilo.
      </p>
      <UploadDropZone onFile={handleFile} error={error} />
      {(cv?.documents?.length || 0) > 0 && (
        <div style={{marginTop:20,paddingTop:16,borderTop:"1px solid var(--color-border)"}}>
          <p style={{fontSize:13,color:"var(--color-text-muted)",marginBottom:8}}>Documenti caricati in precedenza:</p>
          {cv.documents.slice(0,3).map(doc => (
            <div key={doc.id} style={{display:"flex",justifyContent:"space-between",fontSize:13,padding:"4px 0"}}>
              <span>{doc.original_filename}</span>
              <span style={{color:"var(--color-text-muted)"}}>{doc.parse_status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
// ── HintChip — suggerimento inline contestuale ────────────────────────────────
function HintChip({ text, value, onApply }) {
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      background: "#fffbeb", border: "1px solid #fde68a",
      borderRadius: 6, padding: "3px 8px", fontSize: 12,
      color: "#92400e", marginTop: 4,
    }}>
      <span>💡</span>
      <span>{text}{value ? <strong> {value}</strong> : null}</span>
      {onApply && (
        <button
          onClick={onApply}
          style={{
            marginLeft: 4, background: "#f59e0b", color: "#fff",
            border: "none", borderRadius: 4, padding: "1px 7px",
            fontSize: 11, cursor: "pointer", fontWeight: 600,
          }}
        >
          Usa
        </button>
      )}
    </div>
  );
}

// ── AI Suggerimenti Tab ────────────────────────────────────────────────────────
const SECTION_LABELS = {
  profile:        "Profilo",
  skills:         "Competenze",
  experiences:    "Esperienze",
  certifications: "Certificazioni",
  educations:     "Formazione",
  languages:      "Lingue",
};

const PRIORITY_STYLE = {
  HIGH:   { bg: "#fef2f2", border: "#fca5a5", badge: "#dc2626", label: "Alta" },
  MEDIUM: { bg: "#fffbeb", border: "#fde68a", badge: "#d97706", label: "Media" },
  LOW:    { bg: "#f0fdf4", border: "#86efac", badge: "#16a34a", label: "Bassa" },
};

function ScoreGauge({ score }) {
  const color = score >= 75 ? "#16a34a" : score >= 50 ? "#d97706" : "#dc2626";
  return (
    <div style={{ textAlign: "center", marginBottom: 24 }}>
      <div style={{ fontSize: 56, fontWeight: 800, color }}>{Math.round(score)}</div>
      <div style={{ fontSize: 13, color: "var(--color-text-muted)", marginBottom: 8 }}>/ 100 — Qualità CV</div>
      <div style={{ background: "var(--color-border)", borderRadius: 8, height: 10, maxWidth: 300, margin: "0 auto" }}>
        <div style={{ height: 10, borderRadius: 8, background: color, width: `${score}%`, transition: "width .5s" }} />
      </div>
    </div>
  );
}

function SuggestionCard({ s }) {
  const ps = PRIORITY_STYLE[s.priority] || PRIORITY_STYLE.LOW;
  return (
    <div style={{ border: `1px solid ${ps.border}`, borderRadius: 8, padding: "14px 16px", marginBottom: 10, background: ps.bg }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, marginBottom: 6 }}>
        <span style={{ background: ps.badge, color: "#fff", fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 10, whiteSpace: "nowrap", marginTop: 2 }}>
          {ps.label}
        </span>
        <span style={{ fontWeight: 600, fontSize: 14 }}>{s.title}</span>
      </div>
      <p style={{ fontSize: 13, color: "var(--color-text-muted)", margin: 0 }}>{s.description}</p>
      {s.item_ref && (
        <div style={{ marginTop: 6, fontSize: 12, color: "#6b7280" }}>Riferimento: <em>{s.item_ref}</em></div>
      )}
    </div>
  );
}

function AITab({ token }) {
  const [status, setStatus]         = useState("idle"); // idle | loading | done | error
  const [result, setResult]         = useState(null);
  const [errorMsg, setErrorMsg]     = useState("");
  const [activeSection, setSection] = useState("all");

  async function runAnalysis() {
    setStatus("loading");
    setErrorMsg("");
    try {
      const data = await getCVSuggestions(token);
      if (data.status === "error") throw new Error(data.error || "Errore AI");
      setResult(data);
      setStatus("done");
    } catch (e) {
      setErrorMsg(e.message);
      setStatus("error");
    }
  }

  const suggestions = result?.suggestions || [];
  const sections = ["all", ...new Set(suggestions.map(s => s.section))];
  const filtered = activeSection === "all" ? suggestions : suggestions.filter(s => s.section === activeSection);
  const sorted   = [...filtered].sort((a, b) => {
    const order = { HIGH: 0, MEDIUM: 1, LOW: 2 };
    return (order[a.priority] ?? 3) - (order[b.priority] ?? 3);
  });

  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>Analisi AI del CV</h3>
        <button
          className="btn btn-primary"
          onClick={runAnalysis}
          disabled={status === "loading"}
        >
          {status === "loading" ? "Analisi in corso…" : status === "done" ? "Rianalizza" : "Analizza CV"}
        </button>
      </div>

      {status === "idle" && (
        <p style={{ color: "var(--color-text-muted)", marginTop: 16 }}>
          Clicca <strong>Analizza CV</strong> per ricevere suggerimenti personalizzati da AI su come migliorare il tuo profilo.
        </p>
      )}

      {status === "loading" && (
        <div style={{ textAlign: "center", padding: "40px 0", color: "var(--color-text-muted)" }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>🤖</div>
          <p>Analisi in corso, attendi circa 15-30 secondi…</p>
        </div>
      )}

      {status === "error" && (
        <div className="alert alert--error" style={{ marginTop: 16 }}>{errorMsg}</div>
      )}

      {status === "done" && result && (
        <>
          <ScoreGauge score={result.overall_score ?? 0} />

          {result.summary && (
            <div style={{ background: "#f8fafc", borderRadius: 8, padding: "12px 16px", marginBottom: 20, fontSize: 14, color: "#374151", borderLeft: "4px solid var(--color-primary)" }}>
              {result.summary}
            </div>
          )}

          {suggestions.length === 0 ? (
            <div style={{ textAlign: "center", padding: "24px 0", color: "var(--color-text-muted)" }}>
              Nessun suggerimento — CV ottimo!
            </div>
          ) : (
            <>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
                {sections.map(sec => (
                  <button
                    key={sec}
                    onClick={() => setSection(sec)}
                    style={{
                      padding: "4px 12px", borderRadius: 20, fontSize: 13, cursor: "pointer", border: "1px solid var(--color-border)",
                      background: activeSection === sec ? "var(--color-primary)" : "#fff",
                      color: activeSection === sec ? "#fff" : "var(--color-text)",
                      fontWeight: activeSection === sec ? 700 : 400,
                    }}
                  >
                    {sec === "all" ? `Tutti (${suggestions.length})` : `${SECTION_LABELS[sec] || sec} (${suggestions.filter(s => s.section === sec).length})`}
                  </button>
                ))}
              </div>

              {sorted.map((s, i) => <SuggestionCard key={i} s={s} />)}
            </>
          )}
        </>
      )}
    </div>
  );
}

// ── Placeholder View ──────────────────────────────────────────────────────────
function PlaceholderView({ title, onBack, sprint }) {
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <button className="btn btn-secondary btn-sm" onClick={onBack}>← Indietro</button>
        <h2>{title}</h2>
      </div>
      <div className="card">
        <div className="empty-state">
          <div className="empty-state__icon">🚧</div>
          <h3>{title} — {sprint}</h3>
          <p>Questa sezione sarà implementata nel prossimo sprint.</p>
        </div>
      </div>
    </>
  );
}
