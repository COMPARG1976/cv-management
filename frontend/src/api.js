/**
 * HTTP client wrapper per il backend CV Management.
 * Pattern identico a IT_RESOURCE_MGMT: fetch + Bearer token + error extraction.
 */
const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8002";

async function apiFetch(path, options = {}, token = null) {
  const headers = { "Content-Type": "application/json", ...options.headers };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      message = body.detail || JSON.stringify(body.errors) || message;
    } catch (_) {}
    throw new Error(message);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(email, password) {
  const form = new URLSearchParams({ username: email, password });
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Login fallito");
  }
  return res.json();
}

export async function getAuthConfig() {
  return apiFetch("/auth/config");
}

export async function entraExchange(code, redirectUri) {
  return apiFetch("/auth/entra/exchange", {
    method: "POST",
    body: JSON.stringify({ code, redirect_uri: redirectUri }),
  });
}

// ── Users (ADMIN) ─────────────────────────────────────────────────────────────

export async function getUsers(token) {
  return apiFetch("/users", {}, token);
}

export async function createUser(token, data) {
  return apiFetch("/users", { method: "POST", body: JSON.stringify(data) }, token);
}

export async function updateUser(token, userId, data) {
  return apiFetch(`/users/${userId}`, { method: "PUT", body: JSON.stringify(data) }, token);
}

// ── CV ────────────────────────────────────────────────────────────────────────

export async function getMyCV(token) {
  return apiFetch("/cv/me", {}, token);
}

export async function getCVByUserId(token, userId) {
  return apiFetch(`/cv/${userId}`, {}, token);
}

export async function updateMyCV(token, data) {
  return apiFetch("/cv/me", { method: "PUT", body: JSON.stringify(data) }, token);
}

// ── Skill ─────────────────────────────────────────────────────────────────────

export async function addSkill(token, data) {
  return apiFetch("/cv/me/skills", { method: "POST", body: JSON.stringify(data) }, token);
}

export async function updateSkill(token, skillId, data) {
  return apiFetch(`/cv/me/skills/${skillId}`, { method: "PUT", body: JSON.stringify(data) }, token);
}

export async function deleteSkill(token, skillId) {
  return apiFetch(`/cv/me/skills/${skillId}`, { method: "DELETE" }, token);
}

// ── Education ─────────────────────────────────────────────────────────────────

export async function addEducation(token, data) {
  return apiFetch("/cv/me/educations", { method: "POST", body: JSON.stringify(data) }, token);
}

export async function updateEducation(token, eduId, data) {
  return apiFetch(`/cv/me/educations/${eduId}`, { method: "PUT", body: JSON.stringify(data) }, token);
}

export async function deleteEducation(token, eduId) {
  return apiFetch(`/cv/me/educations/${eduId}`, { method: "DELETE" }, token);
}

// ── Language ──────────────────────────────────────────────────────────────────

export async function addLanguage(token, data) {
  return apiFetch("/cv/me/languages", { method: "POST", body: JSON.stringify(data) }, token);
}

export async function updateLanguage(token, langId, data) {
  return apiFetch(`/cv/me/languages/${langId}`, { method: "PUT", body: JSON.stringify(data) }, token);
}

export async function deleteLanguage(token, langId) {
  return apiFetch(`/cv/me/languages/${langId}`, { method: "DELETE" }, token);
}

// ── Role ──────────────────────────────────────────────────────────────────────

export async function addRole(token, data) {
  return apiFetch("/cv/me/roles", { method: "POST", body: JSON.stringify(data) }, token);
}

export async function deleteRole(token, roleId) {
  return apiFetch(`/cv/me/roles/${roleId}`, { method: "DELETE" }, token);
}

// ── Reference ─────────────────────────────────────────────────────────────────

export async function addReference(token, data) {
  return apiFetch("/cv/me/references", { method: "POST", body: JSON.stringify(data) }, token);
}

export async function updateReference(token, refId, data) {
  return apiFetch(`/cv/me/references/${refId}`, { method: "PUT", body: JSON.stringify(data) }, token);
}

export async function deleteReference(token, refId) {
  return apiFetch(`/cv/me/references/${refId}`, { method: "DELETE" }, token);
}

// ── Certification ─────────────────────────────────────────────────────────────

export async function addCertification(token, data) {
  return apiFetch("/cv/me/certifications", { method: "POST", body: JSON.stringify(data) }, token);
}

export async function updateCertification(token, certId, data) {
  return apiFetch(`/cv/me/certifications/${certId}`, { method: "PUT", body: JSON.stringify(data) }, token);
}

export async function deleteCertification(token, certId) {
  return apiFetch(`/cv/me/certifications/${certId}`, { method: "DELETE" }, token);
}

// ── Experience ────────────────────────────────────────────────────────────────

export async function addExperience(token, data) {
  return apiFetch("/cv/me/experiences", { method: "POST", body: JSON.stringify(data) }, token);
}

export async function deleteExperience(token, expId) {
  return apiFetch(`/cv/me/experiences/${expId}`, { method: "DELETE" }, token);
}

// ── Upload & Parsing ──────────────────────────────────────────────────────────

export async function uploadCV(token, file, { aiUpdate = true, tags = [] } = {}) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("ai_update", aiUpdate ? "true" : "false");
  formData.append("tags", JSON.stringify(tags));
  const res = await fetch(`${BASE_URL}/upload/cv`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Upload fallito");
  }
  return res.json();
}

export async function getDocuments(token) {
  return apiFetch("/upload/documents", {}, token);
}

export async function downloadDocument(token, docId, filename = "cv_document") {
  const res = await fetch(`${BASE_URL}/upload/documents/${docId}/download`, {
    headers: { Authorization: `Bearer ${token}` },
    redirect: "follow",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Download fallito");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export async function deleteDocument(token, docId) {
  return apiFetch(`/upload/documents/${docId}`, { method: "DELETE" }, token);
}

export async function getParseResult(token, documentId) {
  return apiFetch(`/upload/parse-result/${documentId}`, {}, token);
}

// ── Skills (tassonomia + autocomplete) ────────────────────────────────────────

export async function searchSkills(q, limit = 20) {
  return apiFetch(`/skills?q=${encodeURIComponent(q)}&limit=${limit}`);
}

export async function getSkillSuggestions(token, q = "") {
  return apiFetch(`/cv/skills/suggest?q=${encodeURIComponent(q)}&limit=20`, {}, token);
}

export async function getCertSuggestions(token, q = "") {
  return apiFetch(`/cv/certifications/suggest?q=${encodeURIComponent(q)}&limit=20`, {}, token);
}

// ── Search / API Pubblica ─────────────────────────────────────────────────────

export async function searchResources(token, params = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/api/v1/resources/search?${qs}`, {}, token);
}

export async function getResources(token, params = {}) {
  const qs = new URLSearchParams(params).toString();
  return apiFetch(`/api/v1/resources?${qs}`, {}, token);
}

// ── Upload & Diff Apply ───────────────────────────────────────────────────────

export async function applyDiff(token, payload) {
  return apiFetch("/upload/apply", { method: "POST", body: JSON.stringify(payload) }, token);
}

// ── CV Hints (DB-driven) ──────────────────────────────────────────────────────

export async function getCVHints(token) {
  return apiFetch("/cv/me/hints", {}, token);
}

// ── Export CV DOCX ────────────────────────────────────────────────────────────

export async function listExportTemplates(token) {
  return apiFetch("/export/templates", {}, token);
}

export async function exportCVDocx(token, templateFilename) {
  const res = await fetch(
    `${BASE_URL}/export/cv/docx?template=${encodeURIComponent(templateFilename)}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Export fallito");
  }
  return res.blob();
}

// ── Export ────────────────────────────────────────────────────────────────────

export async function exportSearchExcel(token, params = {}) {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`${BASE_URL}/export/excel?${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Export fallito");
  return res.blob();
}


// ── Certification — file upload / download ───────────────────────────────────

export async function uploadCertDoc(token, certId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(
    `${BASE_URL}/cv/me/certifications/${certId}/upload-doc`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Upload documento fallito");
  }
  return res.json();
}

export async function deleteCertDoc(token, certId) {
  const res = await fetch(
    `${BASE_URL}/cv/me/certifications/${certId}/upload-doc`,
    { method: "DELETE", headers: { Authorization: `Bearer ${token}` } }
  );
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Eliminazione documento fallita");
  }
}

export function downloadCertDocUrl(token, certId) {
  // Restituisce URL per download diretto (aperto in nuova tab)
  return `${BASE_URL}/cv/me/certifications/${certId}/download-doc?token=${token}`;
}

export async function downloadCredlyPdf(token, certId, save = false) {
  // Se save=false → redirect al PDF Credly (apre tab di download)
  // Se save=true  → scarica e salva come uploaded_file_path, ritorna CertificationResponse
  const url = `${BASE_URL}/cv/me/certifications/${certId}/credly-pdf?save=${save}`;
  if (!save) {
    // Apre il redirect direttamente nel browser
    const a = document.createElement("a");
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    // Aggiungi auth header manualmente tramite fetch+blob
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Download PDF Credly fallito");
    }
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    a.href = blobUrl;
    a.download = `credly_badge_${certId}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
    return null;
  } else {
    return apiFetch(`/cv/me/certifications/${certId}/credly-pdf?save=true`, {}, token);
  }
}

// ── Certification — Credly ────────────────────────────────────────────────────

export async function previewCredlyBadges(token, credlyUrl) {
  return apiFetch(
    `/cv/certifications/credly/preview?url=${encodeURIComponent(credlyUrl)}`,
    {},
    token
  );
}

export async function importCredlyBadges(token, badges) {
  return apiFetch(
    "/cv/certifications/credly/import",
    { method: "POST", body: JSON.stringify({ badges }) },
    token
  );
}

// ── Cert Catalog ──────────────────────────────────────────────────────────────

export async function searchCertCatalog(token, q, vendor = "") {
  const params = new URLSearchParams({ q, limit: 10 });
  if (vendor) params.set("vendor", vendor);
  return apiFetch(`/cv/cert-catalog/search?${params}`, {}, token);
}

export async function suggestCertCodes(token, names) {
  // names: { cert_id: cert_name, ... }
  return apiFetch(
    "/cv/cert-catalog/suggest-codes",
    { method: "POST", body: JSON.stringify({ names }) },
    token
  );
}

export async function refreshCertCatalog(token) {
  return apiFetch("/cv/cert-catalog/refresh", { method: "POST" }, token);
}
