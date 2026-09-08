from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # La base se decrit par ses morceaux, les memes que consomme l'image
    # postgres. Seul l'hote change entre les deux montages : `db`, le service
    # du compose, ou `host.docker.internal` pour un PostgreSQL installe sur la
    # machine. Pas d'URL a reecrire, donc pas d'identifiants en double.
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "aixam"
    postgres_password: str = "aixam"
    postgres_db: str = "aixam"

    # Echappatoire : un PostgreSQL distant, une socket, des options de SSL...
    # Renseignee, elle l'emporte sur les cinq variables ci-dessus.
    database_url: str = ""

    secret_key: str = "dev-secret-change-me"
    access_token_ttl_minutes: int = 60 * 12

    admin_email: str = "admin@aixam.local"
    admin_password: str = "admin"

    kiosk_basic_user: str = ""
    kiosk_basic_password: str = ""
    default_kiosk_token: str = "dev-kiosk-token"

    # Comment part un email. `smtp` : boite OVH ou relais Brevo. `brevo` :
    # API HTTP v3, utile quand le reseau du salon bloque le port 587 mais
    # laisse passer le 443. `relay` : on ne sort pas d'ici, on confie l'envoi
    # a un autre back-office AIXAM (voir app/api/relay.py).
    mail_transport: str = "smtp"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    # OVH ecoute en SSL direct sur le 465 et en STARTTLS sur le 587. Laisse
    # vide, on deduit du port -- une case de moins a se tromper dans le .env.
    smtp_ssl: bool = False
    mail_from: str = "noreply@aixam.com"
    mail_from_name: str = "AIXAM"

    brevo_api_key: str = ""
    brevo_api_url: str = "https://api.brevo.com/v3/smtp/email"

    # --- Relais : cote client (le back-office local du stand) ---
    mail_relay_url: str = ""
    mail_relay_token: str = ""
    mail_relay_timeout_seconds: int = 30
    # Un relais en clair sur un reseau de salon expose le token a quiconque
    # ecoute. On refuse http://, sauf localhost et sauf levee explicite.
    mail_relay_allow_insecure: bool = False

    # --- Relais : cote serveur (le back-office distant qui expedie) ---
    # Ouvre /api/relay/*. Ferme par defaut : un back-office n'accepte de
    # poster pour autrui que si on le lui a demande.
    relay_server_enabled: bool = False
    relay_default_daily_quota: int = 2000
    relay_rate_limit_per_minute: int = 120
    relay_max_body_bytes: int = 512 * 1024
    relay_max_attachment_bytes: int = 8 * 1024 * 1024

    allow_verification_bypass: bool = False

    public_base_url: str = "http://localhost:8080"
    cors_origins: str = ""

    media_dir: str = "media"
    static_dir: str = "static"

    # Duree de vie du code de verification et garde-fous anti-abus.
    verification_code_ttl_seconds: int = 15 * 60
    verification_max_attempts: int = 5

    @property
    def sqlalchemy_url(self) -> URL | str:
        """L'adresse de la base, assemblee sans jamais coller de chaines.

        `URL.create` echappe ce qu'il faut : un mot de passe contenant / @ :
        ou ? passe sans encodage manuel, la ou une URL ecrite a la main serait
        coupee au mauvais endroit.
        """
        if self.database_url:
            return self.database_url
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def smtp_use_ssl(self) -> bool:
        return self.smtp_ssl or self.smtp_port == 465

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
