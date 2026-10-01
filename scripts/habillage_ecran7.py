"""Le calque fixe de l'ecran 7 pour le visuel de l'e-mail : le ruban et le logo
AIXAM | easy, en 3840 x 2160 sur fond transparent.

Le ruban de la borne ecrit son texte le long d'une courbe, en Poppins : les
moteurs de rendu cote serveur (Pillow, Cairo) ne le reproduisent pas
fidelement. Ces deux elements ne dependent pas de la creation : on les
photographie donc une fois, avec Chrome, tels que la borne les dessine, et le
serveur n'a plus qu'a poser ce calque.

A relancer si le ruban de l'ecran 7 (Ribbon modele « editeur ») ou le logo
change -- le trace ci-dessous est celui que la borne produit, releve dans le
navigateur. Mac uniquement (Chrome) ; le PNG produit est versionne.

    python3 scripts/habillage_ecran7.py
"""

import subprocess
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
KIOSK = RACINE / "apps" / "kiosk" / "src"
SORTIE = RACINE / "apps" / "api" / "app" / "templates" / "ecran7" / "habillage.png"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Le SVG du ruban de l'ecran 7, tel que Ribbon.tsx le rend (scene 1920 x 1080,
# debord de 340 px), et le logo a la place que lui donne `.logo-bas-droite`.
PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: Poppins; font-weight: 600; src: url('{police}') format('woff2'); }}
html, body {{ margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: transparent; }}
.ribbon {{ position: absolute; left: -340px; top: -340px; font-family: Poppins, sans-serif; }}
.logo {{ position: absolute; left: 1449px; top: 956.5px; width: 420px; display: block; }}
</style></head><body>
<svg class="ribbon" viewBox="-340 -340 2600 1760" width="2600" height="1760">
  <defs><path id="r" d="M 428.3 -422.05 L 780.45 -22.05 C 780.45 -22.05, 932.83 151.06, 1226.13 147.07
    C 1519.43 143.08, 1575.28 50.43, 1697.25 50.43 C 1786.26 50.43, 1814.23 112.74, 1927.4 112.74 L 2280 112.74"/></defs>
  <use href="#r" fill="none" stroke="#28b7f3" stroke-width="50"/>
  <text fill="#ffffff" font-size="25" font-weight="600" dy="9.05" letter-spacing="-0.27">
    <textPath href="#r" startOffset="600.9">{texte}</textPath></text>
</svg>
<img class="logo" src="{logo}">
</body></html>"""


def main() -> None:
    page = Path(tempfile.mkdtemp()) / "habillage.html"
    page.write_text(PAGE.format(
        police=(KIOSK / "fonts" / "Poppins-SemiBold.woff2").as_uri(),
        logo=(KIOSK / "assets" / "logo-bas-droite.png").as_uri(),
        texte="Crée ta propre planche de bord * " * 6,
    ), encoding="utf-8")
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
        "--force-device-scale-factor=2", "--window-size=1920,1080", "--default-background-color=00000000",
        "--virtual-time-budget=3000", f"--screenshot={SORTIE}", page.as_uri(),
    ], check=True, capture_output=True)
    print(f"ecrit : {SORTIE}")


if __name__ == "__main__":
    main()
