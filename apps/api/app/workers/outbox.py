"""Worker d'envoi des emails.

Boucle simple avec backoff exponentiel. Tourne dans son propre conteneur pour
qu'un SMTP injoignable n'ait aucun effet sur la borne.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import EmailOutbox, OutboxStatus
from app.services.mailer import PermanentSendError, current_transport, send_now

POLL_SECONDS = 5
MAX_ATTEMPTS = 8
BATCH = 20

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("outbox")


def _backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(600, 5 * 2**attempts))


def process_batch() -> int:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        items = db.scalars(
            select(EmailOutbox)
            .where(
                EmailOutbox.status == OutboxStatus.pending,
                EmailOutbox.next_attempt_at <= now,
            )
            .order_by(EmailOutbox.next_attempt_at)
            .limit(BATCH)
            .with_for_update(skip_locked=True)
        ).all()

        for item in items:
            item.status = OutboxStatus.sending
        db.commit()

        for item in items:
            try:
                send_now(db, item)
            except PermanentSendError as exc:
                # Token revoque, cle refusee, configuration absente : sept
                # essais de plus ne changeront rien, autant le dire tout de
                # suite dans la page Emails.
                item.attempts += 1
                item.last_error = str(exc)[:2000]
                item.status = OutboxStatus.failed
                log.error("email %s abandonne : %s", item.id, exc)
            except Exception as exc:
                item.attempts += 1
                item.last_error = str(exc)[:2000]
                if item.attempts >= MAX_ATTEMPTS:
                    item.status = OutboxStatus.failed
                    log.error("email %s abandonne apres %s essais", item.id, item.attempts)
                else:
                    item.status = OutboxStatus.pending
                    item.next_attempt_at = datetime.now(UTC) + _backoff(item.attempts)
                    log.warning("email %s: %s", item.id, exc)
            else:
                item.status = OutboxStatus.sent
                item.sent_at = datetime.now(UTC)
                item.last_error = None
                log.info("email %s envoye a %s", item.id, item.to_email)

        db.commit()
        return len(items)


def recover_stale() -> None:
    """Un crash entre les deux commits laisserait des emails bloques en
    `sending` pour toujours. Au demarrage, on les remet en file."""
    with SessionLocal() as db:
        stale = db.scalars(
            select(EmailOutbox).where(EmailOutbox.status == OutboxStatus.sending)
        ).all()
        for item in stale:
            item.status = OutboxStatus.pending
        if stale:
            log.warning("%s email(s) recuperes depuis l'etat sending", len(stale))
        db.commit()


def attendre_le_schema(delai: float = 2.0, essais: int = 60) -> None:
    """Patiente jusqu'a ce que les tables existent.

    C'est l'API qui les cree, a son demarrage. Le worker part en meme temps et
    peut la devancer : sans cette attente il mourait sur « relation
    email_outbox does not exist ». En conteneur, `restart: unless-stopped` le
    relancait jusqu'a ce que ca passe -- bruyamment ; lance a la main, il ne
    revenait jamais.
    """
    for reste in range(essais, 0, -1):
        try:
            with SessionLocal() as db:
                db.execute(select(EmailOutbox.id).limit(1))
            return
        except Exception as exc:
            if reste == 1:
                raise
            log.warning("base pas prete (%s) -- nouvelle tentative dans %ss", type(exc).__name__, delai)
            time.sleep(delai)


def main() -> None:
    attendre_le_schema()
    with SessionLocal() as db:
        log.info("worker outbox demarre (transport : %s)", current_transport(db))
    recover_stale()
    while True:
        try:
            if process_batch() == 0:
                time.sleep(POLL_SECONDS)
        except Exception:
            log.exception("erreur worker")
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
