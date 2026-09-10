import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

from app.config import settings

_hasher = PasswordHasher()

ALGORITHM = "HS256"


def hash_secret(raw: str) -> str:
    return _hasher.hash(raw)


def verify_secret(raw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, raw)
    except (VerifyMismatchError, VerificationError):
        return False


def create_access_token(subject: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def generate_numeric_code(length: int = 6) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


# --- Tokens de relais ---
#
# Forme : `axr_<prefixe hex>_<secret>`. Le prefixe est public et indexe : il
# retrouve la ligne en une requete, sans parcourir la table ni comparer le
# secret a chacune d'elles. Seul le hash argon2 du secret est stocke, comme
# pour un mot de passe -- le token complet n'existe qu'une fois, a l'ecran de
# creation, et une base volee ne permet pas d'envoyer.

RELAY_TOKEN_SCHEME = "axr"


def generate_relay_token() -> tuple[str, str, str]:
    """Rend (token complet, prefixe, secret). Le token n'est plus jamais reconstituable."""
    prefix = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    return f"{RELAY_TOKEN_SCHEME}_{prefix}_{secret}", prefix, secret


def token_indice(token: str) -> str:
    """Le debut d'un jeton : assez pour le reconnaitre, jamais pour s'en servir.

    Le prefixe est deja public -- le serveur le garde en clair pour retrouver
    le client, seul le secret qui suit est sensible. D'une forme inattendue on
    ne montre que quatre caracteres.
    """
    token = token.strip()
    if not token:
        return ""
    parts = split_relay_token(token)
    return f"{RELAY_TOKEN_SCHEME}_{parts[0]}" if parts else token[:4]


def split_relay_token(token: str) -> tuple[str, str] | None:
    """Rend (prefixe, secret), ou None si la forme ne colle pas."""
    parts = token.strip().split("_", 2)
    if len(parts) != 3 or parts[0] != RELAY_TOKEN_SCHEME or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]
