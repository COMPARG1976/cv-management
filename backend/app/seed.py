"""
Seed dati demo: 1 admin + utenti di test con CV placeholder.
"""
from sqlalchemy.orm import Session
from app.models import User, CV, UserRole, AvailabilityStatus
from app.security import hash_password
from app.database import settings


def seed_data(db: Session) -> None:
    # Admin
    if not db.query(User).filter(User.email == "admin@mashfrog.com").first():
        admin = User(
            email="admin@mashfrog.com",
            full_name="Amministratore Sistema",
            hashed_password=hash_password(settings.admin_user_password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.flush()
        # CV vuoto per admin
        db.add(CV(user_id=admin.id, availability_status=AvailabilityStatus.DISPONIBILE))

    # Utenti demo
    demo_users = [
        ("mario.rossi@mashfrog.com", "Mario Rossi"),
        ("giulia.bianchi@mashfrog.com", "Giulia Bianchi"),
        ("luca.verdi@mashfrog.com", "Luca Verdi"),
    ]
    for email, name in demo_users:
        if not db.query(User).filter(User.email == email).first():
            u = User(
                email=email,
                full_name=name,
                hashed_password=hash_password(settings.default_user_password),
                role=UserRole.USER,
                is_active=True,
            )
            db.add(u)
            db.flush()
            db.add(CV(user_id=u.id, availability_status=AvailabilityStatus.DISPONIBILE))

    db.commit()
