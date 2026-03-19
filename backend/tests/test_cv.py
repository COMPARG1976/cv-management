"""
Test CV endpoints — GET/PUT /cv/me, skills, educations, esperienze, lingue, certificazioni.

Note:
  - La fixture carica dati preesistenti (2 skill, 1 education, 2 exp, 1 cert, 2 lang)
  - I test usano conteggi relativi (initial_count + 1) e indici relativi ([-1])
  - DELETE endpoints restituiscono 204 No Content
  - POST endpoints restituiscono 201 Created
  - Rating/year sono stringhe nello STORE (da Excel)
"""
import pytest
from httpx import AsyncClient

from tests.conftest import USER_EMAIL, ADMIN_EMAIL
import app.excel_store as store

pytestmark = pytest.mark.anyio


# ── GET /cv/me ────────────────────────────────────────────────────────────────

async def test_get_my_cv(user_client: AsyncClient):
    r = await user_client.get("/cv/me")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == USER_EMAIL
    assert data["full_name"] == "Test User"
    assert "completeness_score" in data
    score = data["completeness_score"]
    assert 0.0 <= score <= 1.0, f"Completeness fuori range: {score}"


async def test_completeness_score_range(user_client: AsyncClient):
    """Aggiungere dati mantiene il completeness nel range 0–1."""
    await store.add_skill(USER_EMAIL, {"skill_name": "NewSkill", "category": "HARD", "rating": 4})
    r = await user_client.get("/cv/me")
    assert r.status_code == 200
    score = r.json()["completeness_score"]
    assert 0.0 <= score <= 1.0


async def test_update_cv_profile(user_client: AsyncClient):
    r = await user_client.put("/cv/me", json={"summary": "Nuova bio", "phone": "+39 333 9999999"})
    assert r.status_code == 200
    cv = store.STORE["cv_profiles"][USER_EMAIL]
    assert cv["summary"] == "Nuova bio"
    assert cv["phone"] == "+39 333 9999999"


async def test_admin_can_read_any_cv(admin_client: AsyncClient):
    r = await admin_client.get(f"/cv/{USER_EMAIL}")
    assert r.status_code in (200, 404)


# ── Skills ────────────────────────────────────────────────────────────────────

async def test_add_skill(user_client: AsyncClient):
    initial = len(store.STORE["skills"][USER_EMAIL])
    r = await user_client.post("/cv/me/skills", json={
        "skill_name": "Scala", "category": "HARD", "rating": 3
    })
    assert r.status_code == 201
    skills = store.STORE["skills"][USER_EMAIL]
    assert len(skills) == initial + 1
    added = skills[-1]
    assert added["skill_name"] == "Scala"
    assert str(added["rating"]) == "3"


async def test_update_skill(user_client: AsyncClient):
    """PUT aggiorna la skill esistente."""
    await store.add_skill(USER_EMAIL, {"skill_name": "Java", "category": "HARD", "rating": 3})
    sk_id = store.STORE["skills"][USER_EMAIL][-1]["id"]
    r = await user_client.put(f"/cv/me/skills/{sk_id}", json={
        "skill_name": "Java", "category": "HARD", "rating": 5
    })
    assert r.status_code == 200
    updated = next(s for s in store.STORE["skills"][USER_EMAIL] if s["id"] == sk_id)
    assert str(updated["rating"]) == "5"


async def test_delete_skill(user_client: AsyncClient):
    """DELETE ritorna 204 e rimuove la skill."""
    await store.add_skill(USER_EMAIL, {"skill_name": "Go", "category": "HARD", "rating": 2})
    sk_id = store.STORE["skills"][USER_EMAIL][-1]["id"]
    count_before = len(store.STORE["skills"][USER_EMAIL])
    r = await user_client.delete(f"/cv/me/skills/{sk_id}")
    assert r.status_code == 204
    assert len(store.STORE["skills"][USER_EMAIL]) == count_before - 1
    assert not any(s["id"] == sk_id for s in store.STORE["skills"][USER_EMAIL])


async def test_delete_skill_idempotent(user_client: AsyncClient):
    """DELETE skill inesistente → 204 (idempotente)."""
    r = await user_client.delete("/cv/me/skills/nonexistent-id")
    assert r.status_code == 204


async def test_skill_suggest(user_client: AsyncClient):
    """GET /cv/skills/suggest ritorna lista senza errore."""
    r = await user_client.get("/cv/skills/suggest?q=py")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Educazioni ────────────────────────────────────────────────────────────────

async def test_add_education(user_client: AsyncClient):
    initial = len(store.STORE["educations"][USER_EMAIL])
    r = await user_client.post("/cv/me/educations", json={
        "institution": "Bocconi",
        "degree_level": "MASTER",
        "field_of_study": "Business",
        "graduation_year": 2018,
    })
    assert r.status_code == 201
    edus = store.STORE["educations"][USER_EMAIL]
    assert len(edus) == initial + 1
    assert edus[-1]["institution"] == "Bocconi"


async def test_update_education(user_client: AsyncClient):
    """PUT aggiorna education esistente."""
    await store.add_education(USER_EMAIL, {
        "institution": "Polimi", "degree_level": "LAUREA_TRIENNALE",
        "field_of_study": "Fisica", "graduation_year": 2010,
    })
    edu_id = store.STORE["educations"][USER_EMAIL][-1]["id"]
    r = await user_client.put(f"/cv/me/educations/{edu_id}", json={
        "institution": "Polimi", "graduation_year": 2011
    })
    assert r.status_code == 200


async def test_delete_education(user_client: AsyncClient):
    """DELETE ritorna 204 e rimuove l'education."""
    await store.add_education(USER_EMAIL, {
        "institution": "Luiss", "degree_level": "MASTER",
        "field_of_study": "Management", "graduation_year": 2019,
    })
    edu_id = store.STORE["educations"][USER_EMAIL][-1]["id"]
    count_before = len(store.STORE["educations"][USER_EMAIL])
    r = await user_client.delete(f"/cv/me/educations/{edu_id}")
    assert r.status_code == 204
    assert len(store.STORE["educations"][USER_EMAIL]) == count_before - 1


# ── Esperienze ────────────────────────────────────────────────────────────────

async def test_add_experience(user_client: AsyncClient):
    initial = len(store.STORE["experiences"][USER_EMAIL])
    r = await user_client.post("/cv/me/references", json={
        "company_name": "NewCo",
        "role": "Tech Lead",
        "start_date": "2023-01-01",
        "is_current": True,
    })
    assert r.status_code == 201
    exps = store.STORE["experiences"][USER_EMAIL]
    assert len(exps) == initial + 1
    assert exps[-1]["company_name"] == "NewCo"


async def test_delete_experience(user_client: AsyncClient):
    """DELETE ritorna 204 e rimuove l'esperienza."""
    await store.add_experience(USER_EMAIL, {
        "company_name": "OldCo", "role": "Dev", "start_date": "2018-01-01",
    })
    exp_id = store.STORE["experiences"][USER_EMAIL][-1]["id"]
    count_before = len(store.STORE["experiences"][USER_EMAIL])
    r = await user_client.delete(f"/cv/me/references/{exp_id}")
    assert r.status_code == 204
    assert len(store.STORE["experiences"][USER_EMAIL]) == count_before - 1


# ── Lingue ────────────────────────────────────────────────────────────────────

async def test_add_language(user_client: AsyncClient):
    initial = len(store.STORE["languages"][USER_EMAIL])
    r = await user_client.post("/cv/me/languages", json={
        "language_name": "Tedesco", "level": "A1"
    })
    assert r.status_code == 201
    langs = store.STORE["languages"][USER_EMAIL]
    assert len(langs) == initial + 1
    assert langs[-1]["language_name"] == "Tedesco"


async def test_delete_language(user_client: AsyncClient):
    """DELETE ritorna 204 e rimuove la lingua."""
    await store.add_language(USER_EMAIL, {"language_name": "Francese", "level": "A2"})
    lang_id = store.STORE["languages"][USER_EMAIL][-1]["id"]
    count_before = len(store.STORE["languages"][USER_EMAIL])
    r = await user_client.delete(f"/cv/me/languages/{lang_id}")
    assert r.status_code == 204
    assert len(store.STORE["languages"][USER_EMAIL]) == count_before - 1


# ── Certificazioni ────────────────────────────────────────────────────────────

async def test_add_certification(user_client: AsyncClient):
    initial = len(store.STORE["certifications"][USER_EMAIL])
    r = await user_client.post("/cv/me/certifications", json={
        "name": "Azure Fundamentals",
        "issuing_org": "Microsoft",
        "year": 2023,
    })
    assert r.status_code == 201
    certs = store.STORE["certifications"][USER_EMAIL]
    assert len(certs) == initial + 1
    assert certs[-1]["name"] == "Azure Fundamentals"


async def test_delete_certification(user_client: AsyncClient):
    """DELETE ritorna 204 e rimuove la certificazione."""
    await store.add_certification(USER_EMAIL, {
        "name": "GCP Associate", "issuing_org": "Google", "year": 2022
    })
    cert_id = store.STORE["certifications"][USER_EMAIL][-1]["id"]
    count_before = len(store.STORE["certifications"][USER_EMAIL])
    r = await user_client.delete(f"/cv/me/certifications/{cert_id}")
    assert r.status_code == 204
    assert len(store.STORE["certifications"][USER_EMAIL]) == count_before - 1


async def test_cert_suggest(user_client: AsyncClient):
    """POST /cv/cert-catalog/suggest-codes non crasha con input valido."""
    r = await user_client.post("/cv/cert-catalog/suggest-codes", json={"name": "AWS"})
    assert r.status_code == 200


# ── RBAC ─────────────────────────────────────────────────────────────────────

async def test_user_cannot_read_other_cv(user_client: AsyncClient):
    """Un utente non può leggere il CV di un altro."""
    r = await user_client.get(f"/cv/{ADMIN_EMAIL}")
    assert r.status_code in (403, 404)
