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
BATCH = 20
# Combien de temps on insiste sur une erreur passagere (reseau du salon
# coupe, relais ou SMTP injoignable) avant de passer l'e-mail en echec : le
# temps qu'on voie la panne et qu'on la repare. Une erreur definitive
# (jeton refuse, message refuse) passe en echec tout de suite.
DUREE_RELANCES = timedelta(hours=4)
# Ecart maximal entre deux essais : une fois la panne reparee, l'e-mail part
# dans les dix minutes.
ECART_MAX = timedelta(minutes=10)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("outbox")


def _backoff(attempts: int) -> timedelta:
    return min(ECART_MAX, timedelta(seconds=5 * 2**attempts))


def _essais_pour(duree: timedelta) -> int:
    """Le nombre d'essais dont les ecarts couvrent `duree`.

    Compte en essais plutot qu'en heures depuis la mise en file : un e-mail
    reste en attente pendant que le worker est arrete, et il ne doit pas
    etre abandonne des son premier essai au redemarrage.
    """
    essais, ecoule = 1, timedelta(0)
    while ecoule < duree:
        ecoule += _backoff(essais)
        essais += 1
    return essais


MAX_ATTEMPTS = _essais_pour(DUREE_RELANCES)


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
    """Patiente jusqu'a ce que les tables existent, avec toutes leurs colonnes.

    C'est l'API qui les cree, a son demarrage, et qui ajoute les colonnes
    venues apres coup. Le worker part en meme temps et peut la devancer : sans
    cette attente il mourait sur « relation email_outbox does not exist » --
    ou, la table existant deja, sur « column email_outbox.images_path does not
    exist ». En conteneur, `restart: unless-stopped` le relancait jusqu'a ce
    que ca passe -- bruyamment ; lance a la main, il ne revenait jamais.

    On lit donc une ligne entiere, toutes colonnes du modele, et pas
    seulement l'identifiant.
    """
    for reste in range(essais, 0, -1):
        try:
            with SessionLocal() as db:
                db.execute(select(EmailOutbox).limit(1))
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
