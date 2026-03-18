import urllib.request, json, time, sys, re, unicodedata
from difflib import SequenceMatcher

# ── 1. Fetch Credly ──────────────────────────────────────────────────────────
def fetch_all_badges(org_slug):
    badges, url, page = [], f"https://www.credly.com/organizations/{org_slug}/badges.json?page=1", 1
    while url:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.load(r)
            data = d.get("data", []) if isinstance(d, dict) else d
            badges.extend(data)
            url = d.get("metadata", {}).get("next_page_url")
            page += 1
            if page % 5 == 0: print(f"  {org_slug}: {len(badges)}...", flush=True)
            if url: time.sleep(0.2)
        except Exception as e:
            print(f"  ERR {org_slug} p{page}: {e}", flush=True); break
    return badges

print("Fetching SAP..."); sap   = fetch_all_badges("sap");      print(f"  SAP: {len(sap)}")
print("Fetching OpenText..."); otx = fetch_all_badges("opentext"); print(f"  OpenText: {len(otx)}")

# ── 2. Databricks statico ────────────────────────────────────────────────────
databricks_static = [
    {"name": "Databricks Certified Associate Developer for Apache Spark",   "cert_code": "databricks-associate-developer-apache-spark", "vendor": "Databricks"},
    {"name": "Databricks Certified Data Engineer Associate",                 "cert_code": "databricks-data-engineer-associate",          "vendor": "Databricks"},
    {"name": "Databricks Certified Data Engineer Professional",              "cert_code": "databricks-data-engineer-professional",       "vendor": "Databricks"},
    {"name": "Databricks Certified Machine Learning Associate",              "cert_code": "databricks-machine-learning-associate",       "vendor": "Databricks"},
    {"name": "Databricks Certified Machine Learning Professional",           "cert_code": "databricks-machine-learning-professional",    "vendor": "Databricks"},
    {"name": "Databricks Certified Data Analyst Associate",                  "cert_code": "databricks-data-analyst-associate",           "vendor": "Databricks"},
    {"name": "Databricks Certified Generative AI Engineer Associate",        "cert_code": "databricks-generative-ai-engineer-associate", "vendor": "Databricks"},
    {"name": "Databricks Certified Hadoop Migration Architect",              "cert_code": "databricks-hadoop-migration-architect",       "vendor": "Databricks"},
]

# ── 3. Normalizza catalog Credly → lista flat ────────────────────────────────
def credly_to_entry(b, vendor):
    bt = b.get("badge_template", b)
    name = (bt.get("name") or b.get("name") or "").strip()
    img  = bt.get("image", {})
    img_url = img.get("url", "") if isinstance(img, dict) else str(img)
    # tenta di estrarre cert_code dal nome (pattern SAP: C_xxx, E_xxx, P_xxx)
    m = re.match(r'^([CEP]_[A-Z0-9_]+)\b', name)
    code = m.group(1) if m else ""
    return {
        "name":     name,
        "cert_code": code,
        "vendor":   vendor,
        "img_url":  img_url,
        "credly_id": bt.get("id", b.get("id", "")),
    }

catalog = []
for b in sap: catalog.append(credly_to_entry(b, "SAP"))
for b in otx: catalog.append(credly_to_entry(b, "OpenText"))
for d in databricks_static: catalog.append({**d, "img_url": "", "credly_id": ""})

print(f"\nCatalog totale: {len(catalog)} voci")

# ── 4. Leggi DB ──────────────────────────────────────────────────────────────
import subprocess
db_out = subprocess.check_output([
    "docker","exec","cv_mgmt_db","psql","-U","cv_user","-d","cv_management",
    "-c", "SELECT id, name, issuing_org, cert_code FROM certifications ORDER BY name;",
    "--no-align","--field-separator=|","--tuples-only"
], text=True)
db_certs = []
for line in db_out.strip().splitlines():
    parts = line.split("|")
    if len(parts) >= 4:
        db_certs.append({"id": parts[0].strip(), "name": parts[1].strip(),
                         "issuing_org": parts[2].strip(), "cert_code": parts[3].strip()})
print(f"DB certifications: {len(db_certs)}")

# ── 5. Matching ──────────────────────────────────────────────────────────────
def normalize(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    s = re.sub(r'\b(sap certified|certified|associate|professional|specialist|application|development|technology)\b', '', s)
    return re.sub(r'\s+', ' ', s).strip()

cat_norm = [(normalize(e["name"]), e) for e in catalog]

results = []
for db in db_certs:
    db_norm = normalize(db["name"])
    # rimuovi prefisso codice se già nel nome (es. "C_BW4H_2404 - SAP Certified...")
    db_clean = re.sub(r'^[CEP]_[A-Z0-9_]+\s*[-–]\s*', '', db_norm).strip()

    best_score, best_match = 0, None
    for cat_n, entry in cat_norm:
        s = SequenceMatcher(None, db_clean or db_norm, cat_n).ratio()
        if s > best_score:
            best_score, best_match = s, entry

    results.append({
        "db_id":         db["id"],
        "db_name":       db["name"],
        "db_issuing_org": db["issuing_org"],
        "db_cert_code":  db["cert_code"],
        "match_score":   round(best_score, 3),
        "match_name":    best_match["name"]    if best_match else "",
        "match_code":    best_match["cert_code"] if best_match else "",
        "match_vendor":  best_match["vendor"]  if best_match else "",
        "match_img":     best_match.get("img_url","") if best_match else "",
    })

results.sort(key=lambda x: -x["match_score"])

# ── 6. Stampa analisi ────────────────────────────────────────────────────────
thresholds = [(0.85, "OTTIMO"), (0.70, "BUONO"), (0.50, "PARZIALE"), (0, "DEBOLE")]

def tier(s):
    for t, label in thresholds:
        if s >= t: return label
    return "DEBOLE"

print("\n" + "="*100)
print(f"{'DB NAME':<60} {'SCORE':>6} {'TIER':<8} {'MATCHED NAME':<50} {'CODE'}")
print("="*100)
for r in results:
    t = tier(r["match_score"])
    print(f"{r['db_name'][:59]:<60} {r['match_score']:>6.3f} {t:<8} {r['match_name'][:49]:<50} {r['match_code']}")

# ── 7. Riepilogo ─────────────────────────────────────────────────────────────
counts = {}
for r in results:
    t = tier(r["match_score"])
    counts[t] = counts.get(t, 0) + 1
print("\n" + "="*50)
print("RIEPILOGO MATCH")
for label in ["OTTIMO","BUONO","PARZIALE","DEBOLE"]:
    n = counts.get(label, 0)
    pct = n*100//len(results) if results else 0
    print(f"  {label:<10}: {n:>3} ({pct}%)")
print(f"  TOTALE    : {len(results)}")

# ── 8. Salva catalog definitivo ──────────────────────────────────────────────
out = "C:/20.PROGETTI_CLAUDE_CODE/40.CV_MANAGEMENT/backend/app/cert_catalog.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(catalog, f, ensure_ascii=False, indent=2)
print(f"\nCatalog salvato in: {out} ({len(catalog)} voci)")
