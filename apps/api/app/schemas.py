from __future__ import annotations

import uuid
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.models import Moderation


# --- Admin ---
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Borne / visiteur ---
class RegisterIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    postal_code: str = Field(min_length=2, max_length=16)
    consent_marketing: bool = False
    session_id: str = Field(min_length=4, max_length=64)


class RegisterOut(BaseModel):
    visitor_id: uuid.UUID
    verification_required: bool


class VerifyIn(BaseModel):
    visitor_id: uuid.UUID
    code: str = Field(min_length=4, max_length=8)


class VerifyOut(BaseModel):
    verified: bool
    remaining_attempts: int


# --- Creations ---
class Layer(BaseModel):
    """Un calque : fond (image ou couleur unie) ou objet pose sur la planche."""

    type: Literal["background", "object"]
    assetId: str | None = None
    hex: str | None = None
    x: float = 0.5
    y: float = 0.5
    # None a un sens : un fond que le visiteur n'a pas manipule n'a pas
    # d'echelle, et couvre alors toute la planche. Un defaut numerique ici
    # detruisait cette information -- le fond etait rendu comme un objet, a
    # 20 % de la largeur. Le front applique la meme regle (`effectiveScale`).
    scale: float | None = None
    rotation: float = 0.0
    opacity: float = 1.0
    z: int = 0


class DesignIn(BaseModel):
    session_id: str
    visitor_id: uuid.UUID | None = None
    layers: list[Layer] = []


class DesignOut(BaseModel):
    id: uuid.UUID
    status: str
    render_url: str | None = None


class EventIn(BaseModel):
    name: str = Field(max_length=80)
    session_id: str | None = None
    visitor_id: uuid.UUID | None = None
    payload: dict = {}


# --- Admin dashboard ---
class StatsOut(BaseModel):
    visitors_total: int
    visitors_verified: int
    designs_total: int
    designs_rendered: int
    emails_pending: int
    emails_failed: int


class VisitorRow(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    postal_code: str
    email_verified_at: datetime | None
    consent_marketing: bool
    created_at: datetime
    designs_count: int


# --- Relais de mailing ---
class RelayAttachmentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_type: str = Field(default="application/octet-stream", max_length=120)
    content_b64: str


class RelaySendIn(BaseModel):
    """Un email confie par un autre back-office.

    Un seul destinataire, et pas de champ expediteur : c'est le serveur qui
    impose son `MAIL_FROM`. Un client compromis ne peut donc ni faire du
    publipostage, ni ecrire au nom de quelqu'un d'autre.
    """

    message_id: str = Field(min_length=1, max_length=64)
    to: EmailStr
    subject: str = Field(min_length=1, max_length=255)
    body_html: str = Field(min_length=1)
    attachment: RelayAttachmentIn | None = None


class RelaySendOut(BaseModel):
    accepted: bool
    outbox_id: uuid.UUID
    duplicate: bool = False
    remaining_today: int


class RelayClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # None : on prend RELAY_DEFAULT_DAILY_QUOTA plutot qu'un nombre en dur ici.
    daily_quota: int | None = Field(default=None, ge=1, le=100_000)


class RelayClientPatch(BaseModel):
    is_active: bool | None = None
    daily_quota: int | None = Field(default=None, ge=1, le=100_000)


class MailConfigIn(BaseModel):
    """Le token n'est jamais relu par l'admin, seulement remplace.

    `None` veut dire « ne touche pas », chaine vide « efface » : sans cette
    distinction, recharger la page d'un formulaire qui n'affiche pas le token
    l'effacerait a la premiere sauvegarde.
    """

    transport: Literal["smtp", "brevo", "relay"] | None = None
    relay_url: str | None = None
    relay_token: str | None = None


class MailTestIn(BaseModel):
    to: EmailStr


# --- Remontee des donnees du stand vers le serveur ---
#
# Les identifiants voyagent : `visitors` et `designs` ont des cles UUID, donc
# une ligne garde le meme identifiant des deux cotes et se reinsere-ou-se-met-
# a-jour sans remapping. C'est ce qui rend un renvoi inoffensif.
#
# Ce qui ne voyage pas : `render_path` (un chemin local) et `kiosk_id` (la
# borne n'existe pas sur le serveur). Le JPEG non plus -- `layers` est la
# source de verite, le serveur sait re-rendre.


class SyncVisitorIn(BaseModel):
    id: uuid.UUID
    first_name: str = Field(max_length=120)
    last_name: str = Field(max_length=120)
    email: EmailStr
    postal_code: str = Field(max_length=16)
    email_verified_at: datetime | None = None
    consent_marketing: bool = False
    consent_at: datetime | None = None
    created_at: datetime


class SyncDesignIn(BaseModel):
    id: uuid.UUID
    visitor_id: uuid.UUID | None = None
    session_id: str = Field(max_length=64)
    layers: dict | list = {}
    status: str = Field(max_length=20)
    shared_hint: bool = False
    created_at: datetime
    updated_at: datetime


class SyncEventIn(BaseModel):
    """Cle entiere auto-incrementee cote base : les identifiants se
    telescoperaient entre instances. On ne les transmet donc pas, et le
    dedoublonnage se fait sur (session_id, name, created_at)."""

    session_id: str | None = Field(default=None, max_length=64)
    visitor_id: uuid.UUID | None = None
    name: str = Field(max_length=80)
    payload: dict = {}
    created_at: datetime


class SyncPushIn(BaseModel):
    visitors: list[SyncVisitorIn] = []
    designs: list[SyncDesignIn] = []
    events: list[SyncEventIn] = []


class SyncPushOut(BaseModel):
    visitors: int = 0
    designs: int = 0
    events: int = 0
    events_ignores: int = 0


class SyncConfigIn(BaseModel):
    """Comme pour le relais : `None` veut dire « ne touche pas », chaine vide
    « efface ». Le jeton n'etant jamais relu, l'absence ne doit pas l'effacer."""

    url: str | None = None
    token: str | None = None


class ModerationIn(BaseModel):
    """Verdict de l'animateur. `pending` sert a remettre en attente."""

    decision: Moderation
