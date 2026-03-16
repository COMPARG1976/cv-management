"""
Costruisce cert_catalog.json da tre fonti:
  1. SAP    — learning.sap.com/__NEXT_DATA__ (98 cert con codici objId)
  2. OpenText — lista HTML opzioni dal TrainingRegistry (fornita dall'utente)
  3. Databricks — lista statica (no codici esame su sito ufficiale)

Output: backend/app/cert_catalog.json
"""
import urllib.request, json, re, time, sys, os, html as html_mod

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

OUT_PATH = os.path.join(os.path.dirname(__file__), "backend", "app", "cert_catalog.json")

# ─────────────────────────────────────────────────────────────────────────────
# 1. SAP — pagina per pagina via __NEXT_DATA__
# ─────────────────────────────────────────────────────────────────────────────

def fetch_sap_certs():
    """
    Scarica il catalogo completo SAP via endpoint pubblico JSON,
    filtra le certificazioni (Learning_object_ID che inizia con C_, P_, E_)
    e aggiunge le immagini badge dalla pagina 1 __NEXT_DATA__.
    """
    # 1. Download catalogo completo
    url = "https://learning.sap.com/service/catalog-download/json"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        all_items = json.load(r)
    print(f"  SAP download: {len(all_items)} oggetti totali")

    # 2. Recupera immagini badge dalla pagina 1 (solo 15 ma le più comuni)
    img_map = {}  # objId → imageUrl
    try:
        req2 = urllib.request.Request(
            "https://learning.sap.com/certifications?page=1", headers=HEADERS
        )
        with urllib.request.urlopen(req2, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
        nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.DOTALL)
        if nd:
            nd_data = json.loads(nd.group(1))
            q = nd_data["props"]["pageProps"]["dehydratedState"]["queries"][0]
            for it in q["state"]["data"]["pages"][0].get("results", []):
                if it.get("objId") and it.get("imageUrl"):
                    img_map[it["objId"]] = it["imageUrl"]
    except Exception as e:
        print(f"  (immagini badge non disponibili: {e})", file=sys.stderr)

    # 3. Filtra certificazioni: Learning_object_ID inizia con C_, P_, E_
    entries = []
    seen = set()
    for it in all_items:
        lo_id = (it.get("Learning_object_ID") or "").strip()
        title = (it.get("Title") or "").strip()
        link  = str(it.get("Direct_link") or "").strip()

        # Estrai codice: "C_FIOAD_en-US" → "C_FIOAD", "P_C4H34" → "P_C4H34"
        code_m = re.match(r'^([CEP]_[A-Z0-9]+)', lo_id)
        if not code_m:
            # Prova anche con il titolo "SAP Certified"
            if "SAP Certified" not in title:
                continue
            code_m = None

        cert_code = code_m.group(1) if code_m else None

        # Deduplicazione sul codice (stessa cert in più lingue)
        dedup_key = cert_code or title
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        entries.append({
            "name":      title,
            "vendor":    "SAP",
            "cert_code": cert_code,
            "img_url":   img_map.get(cert_code) or None,
            "credly_id": None,
        })

    print(f"  SAP certificazioni filtrate: {len(entries)}")
    return entries


# ─────────────────────────────────────────────────────────────────────────────
# 2. OpenText — lista HTML opzioni fornita dall'utente
# ─────────────────────────────────────────────────────────────────────────────

OPENTEXT_OPTIONS_RAW = r"""
<option value="1000:3016">1-0181 - Using Content Server - Smart View</option>
<option value="1000:3017">1-0182 - Using Content Server - Enterprise Connect</option>
<option value="1000:2973">1-0184 - Managing Documents in OpenText™ Content Management</option>
<option value="1000:2854">1-0185 - Collaborating in OpenText™ Content Management</option>
<option value="1030:2762">1-0800 - Using Media Management</option>
<option value="1000:3035">1-1710 - Using Brava Enterprise for Content Server (Web browser)</option>
<option value="1000:3271">1-1720 - Using Intelligent Viewing in Extended ECM</option>
<option value="1000:3155">1-2046 - Using Extended ECM for SAP SuccessFactors for Employees</option>
<option value="1000:3156">1-2047 - Using Extended ECM for SAP SuccessFactors for Managers and HR Admins</option>
<option value="1000:2766">1-2101 - Using Vendor Invoice Management for SAP Solutions: Invoice Automation</option>
<option value="1020:1969">1-2921 - Understanding and Using Intelligent Classification Studio</option>
<option value="1021:3621">1-5401 - Content Manager User Fundamentals</option>
<option value="1021:3615">1-5600 - ValueEdge Essentials</option>
<option value="1021:3761">1-5601 - Leveraging OpenText™ DevOps Aviator™ to Streamline and Accelerate Delivery with AI</option>
<option value="1021:3654">1-5660 - Application Lifecycle Management (ALM/QC) Essentials</option>
<option value="1033:2663">1-5901 - OpenText™ eDiscovery Review and Analysis - Case Manager Training & Certification</option>
<option value="1033:3478">1-5902 - Opentext™ eDiscovery Review and Analysis - Power User Training & Certification</option>
<option value="1021:3653">1-6001 - Vertica Essentials</option>
<option value="1021:3616">1-6316 - Operations Bridge Manager (OBM) Fundamentals</option>
<option value="1031:3216">1-6611 - OpenText™ Data Integrator (BizManager) - User Workshop</option>
<option value="1031:3215">1-6612 - OpenText™ Data Integrator (BizManager) - Transformation Mapper Workshop</option>
<option value="1031:3326">1-6613 - OpenText™ Data Integrator (BizManager) - Beyond the Basics</option>
<option value="1031:3327">1-6614 - OpenText™ Data Integrator (BizManager) Mapper Workshop - Advanced Topics</option>
<option value="1031:3211">1-6630 - OpenText™ TrustedLink™ Enterprise Basic Concepts</option>
<option value="1031:3212">1-6631 - OpenText™ TrustedLink™ Enterprise Advanced Mapping</option>
<option value="1031:3197">1-6640 - OpenText™ TrustedLink™ Series i Basic Mapping and Operations</option>
<option value="1031:3198">1-6641 - OpenText™ TrustedLink™ Series i Advanced Mapping</option>
<option value="1031:3199">1-6642 - OpenText™ TrustedLink™ Series i Extended Translation Module</option>
<option value="1031:3214">1-6651 - OpenText™ TrustedLink™ Windows Basic Operations</option>
<option value="1031:3213">1-6652 - OpenText™ TrustedLink™ Windows Catalyst Mapper Workshop</option>
<option value="1031:3340">1-6670 - OpenText™ Contivo™ Mapping</option>
<option value="1030:2381">1-7500 - Qfiniti End User</option>
<option value="1030:2387">1-7507 - OpenText Explore End User</option>
<option value="1030:2892">1-7520 - OpenText™ Web CMS End User</option>
<option value="1030:2893">1-7521 - OpenText™ Web CMS Advanced User</option>
<option value="1030:3331">1-7606 - Using Exstream Content Author</option>
<option value="1030:3458">1-7614 - Using Exstream Empower Documents</option>
<option value="1032:3121">1-8002 - Using Documentum</option>
<option value="1032:2489">1-8414 - Documentum Life Sciences Quality and Manufacturing</option>
<option value="1000:2837">2-0108 - Content Server Business Workspaces</option>
<option value="1000:2976">2-0113 - Content Server Workflow Design</option>
<option value="1000:2977">2-0114 - Content Server Forms Design</option>
<option value="1000:2978">2-0120 - OpenText Records Management</option>
<option value="1000:2979">2-0121 - OpenText Physical Objects</option>
<option value="1000:2590">2-0235 - Extended ECM for Engineering Fundamentals</option>
<option value="1030:3228">2-0801 - Designing Workflows and Managing Processes with Media Management</option>
<option value="1020:2154">2-2910 - OpenText Semantic Strategy Workshop</option>
<option value="1020:2209">2-2933 - Understanding and Building Taxonomies</option>
<option value="1013:2881">2-4912 - Low-code Design for AppWorks Platform</option>
<option value="1021:3638">2-5603 - ValueEdge Functional Test Essentials</option>
<option value="1021:3612">2-5604 - ValueEdge Functional Test Digital Lab</option>
<option value="1021:3649">2-5691 - Using Project and Portfolio Management (PPM) to Plan and Execute Projects</option>
<option value="1021:3589">2-5700 - LoadRunner Enterprise (LRE) Essentials</option>
<option value="1021:3591">2-5701 - LoadRunner Enterprise (LRE) Advanced</option>
<option value="1021:3680">2-5720 - OpenText™ Core Performance Engineering: Scalable Testing Fundamentals</option>
<option value="1033:2664">2-5904 - OpenText™ eDiscovery Data Processing Training & Certification</option>
<option value="1021:3651">2-6003 - Vertica Projection Tuning</option>
<option value="1021:3634">2-6004 - Vertica Aggregate Projection Design</option>
<option value="1011:2246">2-6101 - Working with Magellan Analytics Designer</option>
<option value="1011:2247">2-6103 - Using Magellan Analytics Designer</option>
<option value="1011:2296">2-6151 - Using Magellan Data Discovery</option>
<option value="1011:2520">2-6161 - Cognitive Strategy Workshop</option>
<option value="1021:3592">2-7309 - ArcSight Enterprise Security Manager Advanced Analyst</option>
<option value="1021:3715">2-7329 - ArcSight Recon Analyst</option>
<option value="1030:2382">2-7501 - Qfiniti Application Setup and Design</option>
<option value="1030:2383">2-7505 - Qfiniti Advise Design Workshop</option>
<option value="1030:2386">2-7506 - Qfiniti Survey</option>
<option value="1030:2931">2-7610 - Designing Communications with Exstream Designer</option>
<option value="1030:2969">2-7612 - Designing Communications with Exstream Content Author</option>
<option value="1030:2972">2-7613 - Designing Communications with Exstream Communications Designer</option>
<option value="1030:2975">2-7615 - Designing Communications with Exstream Empower</option>
<option value="1030:3117">2-7618 - Using Exstream Orchestrator Services to Deliver Communications</option>
<option value="1000:3194">2-7621 - Designing Documents with Extended ECM PowerDocs</option>
<option value="1021:3611">2-7704 - Fortify SAST Essentials</option>
<option value="1021:3639">2-7739 - OpenText™ Dynamic Application Security Testing (DAST) Essentials</option>
<option value="1021:3781">2-7740 - OpenText™ ScanCentral Dynamic Application Security Testing Essentials</option>
<option value="1032:2442">2-8301 - Document Sciences: xPression Design Track - xDesign</option>
<option value="1032:2421">2-8302 - Document Sciences: xPression Design Track - xPresso for Adobe InDesign CS5</option>
<option value="1032:2423">2-8304 - Document Sciences: xPression Design Track - xPresso for Word</option>
<option value="1032:2913">2-8701 - Documentum D2 Configuration</option>
<option value="1000:2925">3-0117 - Content Server WebReport Design</option>
<option value="1000:2926">3-0119 - Content Server ActiveView</option>
<option value="1000:2889">3-0127 - OpenText™ Content Management Schema and Report Fundamentals</option>
<option value="1000:2890">3-0128 - Content Server Logging and Troubleshooting Foundation</option>
<option value="1000:3343">3-0132 - Creating an Optimized Search Environment in Extended ECM</option>
<option value="1000:2900">3-0177 - What's New in OpenText™ Content Management</option>
<option value="1000:2542">3-0188 - Content Server System Administration</option>
<option value="1000:3023">3-0189 - Content Server Business Administration</option>
<option value="1000:3225">3-0237 - OpenText Extended ECM for Engineering Business Administration</option>
<option value="1000:2897">3-0300 - OpenText Directory Services Installation and Configuration</option>
<option value="1000:2848">3-0305 - OpenText System Center Manager</option>
<option value="1000:2933">3-0715 - Archive Center Installation and Administration</option>
<option value="1030:3236">3-0803 - Media Management Business Administration</option>
<option value="1030:2744">3-0805 - Implementing OpenText Media Management</option>
<option value="1000:2903">3-1311 - OpenText Extended ECM for Microsoft Office 365 and SharePoint</option>
<option value="1000:3234">3-1711 - Brava Enterprise for Content Server Administration (Web browser)</option>
<option value="1000:1327">3-2010 - Customizing Archiving for SAP Solutions</option>
<option value="1000:1334">3-2011 - Data Archiving for SAP Solutions: Customizing</option>
<option value="1000:1326">3-2015 - Customizing DocuLink for SAP Solutions</option>
<option value="1000:2882">3-2020 - Extended ECM for SAP Solutions Foundation</option>
<option value="1000:3037">3-2038 - OpenText™ Core Archive for SAP Solutions</option>
<option value="1000:3695">3-2044 - OpenText™ Core Content Management for SAP SuccessFactors</option>
<option value="1000:2794">3-2045 - OpenText Extended ECM for SAP SuccessFactors</option>
<option value="1000:2768">3-2105 - Vendor Invoice Management for SAP Solutions: Invoice Automation</option>
<option value="1000:2983">3-2108 - Vendor Invoice Management for SAP Solutions: Beyond Invoice Automation</option>
<option value="1000:2918">3-2201 - OpenText Capture Solutions for SAP</option>
<option value="1000:2776">3-2202 - OpenText Capture Center (OCC)</option>
<option value="1030:2838">3-3710 - OpenText Exstream Communications Server Fundamentals</option>
<option value="1030:2819">3-3730 - OpenText Exstream Communications Server System Administration</option>
<option value="1013:3452">3-4914 - AppWorks Platform Business Administration</option>
<option value="1013:3341">3-4915 - AppWorks Platform System Administration</option>
<option value="1021:3618">3-5402 - Content Manager Administration Fundamentals</option>
<option value="1021:3652">3-5403 - Content Manager Installation Essentials</option>
<option value="1021:3590">3-5450 - OpenText™ Data Protector Business Administration</option>
<option value="1021:3780">3-5628 - OpenText™ Software Delivery Management Business Administration</option>
<option value="1021:3599">3-5665 - OpenText™ Application Quality Management Business Administration</option>
<option value="1021:3646">3-5690 - Project and Portfolio Management (PPM) Configuration</option>
<option value="1000:3709">3-6050 - OpenText™ Knowledge Discovery System Administration Fundamentals</option>
<option value="1011:2249">3-6105 - Managing the Magellan BI & Reporting System</option>
<option value="1011:2297">3-6152 - Administering Magellan Data Discovery</option>
<option value="1011:2798">3-6165 - OpenText Magellan Fundamentals</option>
<option value="1011:2352">3-6201 - Output Transformation Training</option>
<option value="1021:3642">3-6317 - Operations Bridge Manager (OBM) Event Processing, Automation, and Correlation</option>
<option value="1021:3600">3-6318 - Operations Bridge Manager (OBM) Monitoring Automation</option>
<option value="1021:3754">3-6319 - Operations Bridge Manager (OBM) Service Modeling</option>
<option value="1021:3608">3-6331 - Operations Bridge Analytics (OBA) Business Administration</option>
<option value="1021:3628">3-6357 - AI Operations Management Reporting and Dashboards</option>
<option value="1021:3622">3-6358 - OPSB OPTIC Data Lake (ODL) Data Collection</option>
<option value="1021:3605">3-6901 - NNMi Basic Administration and Configuration</option>
<option value="1021:3603">3-6902 - Network Node Manager (NNM) Advanced Business Administration</option>
<option value="1021:3594">3-6917 - Network Automation Essentials</option>
<option value="1021:3633">3-7210 - NetIQ Identity Manager Administration</option>
<option value="1021:3606">3-7211 - NetIQ Identity Manager User Applications</option>
<option value="1021:3596">3-7220 - NetIQ Identity Governance Administration</option>
<option value="1021:3658">3-7230 - NetIQ Access Manager Foundations</option>
<option value="1021:3604">3-7240 - NetIQ Advanced Authentication Administration</option>
<option value="1021:3636">3-7301 - Installing and Configuring ArcSight Platform</option>
<option value="1021:3619">3-7304 - ArcSight ESM Administrator and Analyst</option>
<option value="1021:3657">3-7306 - ArcSight Logger Administration and Operations</option>
<option value="1021:3635">3-7307 - ArcSight Management Center (ArcMC) Administration</option>
<option value="1021:3627">3-7310 - ArcSight Enterprise Security Manager Administration</option>
<option value="1021:3760">3-7320 - ArcSight Security Orchestration Automation and Response Administration and Configuration</option>
<option value="1021:3625">3-7404 - SMAX Application Workflows Design</option>
<option value="1021:3626">3-7407 - SMAX Integration Management</option>
<option value="1021:3620">3-7415 - SMAX Planning and Building</option>
<option value="1021:3641">3-7416 - SMAX Tenant Administration</option>
<option value="1021:3617">3-7432 - UCMDB Essentials</option>
<option value="1021:3595">3-7433 - Universal CMDB Essentials CMS UI</option>
<option value="1021:3624">3-7434 - Universal Discovery Business Administration using Web UI</option>
<option value="1021:3644">3-7435 - UD120 - Universal Discovery Essentials</option>
<option value="1030:2385">3-7504 - Qfiniti Observe Administration</option>
<option value="1030:2389">3-7509 - Qfiniti Interactive Control Element (ICE) Policy Creation</option>
<option value="1030:2583">3-7523 - TeamSite System Administrator</option>
<option value="1030:2391">3-7550 - OpenText LiquidOffice</option>
<option value="1030:3172">3-7617 - Exstream Design and Production Business Administration</option>
<option value="1000:3200">3-7624 - Extended ECM PowerDocs Business Administration</option>
<option value="1030:3440">3-7627 - Exstream Cloud-Native Business Administration</option>
<option value="1021:3704">3-7830 - OpenText™ Structured Data Manager (SDM) Administration</option>
<option value="1021:3730">3-7901 - OpenText™ Cloud Management Business Administration</option>
<option value="1021:3645">3-7917 - HCMX FinOps Business Administration</option>
<option value="1021:3736">3-7928 - OpenText™ Operations Orchestration Operational Administration</option>
<option value="1032:2909">3-8010 - Documentum Technical Fundamentals</option>
<option value="1032:2910">3-8011 - Documentum System Administration Fundamentals</option>
<option value="1032:2985">3-8201 - Intelligent Capture Fundamentals and Administration</option>
<option value="1000:3438">3-8210 - Core Capture Business Administration</option>
<option value="1032:2431">3-8310 - Document Sciences: xPression Admin Track - Enterprise Edition</option>
<option value="1032:2433">3-8311 - Document Sciences: xPression Enterprise Application Integration</option>
<option value="1032:2840">3-8406 - Documentum Capital Projects Express Administration</option>
<option value="1032:2894">3-8802 - InfoArchive Fundamentals</option>
<option value="1000:3170">3-9005 - OpenText Core Content Management Business Administration</option>
<option value="1000:2980">4-0140 - CSIDE Fundamentals for OpenText™ Content Management</option>
<option value="1000:2981">4-0144 - REST API and Content Web Service Fundamentals</option>
<option value="1000:2928">4-0190 - Content Server Smart View Development</option>
<option value="1030:2734">4-0804 - Developing for OpenText Media Management</option>
<option value="1000:2756">4-2310 - OpenText InfoFusion Integration Center Foundation</option>
<option value="1000:2757">4-2311 - Advanced OpenText InfoFusion Integration Center: ECM Object Migrations</option>
<option value="1000:2758">4-2315 - OpenText Magellan Integration Center Boot Camp</option>
<option value="1013:2887">4-4913 - Solution Development for AppWorks Platform</option>
<option value="1021:3656">4-5710 - LoadRunner Professional (LRP) Essentials</option>
<option value="1021:3738">4-5711 - OpenText™ Professional Performance Engineering for Advanced Scripting and Integration</option>
<option value="1021:3640">4-5712 - Virtual User Generator (VuGen) Essentials</option>
<option value="1021:3684">4-5714 - TruClient Scripting for Performance Engineers</option>
<option value="1021:3716">4-5722 - Shift Left Testing with OpenText™ Performance Engineering for Developers</option>
<option value="1021:3593">4-5801 - Unified Functional Testing One (UFT One) Essentials</option>
<option value="1021:3598">4-5802 - Unified Functional Testing One (UFT One) Advanced</option>
<option value="1011:2298">4-6153 - Using Magellan Data Discovery qLoader</option>
<option value="1021:3650">4-7303 - ArcSight FlexConnector Configuration</option>
<option value="1021:3613">4-7930 - Operations Orchestration Citizen Developer</option>
<option value="1032:2826">4-8205 - Intelligent Capture Advanced Recognition</option>
<option value="1032:2827">4-8206 - OpenText™ Capture Designer</option>
<option value="1032:2830">4-8207 - Intelligent Capture Developer</option>
<option value="1032:2992">4-8601 - Documentum xCP Designer</option>
<option value="1000:1265">5-0161 - OpenText Business Analyst Certification Bootcamp</option>
<option value="1000:1267">5-0162 - OpenText Administrator Certification Bootcamp</option>
<option value="1000:1263">5-0163 - OpenText Developer Certification Bootcamp</option>
<option value="1031:3328">6-6701 - EDI 101 - Introduction to Electronic Data Interchange</option>
<option value="1031:3329">6-6702 - EDI 201 - Relational Map Planning</option>
<option value="1031:3330">6-6703 - EDIFACT 101 - Introduction to EDIFACT EDI</option>
<option value="1021:3623">ALM Octane Fundamentals</option>
<option value="1021:3614">Application Performance Management Advanced</option>
<option value="1021:3631">Application Performance Management Essentials</option>
<option value="1021:3686">CCF-SAUTO - Concepts, Components & Functions of  SMAX (Germany CUSTOM)</option>
<option value="1000:3756">CIW: Certified Instructor Workshop</option>
<option value="1001:1005">Collections Server System Administration on Linux/UNIX</option>
<option value="1001:1126">Collections Server System Administration on Windows</option>
<option value="1021:3643">Configuration Management System Advanced</option>
<option value="1033:2646">DF120 - Foundations in Digital Forensics with EnCase</option>
<option value="1033:2652">DF125 - Mobile Device Examinations with EnCase</option>
<option value="1033:2599">DF210 - Building an Investigation with EnCase</option>
<option value="1033:2625">DF310 - EnCase Certified Examiner Prep</option>
<option value="1033:2598">DF320 - Advanced Analysis of Windows Artifacts with EnCase</option>
<option value="1033:2628">DF410 - NTFS Examinations with EnCase</option>
<option value="1033:2629">DF420 - Mac Examinations with EnCase</option>
<option value="1033:2615">DFIR130 - OpenText Endpoint Investigator | Endpoint Forensics and Response Training</option>
<option value="1033:2649">DFIR350 - Internet-based Investigation with EnCase</option>
<option value="1033:2647">DFIR370 - Host Intrusion Methodology and Investigation</option>
<option value="1033:2626">DFIR450 - EnCase EnScript Programming</option>
<option value="1033:2624">ED290 - eDiscovery Training with OpenText™ Information Assurance</option>
<option value="1021:3602">Flow Development using OO Studio</option>
<option value="1033:2648">IR250 - Incident Investigation</option>
<option value="1021:3607">NOM OPTIC Data Lake Reporting</option>
<option value="1021:3601">Operations Orchestration Administration</option>
<option value="1001:1007">Quickstart Database Administration</option>
<option value="1021:3609">SBM Advanced Designer</option>
<option value="1021:3610">SBM Designer & Administrator</option>
<option value="1021:3632">Service Management Automation X  Essentials for Service Desk Agents</option>
<option value="1021:3630">Service Management Automation X (SMAX) Essentials for Suite Administrators</option>
<option value="1021:3629">Service Management Automation X Essentials for Support Engineers</option>
<option value="1021:3647">Service Manager Administration</option>
<option value="1021:3648">Service Manager Advanced</option>
<option value="1021:3655">Service Manager Foundations for Process Owners</option>
<option value="1021:3597">SiteScope Essentials</option>
<option value="1001:1464">Thesaurus Database Administration</option>
<option value="1001:2145">Using Library Management</option>
<option value="1001:1065">Webtop Administration</option>
"""

# Filtra: scarta corsi "Custom private course", "Germany CUSTOM", "CIW: Certified Instructor"
SKIP_PATTERNS = [
    r'custom private course',
    r'germany custom',
    r'ciw:?\s*certified instructor',
    r'quickstart database',
    r'thesaurus database',
    r'using library management',
    r'webtop administration',
    r'collections server system',
]

def parse_opentext_options():
    entries = []
    for m in re.finditer(r'<option[^>]*value="([^"]+)"[^>]*>([^<]+)</option>', OPENTEXT_OPTIONS_RAW):
        prod_course_id = m.group(1)          # es. "1000:3016"
        raw_label = html_mod.unescape(m.group(2)).strip()

        # Salta voci non desiderate
        skip = False
        for pat in SKIP_PATTERNS:
            if re.search(pat, raw_label, re.IGNORECASE):
                skip = True
                break
        if skip:
            continue

        # Estrai cert_code dal label: pattern "CODICE - Descrizione"
        # Codici validi: "1-0181", "DF120", "DFIR130", "ED290", "IR250", "ALM", "CCF-SAUTO", etc.
        code_m = re.match(r'^([A-Z0-9][A-Z0-9\-]{1,12})\s*-\s+(.+)$', raw_label)
        if code_m:
            cert_code = code_m.group(1).strip()
            name      = code_m.group(2).strip()
            # Scarta codici numerici puri tipo "1", "10", ecc.
            if re.match(r'^\d+$', cert_code):
                cert_code = None
                name = raw_label
        else:
            cert_code = None
            name = raw_label

        entries.append({
            "name":      name,
            "vendor":    "OpenText",
            "cert_code": cert_code,
            "img_url":   None,
            "credly_id": None,
        })

    return entries


# ─────────────────────────────────────────────────────────────────────────────
# 3. Databricks — lista statica con codici ufficiali
# ─────────────────────────────────────────────────────────────────────────────

DATABRICKS_CERTS = [
    {"name": "Databricks Certified Associate Developer for Apache Spark",    "cert_code": "databricks-associate-developer-apache-spark"},
    {"name": "Databricks Certified Data Engineer Associate",                  "cert_code": "databricks-data-engineer-associate"},
    {"name": "Databricks Certified Data Engineer Professional",               "cert_code": "databricks-data-engineer-professional"},
    {"name": "Databricks Certified Machine Learning Associate",               "cert_code": "databricks-machine-learning-associate"},
    {"name": "Databricks Certified Machine Learning Professional",            "cert_code": "databricks-machine-learning-professional"},
    {"name": "Databricks Certified Data Analyst Associate",                   "cert_code": "databricks-data-analyst-associate"},
    {"name": "Databricks Certified Generative AI Engineer Associate",         "cert_code": "databricks-generative-ai-engineer-associate"},
    {"name": "Databricks Certified Hadoop Migration Architect",               "cert_code": "databricks-hadoop-migration-architect"},
    {"name": "Databricks Certified Platform Administrator",                   "cert_code": "databricks-platform-administrator"},
    {"name": "Databricks Certified Lakehouse Platform Expert",                "cert_code": "databricks-lakehouse-platform-expert"},
]

def build_databricks():
    return [
        {"name": d["name"], "vendor": "Databricks", "cert_code": d["cert_code"],
         "img_url": None, "credly_id": None}
        for d in DATABRICKS_CERTS
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Fetching SAP certifications ===")
    sap = fetch_sap_certs()
    print(f"SAP: {len(sap)} voci")

    print("\n=== Parsing OpenText options ===")
    ot = parse_opentext_options()
    print(f"OpenText: {len(ot)} voci")
    # Mostra 5 esempi con codice
    coded = [e for e in ot if e["cert_code"]]
    print(f"  con codice: {len(coded)}, es: {[(e['cert_code'], e['name'][:40]) for e in coded[:5]]}")

    print("\n=== Databricks static list ===")
    db_certs = build_databricks()
    print(f"Databricks: {len(db_certs)} voci")

    all_entries = sap + ot + db_certs
    print(f"\nTotale: {len(all_entries)} voci")
    print(f"  SAP con codice: {sum(1 for e in sap if e['cert_code'])}/{len(sap)}")
    print(f"  OpenText con codice: {sum(1 for e in ot if e['cert_code'])}/{len(ot)}")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, ensure_ascii=False, indent=2)
    print(f"\nSalvato: {OUT_PATH} ({os.path.getsize(OUT_PATH)//1024} KB)")
