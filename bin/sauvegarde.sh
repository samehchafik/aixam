#!/usr/bin/env bash
# Sauvegarde la base : visiteurs, creations, file d'emails ET reglages.
#
# Pourquoi : les reglages saisis dans le back-office -- jeton du relais,
# adresse du relais, jeton de remontee -- vivent dans la base. Recreer celle-ci
# (reinstallation, migration, `bin/stop.sh --volumes`) les efface, et l'envoi
# des emails s'arrete sans que rien ne l'annonce. Au salon, ce serait aussi les
# visiteurs de la journee.
#
#   bin/sauvegarde.sh                dans .run/sauvegardes/
#   bin/sauvegarde.sh --vers DOSSIER ailleurs (cle USB, partage)
#
# Restauration -- la base doit exister et etre vide. La creer demande le
# superutilisateur : le role « aixam » n'a pas ce droit, et c'est voulu.
#   psql -U postgres -h localhost -d postgres -c "create database aixam owner aixam"
#   psql -U aixam    -h localhost -d aixam    -f .run/sauvegardes/aixam-....sql
# Eprouve le 2026-09-21 sur une base d'essai : reglages, visiteurs, creations
# et bornes reviennent, jeton du relais compris.
#
# Ce qui n'y est PAS : les JPEG de media/renders/. Ils se refabriquent depuis
# les calques, qui sont en base (voir README, « Apres le salon »).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$ROOT/bin/plateforme.sh"

say()  { printf '\033[36m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[31merreur:\033[0m %s\n' "$*" >&2; exit 1; }

DOSSIER="$ROOT/.run/sauvegardes"
GARDEES=14
while [ $# -gt 0 ]; do
  case "$1" in
    --vers) DOSSIER="$2"; shift ;;
    --gardees) GARDEES="$2"; shift ;;
    -h|--help) sed -n '2,/^[^#]/ s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "option inconnue : $1 (voir -h)" ;;
  esac
  shift
done

[ -f "$ROOT/.env" ] || die "pas de .env : rien a sauvegarder"
# Les \r d'un .env edite dans Notepad feraient un mot de passe faux.
set -a; . <(tr -d '\r' < "$ROOT/.env"); set +a
: "${POSTGRES_USER:=aixam}" "${POSTGRES_DB:=aixam}" "${POSTGRES_HOST:=localhost}"

mkdir -p "$DOSSIER"
CIBLE="$DOSSIER/aixam-$(date +%Y%m%d-%H%M).sql"

# La base tourne-t-elle en conteneur ou sur la machine ? On ne le devine pas :
# on regarde si pg_dump est la, et sinon on passe par docker compose.
PGDUMP=""
for candidat in pg_dump "/c/Program Files/PostgreSQL/16/bin/pg_dump.exe" \
                "/c/Program Files/PostgreSQL/17/bin/pg_dump.exe"; do
  if command -v "$candidat" >/dev/null 2>&1 || [ -x "$candidat" ]; then PGDUMP="$candidat"; break; fi
done

say "sauvegarde de $POSTGRES_DB vers $(basename "$CIBLE")"
if [ -n "$PGDUMP" ]; then
  PGPASSWORD="${POSTGRES_PASSWORD:-}" "$PGDUMP" \
    -U "$POSTGRES_USER" -h "$POSTGRES_HOST" -d "$POSTGRES_DB" --no-owner --no-privileges > "$CIBLE"
elif command -v docker >/dev/null 2>&1; then
  (cd "$ROOT" && docker compose exec -T db pg_dump \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges) > "$CIBLE"
else
  die "ni pg_dump ni docker : impossible de sauvegarder"
fi

# Une sauvegarde vide est pire qu'aucune : on la refuse plutot que de la garder.
TAILLE=$(wc -c < "$CIBLE" | tr -d ' ')
[ "$TAILLE" -gt 1000 ] || { rm -f "$CIBLE"; die "sauvegarde vide ($TAILLE octets) : rien n'a ete ecrit"; }
grep -q "CREATE TABLE" "$CIBLE" || { rm -f "$CIBLE"; die "sauvegarde sans aucune table : suspecte, ecartee"; }

say "$(( TAILLE / 1024 )) Ko, $(grep -c '^INSERT\|^COPY' "$CIBLE" || true) bloc(s) de donnees"

# On garde les dernieres, pas toutes : un disque plein arrete la borne.
ls -1t "$DOSSIER"/aixam-*.sql 2>/dev/null | tail -n +$((GARDEES + 1)) | while read -r vieille; do
  rm -f "$vieille"; say "ecartee : $(basename "$vieille")"
done
say "terminee. $(ls -1 "$DOSSIER"/aixam-*.sql 2>/dev/null | wc -l | tr -d ' ') sauvegarde(s) conservee(s)."
