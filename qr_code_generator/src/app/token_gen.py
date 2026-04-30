import secrets
import string

from sqlalchemy.orm import Session

from .models import UrlMapping


TOKEN_ALPHABET = string.ascii_letters + string.digits
TOKEN_LENGTH = 7
MAX_RETRIES = 20


def token_exists(db: Session, token: str) -> bool:
    return db.query(UrlMapping.id).filter(UrlMapping.token == token).first() is not None


def generate_token(db: Session) -> str:
    for _ in range(MAX_RETRIES):
        token = "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))
        if not token_exists(db, token):
            return token
    raise RuntimeError("Could not allocate a unique token")
