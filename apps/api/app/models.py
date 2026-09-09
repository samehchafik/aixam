"""Modele de donnees.

Note RGPD : toutes les donnees nominatives vivent sur `Visitor`. Une purge se
fait en supprimant les lignes `Visitor` -- le reste (creations, evenements)
est conserve anonymise via `ON DELETE SET NULL`.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Kiosk(Base):
    """Une borne physique. Le token est presente par le front a chaque appel."""

    __tablename__ = "kiosks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Visitor(Base):
    __tablename__ = "visitors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120))
    # Unique : l'email identifie la personne. `register` reprend deja la ligne
    # existante, mais la contrainte est ce qui garantit qu'aucun chemin -- bug
    # futur, import, deux bornes qui inscrivent la meme adresse en meme temps
    # -- ne puisse recreer un doublon.
    #
    # Sur une base existante, `create_all` ne l'ajoute pas : il ne sait creer
    # que des tables. Passer par `python -m app.tools.dedupe_visitors`.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    postal_code: Mapped[str] = mapped_column(String(16))

    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    designs: Mapped[list["Design"]] = relationship(back_populates="visitor")

    __table_args__ = (Index("ix_visitors_email_created", "email", "created_at"),)


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    visitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visitors.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DesignStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    rendered = "rendered"
    failed = "failed"


class Design(Base):
    """Creation d'un visiteur.

    `layers` est la source de verite (schema maison, coordonnees normalisees
    0..1). Le JPEG envoye par mail est re-rendu cote serveur a partir de ce
    JSON : qualite constante quel que soit l'ecran, et re-render possible
    apres le salon pour la production reelle du skin.
    """

    __tablename__ = "designs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("visitors.id", ondelete="SET NULL"), index=True
    )
    kiosk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("kiosks.id", ondelete="SET NULL"), index=True
    )
    session_id: Mapped[str] = mapped_column(String(64), index=True)

    layers: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[DesignStatus] = mapped_column(
        Enum(DesignStatus, name="design_status"), default=DesignStatus.draft
    )
    render_path: Mapped[str | None] = mapped_column(String(512))
    shared_hint: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    visitor: Mapped[Visitor | None] = relationship(back_populates="designs")


class Event(Base):
    """Journal d'usage de la borne : c'est ce qui alimente les stats de l'admin."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kiosk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("kiosks.id", ondelete="SET NULL"), index=True
    )
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("visitors.id", ondelete="SET NULL"), index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class OutboxStatus(str, enum.Enum):
    pending = "pending"
    sending = "sending"
    sent = "sent"
    failed = "failed"


class EmailOutbox(Base):
    """File d'attente des emails.

    Le salon n'a pas forcement de reseau fiable : rien n'est envoye en direct
    depuis une requete HTTP, tout passe par cette table et le worker.
    """

    __tablename__ = "email_outbox"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    to_email: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body_html: Mapped[str] = mapped_column(Text)
    attachment_path: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, name="outbox_status"), default=OutboxStatus.pending, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSetting(Base):
    """Reglages modifiables a chaud depuis l'admin (bypass verif, textes...)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RelayClient(Base):
    """Un back-office autorise a faire expedier ses emails par celui-ci.

    Le token presente ressemble a `axr_<prefixe>_<secret>` : le prefixe est
    public et indexe (il retrouve la ligne en une requete), le secret n'est
    jamais stocke -- seul son hash argon2 l'est, comme un mot de passe. Un
    vol de la base ne donne donc pas le droit d'envoyer, et le token complet
    n'est affiche qu'une fois, a la creation.

    Les compteurs sont ce qui empeche la plateforme de devenir un relais de
    spam ouvert : au-dela de `daily_quota` envois dans la journee, le client
    est refuse jusqu'au lendemain, et `is_active` le coupe immediatement.
    """

    __tablename__ = "relay_clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    token_prefix: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    daily_quota: Mapped[int] = mapped_column(Integer, default=2000)
    quota_day: Mapped[date | None] = mapped_column(Date)
    sent_today: Mapped[int] = mapped_column(Integer, default=0)
    sent_total: Mapped[int] = mapped_column(Integer, default=0)

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RelayMessage(Base):
    """Trace des messages deja acceptes, pour l'idempotence.

    Le worker du back-office local retente avec backoff : sans cette table,
    une reponse perdue apres un envoi reussi ferait partir le meme email deux
    ou trois fois. Le client envoie l'identifiant de SA ligne d'outbox, la
    contrainte d'unicite fait le reste et on lui rend l'envoi deja enregistre.
    """

    __tablename__ = "relay_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("relay_clients.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str] = mapped_column(String(64))
    outbox_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("email_outbox.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("client_id", "message_id", name="uq_relay_message"),)
