"""API bağımlılıkları.

Şu an tek kullanıcı: varsayılan yerel kullanıcı get-or-create edilir. Çok
kullanıcılı moda geçince burası gerçek auth (JWT/OAuth) ile değiştirilecek;
veri modeli zaten user_id ile hazır.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db

DEFAULT_EMAIL = "local@fontakip"


def get_current_user(db: Session = Depends(get_db)) -> User:
    user = db.execute(select(User).where(User.email == DEFAULT_EMAIL)).scalars().first()
    if user is None:
        user = User(email=DEFAULT_EMAIL, display_name="Yerel Kullanıcı")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user
