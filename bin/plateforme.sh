# Tout ce que Windows impose, en un seul endroit.
#
# A sourcer apres ROOT, dans chaque script de bin/ :
#     . "$ROOT/bin/plateforme.sh"
#
# Les memes scripts tournent sous macOS, sous Linux, et sous Git Bash sur la
# borne du salon. Seul ce dernier cas demande des precautions, parce que bash
# y lance des binaires Windows :
#
# 1. MSYS reecrit tout argument qui ressemble a un chemin Unix avant de le
#    passer au binaire : `-w /app` arrive au demon docker en `C:/Program
#    Files/Git/app`, et la compilation echoue des la premiere ligne. On coupe
#    la conversion pour tout le monde, et `hote` traduit a la main les seuls
#    chemins qui doivent rester des chemins Windows : ceux de la machine
#    hote, passes a `-v`.
#
# 2. Le CLI de Docker Desktop interroge le coffre d'identifiants de Windows,
#    qu'une session SSH -- une ouverture de session *reseau* -- n'a pas le
#    droit d'ouvrir : "A specified logon session does not exist". Tout
#    `docker pull` echoue alors, y compris sur des images publiques, et
#    piloter la borne a distance devient impossible. On donne donc au CLI un
#    assistant qui repond "aucun identifiant" (bin/win/), ce qui suffit pour
#    Docker Hub public. Un registre prive depuis Windows demande de definir
#    DOCKER_CONFIG soi-meme : s'il est deja pose, on n'y touche pas.
#
# Sur macOS et Linux, ce fichier ne fait que definir PLATEFORME et hote().

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) PLATEFORME=windows ;;
  Darwin)               PLATEFORME=macos ;;
  *)                    PLATEFORME=linux ;;
esac

if [ "$PLATEFORME" = "windows" ]; then
  export MSYS2_ARG_CONV_EXCL='*'
  hote() { cygpath -m "$1"; }

  if [ -z "${DOCKER_CONFIG:-}" ]; then
    mkdir -p "$ROOT/.run/docker"
    printf '{"auths":{},"credsStore":"anonyme"}\n' > "$ROOT/.run/docker/config.json"
    DOCKER_CONFIG="$(cygpath -m "$ROOT/.run/docker")"
    export DOCKER_CONFIG
    PATH="$ROOT/bin/win:$PATH"
    export PATH
  fi
else
  hote() { printf '%s' "$1"; }
fi
