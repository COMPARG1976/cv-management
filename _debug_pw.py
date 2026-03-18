from app.database import SessionLocal, settings
from app.models import User
from app.security import verify_password, hash_password

db = SessionLocal()
u = db.query(User).filter(User.username == 'antonio.minervini').first()
print('hash:', u.hashed_password[:60])
print('default_password:', repr(settings.default_password))

pw = settings.default_password
print('verify with settings.default_password:', verify_password(pw, u.hashed_password))

# Genera nuovo hash e verifica
h2 = hash_password(pw)
print('new hash:', h2[:60])
print('verify new hash:', verify_password(pw, h2))

# Aggiorna tutti manualmente
count = 0
for user in db.query(User).all():
    user.hashed_password = hash_password(pw)
    count += 1
db.commit()
print(f'Updated {count} users')

# Verifica post-update
db.refresh(u)
print('post-update verify:', verify_password(pw, u.hashed_password))
db.close()
