"""
Seed dati demo: 1 admin + utenti di test con CV placeholder.
La password viene sincronizzata a settings.default_password ad ogni avvio
per tutti gli utenti (Excel e non), in modo da avere sempre credenziali coerenti.
"""
from sqlalchemy.orm import Session
from app.models import User, CV, UserRole, AvailabilityStatus
from app.security import hash_password
from app.database import settings


def seed_data(db: Session) -> None:
    _ensure_admin(db)
    _ensure_demo_users(db)
    _sync_all_passwords(db)


def _ensure_admin(db: Session) -> None:
    if db.query(User).filter(User.email == "admin@mashfrog.com").first():
        return
    admin = User(
        email="admin@mashfrog.com",
        username="admin",
        full_name="Amministratore Sistema",
        hashed_password=hash_password(settings.default_password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin)
    db.flush()
    db.add(CV(user_id=admin.id, availability_status=AvailabilityStatus.DISPONIBILE))
    db.commit()


def _ensure_demo_users(db: Session) -> None:
    demo_users = [
        ("mario.rossi@mashfrog.com",    "mario.rossi",    "Mario Rossi"),
        ("giulia.bianchi@mashfrog.com", "giulia.bianchi", "Giulia Bianchi"),
        ("luca.verdi@mashfrog.com",     "luca.verdi",     "Luca Verdi"),
    ]
    for email, username, name in demo_users:
        if db.query(User).filter(User.email == email).first():
            continue
        u = User(
            email=email,
            username=username,
            full_name=name,
            hashed_password=hash_password(settings.default_password),
            role=UserRole.USER,
            is_active=True,
        )
        db.add(u)
        db.flush()
        db.add(CV(user_id=u.id, availability_status=AvailabilityStatus.DISPONIBILE))
    db.commit()


def _sync_all_passwords(db: Session) -> None:
    """Allinea la password di tutti gli utenti a settings.default_password."""
    new_hash = hash_password(settings.default_password)
    db.query(User).update({User.hashed_password: new_hash})
    db.commit()
