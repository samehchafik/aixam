"""Importe les elements de skin livres par le studio.

    python3 scripts/import_assets.py [dossier] [--demo]
    python3 scripts/import_assets.py --ecrans <livraison des ecrans>

Le dossier attendu est `elements_creation_skins`, tel que le studio le livre :

    Gabarit_skin.svg              silhouette exacte de la planche
    fonds_skin/fond_N.svg         le fond, 3460x690
    fonds_skin/Vignette_fond_N.svg  sa vignette 16:9 pour le panier
    objets_skin/objet_N.svg       un objet a poser

Tout est en SVG, et le reste de la chaine aussi : la borne les affiche tels
quels, le rendu serveur les rasterise a la volee. Il n'y a donc qu'une seule
version de chaque element, celle du studio.

Le script ecrit dans apps/api/media/ :
    backgrounds/index.json, objects/index.json   ordre, dimensions, libelles
    base/shape.json                              la silhouette, en points

Les libelles sont generes en « Fond 1 », « Objet 1 » : le studio n'en fournit
pas. Ils se corrigent directement dans index.json, sans toucher au code.

--ecrans prend une livraison d'ecrans (un dossier par ecran, 01_... a 08_...)
et en tire le decor du diaporama (media/mockup) et les images du front
(apps/kiosk/src/assets). Voir `importer_ecrans`.

--demo ajoute des complements FABRIQUES, pour avoir de quoi montrer en
attendant la livraison complete : des fonds F6 a F12 batis sur le meme modele
que ceux du studio, et deux variantes de teinte pour chaque objet. Ils
disparaissent au prochain import sans --demo.
"""

from __future__ import annotations

import colorsys
import io
import json
import random
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import cairosvg
from PIL import Image

RACINE = Path(__file__).resolve().parent.parent
MEDIA = RACINE / "apps" / "api" / "media"
DEFAUT = Path(
    "/Users/sameh/Downloads/BorneEasy_PourSam/Interface/elements_creation_skins"
)

LIBELLES = {
    "fond": {"fr": "Fond {n}", "en": "Background {n}", "es": "Fondo {n}"},
    "objet": {"fr": "Objet {n}", "en": "Object {n}", "es": "Objeto {n}"},
}


def dimensions(svg: Path) -> tuple[float, float]:
    """Largeur et hauteur intrinseques, lues sur la balise racine.

    Elles servent au rapport d'un objet dans la bande du panier et a sa taille
    d'apparition sur la planche : on les connait sans attendre le chargement
    de l'image.
    """
    tete = svg.read_text(encoding="utf-8")[:1200]
    vb = re.search(r'viewBox="\s*([\d.eE+-]+)[ ,]+([\d.eE+-]+)[ ,]+([\d.eE+-]+)[ ,]+([\d.eE+-]+)', tete)
    if vb:
        return float(vb.group(3)), float(vb.group(4))
    w = re.search(r'\swidth="([\d.]+)', tete)
    h = re.search(r'\sheight="([\d.]+)', tete)
    if w and h:
        return float(w.group(1)), float(h.group(1))
    raise SystemExit(f"{svg.name} : ni viewBox ni width/height")


def numero(nom: str) -> int:
    m = re.search(r"(\d+)", nom)
    return int(m.group(1)) if m else 0


# Familles generiques : elles n'ont pas a etre installees.
_GENERIQUES = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui"}
# Ce qui fait qu'un SVG dessine quelque chose sans dependre d'une police.
_DESSIN = re.compile(r"<(path|rect|circle|ellipse|polygon|polyline|line|image)\b")


def _polices_citees(svg: str) -> set[str]:
    familles = set()
    for declaration in re.findall(r"font-family\s*:\s*([^;}]+)", svg):
        for nom in declaration.split(","):
            nom = nom.strip().strip("'\"")
            if nom and nom.lower() not in _GENERIQUES:
                familles.add(nom)
    return familles


@lru_cache(maxsize=64)
def _police_installee(famille: str) -> bool | None:
    """La police est-elle reellement disponible ? None si on ne peut pas savoir.

    fontconfig repond TOUJOURS quelque chose a `fc-match` : a defaut de la
    police demandee, il propose un remplacant. C'est ce silence qui fait mal --
    le rendu ne signale rien, il substitue.
    """
    try:
        resultat = subprocess.run(
            ["fc-match", "-f", "%{family}", famille],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if resultat.returncode != 0:
        return None
    proposees = {p.strip().lower() for p in resultat.stdout.split(",")}
    return famille.strip().lower() in proposees


def verifier_polices(svg: Path) -> list[str]:
    """Les polices que ce SVG reclame et que la machine n'a pas.

    Un SVG d'Illustrator garde le TEXTE, pas ses contours : sans la police, le
    rendu substitue en silence. Quand ce texte est une ligature d'icone --
    « paper-plane » en Font Awesome -- on n'obtient pas un avion mais les onze
    lettres du mot, bien plus larges que la zone de dessin, donc tranchees a
    « pa ». C'est passe en production une fois ; on regarde desormais.
    """
    contenu = svg.read_text(encoding="utf-8", errors="replace")
    return sorted(f for f in _polices_citees(contenu) if _police_installee(f) is False)


def _que_du_texte(svg: Path) -> bool:
    """Le dessin repose-t-il entierement sur du texte ?"""
    contenu = svg.read_text(encoding="utf-8", errors="replace")
    return "<text" in contenu and not _DESSIN.search(contenu)


# Un dessin deborde toujours un peu de sa zone : anti-aliasing, epaisseur de
# trait, fond volontairement a fond perdu. Mesure sur le jeu livre, ce debord
# normal ne depasse pas 4 %. On ne recadre qu'au-dela du quart -- a ce niveau
# ce n'est plus du debord, c'est un dessin qui n'a plus rien a voir avec sa
# zone, et c'est la signature d'une police substituee.
TOLERANCE_CADRE = 0.25
# La zone d'observation, en multiples de la zone d'origine. Elle est dilatee
# tant que l'encre touche son bord : on ne sait pas d'avance de combien un
# dessin deborde.
SONDE = 12.0
SONDE_MAX = 400.0


def _vue(svg: str) -> tuple[float, float, float, float] | None:
    trouve = re.search(r'viewBox="([^"]+)"', svg)
    if not trouve:
        return None
    valeurs = [float(v) for v in re.split(r"[ ,]+", trouve.group(1).strip())]
    return tuple(valeurs) if len(valeurs) == 4 else None


def _encre(svg: str, sonde: float) -> tuple[tuple[float, float, float, float], bool] | None:
    """Boite de l'encre en unites utilisateur, et si elle sature l'observation.

    On regarde LARGE, bien au-dela de la zone declaree : c'est justement ce qui
    en sort qu'on cherche. Un `<svg>` masque ce qui deborde, donc rien de tout
    cela n'est visible tant qu'on ne dilate pas la vue.
    """
    vue = _vue(svg)
    if not vue:
        return None
    x, y, w, h = vue
    X, Y = x - w * (sonde - 1) / 2, y - h * (sonde - 1) / 2
    W, H = w * sonde, h * sonde
    essai = re.sub(r'viewBox="[^"]+"', f'viewBox="{X} {Y} {W} {H}"', svg, count=1)
    essai = re.sub(r'\swidth="[^"]+"', f' width="{W:g}"', essai, count=1)
    essai = re.sub(r'\sheight="[^"]+"', f' height="{H:g}"', essai, count=1)
    image = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=essai.encode(), output_width=1400)))
    boite = image.convert("RGBA").getchannel("A").getbbox()
    if not boite:
        return None
    k = W / image.width
    gx, gy, dx, dy = boite
    sature = gx <= 0 or gy <= 0 or dx >= image.width or dy >= image.height
    return (X + gx * k, Y + gy * k, X + dx * k, Y + dy * k), sature


def recadrer_sur_encre(chemin: Path) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Elargit la zone de dessin d'un SVG jusqu'a contenir tout son dessin.

    Un SVG masque ce qui sort de sa zone. Illustrator ecrit cette zone d'apres
    ce qu'il voit AVEC les polices du studio : que l'une manque ici, et le
    texte de remplacement -- bien plus large -- passe hors de la zone et
    disparait. C'est ce qui reduisait un avion en papier a « pa ».

    On ne touche ni au dessin ni a ses coordonnees : seule la fenetre change.
    Rien n'est supprime, tout redevient visible, et le panneau comme le rendu
    montrent la meme chose puisqu'ils lisent le meme fichier.

    Retourne (avant, apres) si le cadre a bouge, None sinon.
    """
    svg = chemin.read_text(encoding="utf-8")
    vue = _vue(svg)
    if not vue:
        return None
    x, y, w, h = vue

    sonde = SONDE
    while True:
        mesure = _encre(svg, sonde)
        if not mesure:
            return None
        (gx, gy, dx, dy), sature = mesure
        if not sature or sonde >= SONDE_MAX:
            break
        sonde *= 4

    marge_x, marge_y = w * TOLERANCE_CADRE, h * TOLERANCE_CADRE
    if gx >= x - marge_x and gy >= y - marge_y and dx <= x + w + marge_x and dy <= y + h + marge_y:
        return None

    # Une marge d'un pour cent : l'anti-aliasing depose un voile juste au bord,
    # que la mesure ne voit pas toujours.
    marge = max(dx - gx, dy - gy) * 0.01
    nx, ny = gx - marge, gy - marge
    nw, nh = (dx - gx) + 2 * marge, (dy - gy) + 2 * marge

    svg = re.sub(r'viewBox="[^"]+"', f'viewBox="{nx:.2f} {ny:.2f} {nw:.2f} {nh:.2f}"', svg, count=1)
    svg = re.sub(r'\swidth="[^"]+"', f' width="{nw:.2f}"', svg, count=1)
    svg = re.sub(r'\sheight="[^"]+"', f' height="{nh:.2f}"', svg, count=1)
    chemin.write_text(svg, encoding="utf-8")
    return (w, h), (nw, nh)


def importer(
    source: Path,
    groupe: str,
    motif: str,
    cible: str,
    vignettes: str | None = None,
    recadrer: bool = False,
) -> int:
    dossier = MEDIA / cible
    if dossier.exists():
        ancien = dossier / "index.json"
        if ancien.is_file():
            fabriques = sum(
                1 for i in json.loads(ancien.read_text(encoding="utf-8")).get("items", [])
                if i.get("demo")
            )
            if fabriques:
                print(f"  {cible} : {fabriques} element(s) fabrique(s) remplaces (--demo pour les refaire)")
        shutil.rmtree(dossier)
    dossier.mkdir(parents=True)

    fichiers = sorted(source.glob(motif), key=lambda p: numero(p.name))
    items = []
    for svg in fichiers:
        manquantes = verifier_polices(svg)
        copie = dossier / svg.name
        shutil.copy2(svg, copie)
        if manquantes:
            print(f"  attention : {svg.name} porte du texte en {', '.join(manquantes)}, absente ici")
        recadre = recadrer_sur_encre(copie) if recadrer else None
        if recadre:
            avant, apres = recadre
            print(f"             recadre : {avant[0]:.0f}x{avant[1]:.0f} -> {apres[0]:.0f}x{apres[1]:.0f}"
                  f" (le dessin debordait de sa zone, il etait coupe)")
        w, h = dimensions(copie)
        n = numero(svg.name)
        item = {
            "id": f"{groupe}-{n}",
            "file": svg.name,
            "width": round(w, 2),
            "height": round(h, 2),
            "label": {lg: tpl.format(n=n) for lg, tpl in LIBELLES[groupe].items()},
        }
        if vignettes:
            vig = source / vignettes.format(n=n)
            if vig.is_file():
                shutil.copy2(vig, dossier / vig.name)
                item["thumb"] = vig.name
            else:
                print(f"  attention : pas de vignette pour {svg.name}")
        items.append(item)

    (dossier / "index.json").write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(items):2d} {cible:12s} -> {dossier}")
    return len(items)


def importer_gabarit(gabarit: Path) -> None:
    """La silhouette de la planche, en points.

    Le gabarit est une polyligne fermee de plus de 250 points : la planche
    n'est pas un simple rectangle arrondi, ses bords ondulent legerement. On
    garde les points tels quels -- la borne les trace, le serveur en fait un
    masque. Les deux lisent donc la meme geometrie.
    """
    s = gabarit.read_text(encoding="utf-8")
    vb = re.search(r'viewBox="\s*[\d.eE+-]+[ ,]+[\d.eE+-]+[ ,]+([\d.eE+-]+)[ ,]+([\d.eE+-]+)', s)
    pts = re.search(r'<polyline[^>]*points="([^"]+)"', s)
    if not (vb and pts):
        raise SystemExit("Gabarit_skin.svg : polyline ou viewBox introuvable")
    v = pts.group(1).split()
    points = [[float(v[i]), float(v[i + 1])] for i in range(0, len(v) - 1, 2)]

    largeur, hauteur = float(vb.group(1)), float(vb.group(2))
    forme = {
        "width": largeur,
        "height": hauteur,
        "points": points,
        "notch": encoche(points, largeur, hauteur),
    }

    base = MEDIA / "base"
    base.mkdir(parents=True, exist_ok=True)
    (base / "shape.json").write_text(json.dumps(forme, indent=2), encoding="utf-8")
    n = forme["notch"]
    print(f"{len(points):3d} points   -> {base / 'shape.json'}")
    print(f"    encoche  x {n['x']:.0f} y {n['y']:.0f}  {n['width']:.0f} x {n['height']:.0f}")


def encoche(points: list[list[float]], largeur: float, hauteur: float) -> dict:
    """Le creux central du bord bas, mesure sur la silhouette.

    C'est la que se pose le panneau « Supprime / Reinitialise ». On ne le
    deduit pas de parametres -- ils n'existent plus -- mais du gabarit
    lui-meme : on rasterise la silhouette et on lit, colonne par colonne, ou
    le bord bas remonte.
    """
    from PIL import Image, ImageDraw

    L, H = 1600, max(1, round(1600 * hauteur / largeur))
    sx, sy = L / largeur, H / hauteur
    masque = Image.new("L", (L, H), 0)
    ImageDraw.Draw(masque).polygon([(x * sx, y * sy) for x, y in points], fill=255)
    px = masque.load()

    bas = []
    for x in range(L):
        col = [y for y in range(H - 1, -1, -1) if px[x, y]]
        bas.append(col[0] if col else 0)

    # Le bord bas ondule doucement d'un bout a l'autre : un simple seuil le
    # prendrait pour un creux. L'encoche, elle, est une coupe franche -- on la
    # reconnait a ses deux ruptures, l'une qui monte, l'autre qui redescend.
    seuil = H * 0.15
    montees = [x for x in range(L - 1) if bas[x + 1] - bas[x] < -seuil]
    descentes = [x for x in range(L - 1) if bas[x + 1] - bas[x] > seuil]
    if not montees or not descentes:
        return {"x": largeur / 2, "y": hauteur, "width": 0.0, "height": 0.0}

    x0, x1 = min(montees) + 1, max(descentes)
    plancher = max(bas)
    haut = min(bas[x] for x in range(x0, x1 + 1))
    return {
        "x": round(x0 / sx, 2),
        "y": round(haut / sy, 2),
        "width": round((x1 - x0) / sx, 2),
        "height": round((plancher - haut) / sy, 2),
    }


# --------------------------------------------------------------- complements
#
# Tout ce qui suit FABRIQUE des elements, il ne les importe pas. C'est un
# depannage de demonstration, pas de la matiere livree.

# Fonds F6 a F12, sur le modele du studio : un aplat, son numero en plus sombre.
FONDS_DEMO = [
    ("#b5453a", "#8d3229"), ("#1f7a7a", "#165a5a"), ("#7a5a1f", "#5a4216"),
    ("#3d5a8b", "#2c4268"), ("#6b2f6b", "#4e224e"), ("#2f6b3d", "#224e2d"),
    ("#8b3d5a", "#682c42"),
]

# Deux tiers de tour chacune : les variantes restent distinctes entre elles.
TEINTES = [(1, 120.0), (2, 240.0)]

# Lignes du panier des objets. Le melange s'en sert pour eviter qu'une meme
# forme occupe une colonne entiere.
LIGNES_PANIER = 3


def fond_demo(numero: int, fond: str, encre: str, largeur: int, hauteur: int, taille: int) -> str:
    """Un fond de demonstration, calque sur ceux du studio.

    La police est `sans-serif` et non celle du studio : elle est absente de la
    machine comme du conteneur. Un nom generique laisse chaque moteur prendre
    ce qu'il a.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{largeur}" height="{hauteur}" '
        f'viewBox="0 0 {largeur} {hauteur}">\n'
        f'  <rect fill="{fond}" width="{largeur}" height="{hauteur}"/>\n'
        f'  <text fill="{encre}" font-family="DejaVu Sans, Verdana, sans-serif" '
        f'font-size="{taille}" text-anchor="middle" '
        f'x="{largeur / 2:.0f}" y="{hauteur * 0.78:.0f}">F{numero}</text>\n'
        "</svg>\n"
    )


def tourner_teinte(couleur: str, degres: float) -> str:
    """Fait tourner la teinte d'une couleur, en laissant les gris tranquilles.

    Les noirs, blancs et gris portent les contours et les ombres d'un dessin :
    les teinter les ferait virer avec le reste et l'objet perdrait son trait.
    """
    v = couleur.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    r, g, b = (int(v[i : i + 2], 16) / 255 for i in (0, 2, 4))
    # colorsys rend (teinte, LUMINOSITE, saturation) -- dans cet ordre. Les
    # lire comme (teinte, saturation, luminosite) echangeait les deux
    # dernieres : la luminosite recevait la saturation, si bien qu'une couleur
    # franche ressortait BLANCHE, quelle que soit la teinte demandee. Les deux
    # variantes d'un meme objet devenaient alors identiques.
    teinte, luminosite, saturation = colorsys.rgb_to_hls(r, g, b)
    if saturation < 0.08:
        return couleur
    r, g, b = colorsys.hls_to_rgb((teinte + degres / 360) % 1.0, luminosite, saturation)
    return "#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in (r, g, b)))


def variante(svg: str, degres: float) -> str:
    """Le meme dessin, toutes ses couleurs tournees d'autant."""
    return re.sub(
        r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b",
        lambda m: tourner_teinte(m.group(0), degres),
        svg,
    )


def melanger(elements: list[tuple[str, dict]], fenetre: int) -> list[dict]:
    """Melange les objets, sans laisser deux fois la meme forme dans une colonne.

    Le panier remplit ses colonnes par groupes de `fenetre` elements qui se
    suivent. Range par origine, chaque colonne montrait donc une seule forme
    dans ses trois teintes -- repetitif, et on ne voyait qu'un tiers du
    catalogue d'un coup d'oeil. Un melange simple laisserait le hasard
    reformer ces paquets ; on ecarte donc ce qui vient de la meme origine.
    """
    reste = elements[:]
    random.shuffle(reste)
    ordre: list[tuple[str, dict]] = []
    while reste:
        voisins = {origine for origine, _ in ordre[-(fenetre - 1):]} if fenetre > 1 else set()
        choix = next((e for e in reste if e[0] not in voisins), reste[0])
        reste.remove(choix)
        ordre.append(choix)
    return [item for _, item in ordre]


def completer(source: Path) -> None:
    fonds = MEDIA / "backgrounds"
    index = json.loads((fonds / "index.json").read_text(encoding="utf-8"))
    depart = max(numero(i["id"]) for i in index["items"]) + 1
    for k, (fond, encre) in enumerate(FONDS_DEMO):
        n = depart + k
        grand, vignette = f"fond_{n}.svg", f"Vignette_fond_{n}.svg"
        (fonds / grand).write_text(fond_demo(n, fond, encre, 3460, 690, 520), encoding="utf-8")
        (fonds / vignette).write_text(fond_demo(n, fond, encre, 334, 187, 130), encoding="utf-8")
        index["items"].append({
            "id": f"fond-{n}", "file": grand, "width": 3460.0, "height": 690.0,
            "label": {lg: tpl.format(n=n) for lg, tpl in LIBELLES["fond"].items()},
            "thumb": vignette,
            # Marque ce qui n'a pas ete livre : ces elements partiront quand le
            # studio fournira le jeu definitif.
            "demo": True,
        })
    (fonds / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(FONDS_DEMO):2d} fonds fabriques -> F{depart} a F{depart + len(FONDS_DEMO) - 1}")

    objets = MEDIA / "objects"
    index = json.loads((objets / "index.json").read_text(encoding="utf-8"))
    # Les variantes suivent leur original : le visiteur voit la meme forme en
    # trois teintes, cote a cote dans la bande.
    enrichi: list[tuple[str, dict]] = []
    faits = 0
    for item in index["items"]:
        enrichi.append((item["id"], item))
        svg = (objets / item["file"]).read_text(encoding="utf-8")
        for suffixe, degres in TEINTES:
            nom = item["file"].replace(".svg", f"-{suffixe + 1}.svg")
            (objets / nom).write_text(variante(svg, degres), encoding="utf-8")
            enrichi.append((item["id"], {
                **item, "id": f"{item['id']}-{suffixe + 1}", "file": nom,
                "label": {lg: f"{txt} · {suffixe + 1}" for lg, txt in item["label"].items()},
                "demo": True,
            }))
            faits += 1
    index["items"] = melanger(enrichi, LIGNES_PANIER)
    (objets / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{faits:2d} variantes de teinte -> {len(index['items'])} objets, ordre melange")


NOTE = """# {titre}

Le jeu de donnees des {quoi} de la borne. Genere UNE FOIS par
`scripts/import_assets.py`, puis simplement servi : rien n'est fabrique a
l'execution, ni au demarrage de l'API ni a chaque requete.

`index.json` fait foi. Il fixe l'ordre d'affichage, les dimensions et le
libelle par langue. Le modifier suffit a changer le panier, sans toucher au
code ni redeployer : le catalogue est relu a chaque demarrage de la borne.

Un element portant `"demo": true` est FABRIQUE, pas livre. C'est un bouchon en
attendant le jeu definitif du studio.

## Remplacer par le jeu definitif

    make assets SOURCE=/chemin/vers/elements_creation_skins

Cela vide le dossier et le reconstruit a partir de ce que le studio a livre.
Les elements fabriques disparaissent alors -- c'est le but.
"""


def ecrire_note(cible: str, titre: str, quoi: str) -> None:
    (MEDIA / cible / "README.md").write_text(NOTE.format(titre=titre, quoi=quoi), encoding="utf-8")


# ---------------------------------------------------------------- le mockup
#
# Le diaporama pose les creations sur une planche de bord photographiee. Le
# studio livre trois images de meme cadre : le decor, le masque de la zone, et
# l'ombrage qui se pose par-dessus. Reste a savoir OU tombent les quatre coins
# de la planche dans cette photo -- c'est une projection a quatre points, et on
# la calcule ici plutot que de la relever a la main : le jour ou le studio
# livre une photo en haute definition, il suffit de relancer l'import.


def _silhouette(forme: dict):
    """Les points du gabarit, ramenes au carre unite."""
    return [(x / forme["width"], y / forme["height"]) for x, y in forme["points"]]


def _homographie(coins: list) -> list[float]:
    """Coefficients menant le carre unite vers quatre coins."""
    A, B = [], []
    for (u, v), (x, y) in zip([(0, 0), (1, 0), (1, 1), (0, 1)], coins):
        A.append([u, v, 1, 0, 0, 0, -u * x, -v * x]); B.append(x)
        A.append([0, 0, 0, u, v, 1, -u * y, -v * y]); B.append(y)
    for i in range(8):
        p = max(range(i, 8), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]; B[i], B[p] = B[p], B[i]
        for r in range(8):
            if r == i or A[r][i] == 0:
                continue
            q = A[r][i] / A[i][i]
            A[r] = [t - q * w for t, w in zip(A[r], A[i])]; B[r] -= q * B[i]
    return [B[i] / A[i][i] for i in range(8)]


def _projeter(coins, points):
    a, b, c, d, e, f, g, h = _homographie(coins)
    out = []
    for u, v in points:
        w = g * u + h * v + 1
        out.append(((a * u + b * v + c) / w, (d * u + e * v + f) / w))
    return out


def _droite(points) -> tuple[float, float, float]:
    """Ajuste une droite a x + b y + c = 0 sur un nuage, par moindres carres."""
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    cxx = sum((p[0] - mx) ** 2 for p in points) / n
    cyy = sum((p[1] - my) ** 2 for p in points) / n
    cxy = sum((p[0] - mx) * (p[1] - my) for p in points) / n
    tr, det = cxx + cyy, cxx * cyy - cxy * cxy
    lam = tr / 2 - max(0.0, (tr / 2) ** 2 - det) ** 0.5
    nx, ny = (cxy, lam - cxx) if abs(cxy) > 1e-9 else (1.0, 0.0)
    k = (nx * nx + ny * ny) ** 0.5
    return (nx / k, ny / k, -(nx * mx + ny * my) / k)


def _depart(masque_img, forme: dict) -> list:
    """Premiere projection, tiree des quatre droites de la planche.

    Le contour seul ne suffit pas a fixer la projection : la planche est
    presque symetrique, et plusieurs perspectives epousent la meme silhouette
    en repartissant tout autrement ce qu'il y a dedans. L'encoche, elle, est un
    reperage interne -- ses deux murs, avec les bords haut et bas, donnent
    quatre droites, et quatre droites suffisent a determiner une projection.
    """
    W, H = masque_img.size
    a = masque_img.load()
    plein = lambda x, y: 0 <= x < W and 0 <= y < H and a[x, y] > 127

    haut, bas = {}, {}
    for x in range(W):
        ys = [y for y in range(H) if plein(x, y)]
        if ys:
            haut[x], bas[x] = ys[0], ys[-1]

    # Bande principale : le plus long morceau contigu (le reste est occulte).
    cols = sorted(haut)
    morceaux, debut = [], cols[0]
    for i in range(1, len(cols)):
        if cols[i] != cols[i - 1] + 1:
            morceaux.append((debut, cols[i - 1]))
            debut = cols[i]
    morceaux.append((debut, cols[-1]))
    g, d = max(morceaux, key=lambda m: m[1] - m[0])

    # Murs de l'encoche : les deux ruptures franches du bord bas.
    sauts = sorted(((abs(bas[x + 1] - bas[x]), x) for x in range(g, d) if x + 1 in bas),
                   reverse=True)[:2]
    murs = sorted(x for _, x in sauts)
    if len(murs) < 2:
        raise SystemExit("encoche introuvable dans le masque")

    def mur(xa):
        pts = []
        for y in range(H):
            for x in range(xa - 25, xa + 26):
                if plein(x, y) != plein(x + 1, y):
                    pts.append((x + 0.5, y))
                    break
        return pts

    marge = max(10, (d - g) // 24)
    dst = [
        _droite([(x, haut[x]) for x in range(g + marge, d - marge) if x in haut]),
        _droite([(x, bas[x]) for x in range(g + marge, d - marge)
                 if x in bas and not murs[0] - 6 <= x <= murs[1] + 6]),
        _droite(mur(murs[0])),
        _droite(mur(murs[1])),
    ]

    # Repere centre sur la planche : aucune de ces droites ne passe alors par
    # l'origine, ou le systeme degenererait.
    LW, LH, n = forme["width"], forme["height"], forme["notch"]
    cx, cy = LW / 2, LH / 2
    src = [(0, 1, cy), (0, 1, -cy), (1, 0, cx - n["x"]), (1, 0, cx - (n["x"] + n["width"]))]

    A, B = [], []
    for (u, v, w), (x, y, z) in zip(src, dst):
        u, v, x, y = u / w, v / w, x / z, y / z
        A.append([u, v, 1, 0, 0, 0, -u * x, -v * x]); B.append(x)
        A.append([0, 0, 0, u, v, 1, -u * y, -v * y]); B.append(y)
    for i in range(8):
        p = max(range(i, 8), key=lambda r: abs(A[r][i]))
        A[i], A[p] = A[p], A[i]; B[i], B[p] = B[p], B[i]
        for r in range(8):
            if r == i or A[r][i] == 0:
                continue
            q = A[r][i] / A[i][i]
            A[r] = [t - q * w for t, w in zip(A[r], A[i])]; B[r] -= q * B[i]
    c = [B[i] / A[i][i] for i in range(8)]
    # Les droites se transforment par l'inverse transposee : on revient donc
    # aux points en inversant puis transposant.
    Hd = [[c[0], c[1], c[2]], [c[3], c[4], c[5]], [c[6], c[7], 1.0]]
    t = [[Hd[j][i] for j in range(3)] for i in range(3)]
    (a1, b1, c1), (d1, e1, f1), (g1, h1, i1) = t
    det = a1 * (e1 * i1 - f1 * h1) - b1 * (d1 * i1 - f1 * g1) + c1 * (d1 * h1 - e1 * g1)
    inv = [[(e1 * i1 - f1 * h1) / det, -(b1 * i1 - c1 * h1) / det, (b1 * f1 - c1 * e1) / det],
           [-(d1 * i1 - f1 * g1) / det, (a1 * i1 - c1 * g1) / det, -(a1 * f1 - c1 * d1) / det],
           [(d1 * h1 - e1 * g1) / det, -(a1 * h1 - b1 * g1) / det, (a1 * e1 - b1 * d1) / det]]

    def proj(x, y):
        w = inv[2][0] * x + inv[2][1] * y + inv[2][2]
        return [(inv[0][0] * x + inv[0][1] * y + inv[0][2]) / w,
                (inv[1][0] * x + inv[1][1] * y + inv[1][2]) / w]

    return [proj(-cx, -cy), proj(cx, -cy), proj(cx, cy), proj(-cx, cy)]


def coins_planche(masque_img, forme: dict) -> tuple[list, float]:
    """Les quatre coins de la planche dans la photo.

    On part de la projection tiree des droites, puis on l'affine par petits
    pas : le contour du gabarit est arrondi et l'ajustement des droites porte
    sur quelques pixels d'erreur, que ce reglage final rattrape.
    """
    from PIL import Image, ImageDraw

    W, H = masque_img.size
    mk = masque_img.load()
    pts = _silhouette(forme)
    dedans = [(x, y) for y in range(0, H, 2) for x in range(0, W, 2) if mk[x, y] > 127]
    dehors = [(x, y) for y in range(0, H, 2) for x in range(0, W, 2) if mk[x, y] <= 127]

    def note(coins):
        im = Image.new("L", (W, H), 0)
        ImageDraw.Draw(im).polygon(_projeter(coins, pts), fill=255)
        r = im.load()
        couvre = sum(1 for x, y in dedans if r[x, y]) / max(1, len(dedans))
        deborde = sum(1 for x, y in dehors if r[x, y]) / max(1, len(dehors))
        return couvre - 0.25 * deborde, couvre

    coins = _depart(masque_img, forme)
    meilleure = note(coins)[0]
    pas = max(W, H) / 40
    while pas > 0.3:
        bouge = False
        for i in range(4):
            for axe in (0, 1):
                for signe in (1, -1):
                    essai = [list(c) for c in coins]
                    essai[i][axe] += signe * pas
                    v = note(essai)[0]
                    if v > meilleure + 1e-5:
                        coins, meilleure, bouge = essai, v, True
        if not bouge:
            pas /= 2
    return coins, note(coins)[1]


# ------------------------------------------------------ les ecrans du studio
#
# Le studio livre chaque ecran dans son dossier, en 3840x2160 (plus un pixel de
# trop sur chaque bord). On en tire deux choses :
#
#   le decor du diaporama     apps/api/media/mockup/   (partage par le grand
#                             ecran et les ecrans 1 et 7 du tactile)
#   les images des ecrans     apps/kiosk/src/assets/   (embarquees dans le front)
#
# Les photos et les degrades partent en AVIF 10 bits 4:4:4 : le ciel violet
# des photos et le degrade de l'ecran 8 y restent aussi lisses qu'en PNG, pour
# une fraction du poids (11,8 Mo -> 0,6 Mo pour la photo, 1,4 Mo -> 32 Ko pour
# un degrade). Un JPEG ou un WebP de meme poids y laissent des bandes. Ce qui a
# des aplats nets et de la transparence (logos, bandeau de marque) reste en
# PNG, et les pictos restent en SVG.

KIOSK_ASSETS = RACINE / "apps" / "kiosk" / "src" / "assets"
ECRAN = (3840, 2160)
# Le decor est mis a l'echelle de la scene (1920x1080) : les coordonnees que
# lit la borne sont en pixels de scene, pas en pixels d'image.
SCENE = (1920, 1080)

# Image du front <- fichier de la livraison. Les .avif sont convertis, le reste
# est copie tel quel (recadre au besoin).
ECRANS_KIOSK = {
    "fond-borne.avif": "04_05_06_creationduskin/Fond_borne.png",
    "fond-formulaire.avif": "02_formulaire/fond_02a_formulaire.png",
    "fond-merci.avif": "08_skin_valid/fond_08_skin_valid.png",
    "bandeau-marque.png": "01_slideshow_Et_ecran1/fond_bis/logo.png",
    "logo-bas-droite.png": "07_validation_ou_modification/fond_bis_avec_fond01/logo_enbasdroite.png",
    "logo-easy.svg": "01_slideshow_Et_ecran1/Bouton_LogoEasy.svg",
    "fermer.svg": "02_formulaire/fermeture_popin.svg",
}


def vers_avif(source: Path, sortie: Path, qualite: int = 70) -> None:
    """Convertit une image du studio en AVIF 10 bits 4:4:4, recadree en 16/9.

    Le 10 bits est ce qui garde les degrades sans bandes ; le 4:4:4 garde net
    le bord des lettres « PIMP TON SKIN » peintes dans les fonds. `avifenc`
    (brew install libavif) et non Pillow : Pillow n'ecrit que du 8 bits.
    """
    from PIL import Image

    image = Image.open(source)
    if image.size[0] >= ECRAN[0] and image.size[1] >= ECRAN[1]:
        image = image.crop((0, 0, *ECRAN))
    tampon = sortie.with_suffix(".tmp.png")
    image.save(tampon)
    try:
        subprocess.run(
            ["avifenc", "-q", str(qualite), "-d", "10", "-y", "444", "-s", "4", str(tampon), str(sortie)],
            check=True, capture_output=True,
        )
    finally:
        tampon.unlink(missing_ok=True)


def _premier_point(svg: str) -> tuple[float, float]:
    """Le point de depart du premier trace : il sert de repere commun."""
    m = re.search(r'\sd="M\s*([\d.+-]+)[ ,]+([\d.+-]+)', svg)
    if not m:
        raise SystemExit("masque : aucun trace")
    return float(m.group(1)), float(m.group(2))


def coins_sur_pose(dossier: Path, forme: dict) -> list | None:
    """Les coins de la planche, lus sur l'ecran ou le studio a pose un skin.

    La livraison contient l'ecran compose (`01_slideshow.png`) et le skin qui
    y est pose (`skin_pour_test.svg`). Des points apparies entre les deux
    donnent la projection exacte que le studio a appliquee -- la ou le masque
    seul laisse flotter les coins de droite, hors du cadre photo.

    Rend None si ces deux fichiers manquent, ou si OpenCV n'est pas installe.
    """
    compose, skin_svg = dossier / "01_slideshow.png", dossier / "skin_pour_test.svg"
    if not (compose.is_file() and skin_svg.is_file()):
        return None
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    import cairosvg
    from PIL import Image

    L, H = int(forme["width"]), int(forme["height"])
    skin = Image.open(io.BytesIO(cairosvg.svg2png(url=str(skin_svg), output_width=L, output_height=H)))
    gris = lambda im: cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2GRAY)
    a, b = gris(skin), gris(Image.open(compose).crop((0, 0, *ECRAN)))

    sift = cv2.SIFT_create(nfeatures=20000)
    ka, da = sift.detectAndCompute(a, None)
    kb, db = sift.detectAndCompute(b, None)
    paires = [m for m, n in cv2.BFMatcher().knnMatch(da, db, k=2) if m.distance < 0.75 * n.distance]
    if len(paires) < 12:
        return None
    pa = np.float32([ka[m.queryIdx].pt for m in paires])
    pb = np.float32([kb[m.trainIdx].pt for m in paires])
    projection, retenus = cv2.findHomography(pa, pb, cv2.RANSAC, 3.0)
    if projection is None or int(retenus.sum()) < 12:
        return None
    coins = cv2.perspectiveTransform(np.float32([[[0, 0], [L, 0], [L, H], [0, H]]]), projection)[0]
    return [(float(x), float(y)) for x, y in coins]


def importer_mockup(dossier: Path) -> None:
    """Le decor du diaporama : la photo, le masque de la planche, l'ombrage.

    Le studio livre le masque deux fois : recadre sur la planche, et place dans
    le cadre complet. Le premier est celui qu'on sert (plus petit) ; le second
    dit ou le poser -- l'ecart entre leurs premiers points.
    """
    import cairosvg
    from PIL import Image

    fichiers = {
        "decor": dossier / "fond_bis" / "fondbis.png",
        "masque": dossier / "masque_skin.svg",
        "placement": dossier / "masque_skin_placement.svg",
        "ombrage": dossier / "effet_sur_skin.png",
    }
    absents = [f.name for f in fichiers.values() if not f.is_file()]
    if absents:
        raise SystemExit(f"{dossier} : il manque {', '.join(absents)}")

    cible = MEDIA / "mockup"
    if cible.exists():
        shutil.rmtree(cible)
    cible.mkdir(parents=True)

    vers_avif(fichiers["decor"], cible / "decor.avif")
    vers_avif(fichiers["ombrage"], cible / "ombrage.avif", qualite=75)
    masque_svg = fichiers["masque"].read_text(encoding="utf-8")
    (cible / "masque.svg").write_text(masque_svg, encoding="utf-8")

    (px, py), (mx, my) = _premier_point(fichiers["placement"].read_text(encoding="utf-8")), _premier_point(masque_svg)
    origine = (px - mx, py - my)
    largeur, hauteur = dimensions(fichiers["masque"])

    forme = json.loads((MEDIA / "base" / "shape.json").read_text(encoding="utf-8"))
    coins = coins_sur_pose(dossier, forme)
    if coins:
        print("   planche calee sur la pose du skin de test du studio")
    else:
        # Repli : la silhouette seule. Elle cale bien la gauche, mais la
        # planche sort du cadre a droite, et les deux coins de ce cote y sont
        # mal tenus.
        masque = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=masque_svg.encode()))).getchannel("A")
        coins, couverture = coins_planche(masque, forme)
        coins = [(x + origine[0], y + origine[1]) for x, y in coins]
        print(f"   planche calee sur le masque (couvert a {couverture * 100:.1f} %)")

    echelle = SCENE[0] / ECRAN[0]
    a_la_scene = lambda x, y: [round(x * echelle, 2), round(y * echelle, 2)]
    (cible / "index.json").write_text(json.dumps({
        "width": SCENE[0], "height": SCENE[1],
        "decor": "decor.avif", "masque": "masque.svg", "ombrage": "ombrage.avif",
        "maskOrigin": a_la_scene(*origine),
        "maskSize": a_la_scene(largeur, hauteur),
        "corners": [a_la_scene(x, y) for x, y in coins],
    }, indent=2), encoding="utf-8")
    print(f"   mockup -> {cible}")


def importer_ecrans(livraison: Path) -> None:
    """Toute une livraison d'ecrans : le decor du diaporama, puis les images du front."""
    importer_mockup(livraison / "01_slideshow_Et_ecran1")
    from PIL import Image

    for nom, relatif in ECRANS_KIOSK.items():
        source, sortie = livraison / relatif, KIOSK_ASSETS / nom
        if not source.is_file():
            raise SystemExit(f"livraison incomplete : {relatif}")
        if sortie.suffix == ".avif":
            vers_avif(source, sortie)
        elif sortie.suffix == ".png":
            # Les PNG livres debordent d'un pixel et portent des marges
            # transparentes : on garde l'emprise utile, bornee au cadre.
            image = Image.open(source)
            boite = image.getchannel("A").getbbox() if image.mode == "RGBA" else None
            if boite:
                boite = (boite[0], boite[1], min(boite[2], ECRAN[0]), min(boite[3], ECRAN[1]))
                image = image.crop(boite)
            image.save(sortie, optimize=True)
        else:
            shutil.copy2(source, sortie)
        print(f"   {nom:22s} {sortie.stat().st_size // 1024:5d} Ko")


def main() -> None:
    if "--ecrans" in sys.argv:
        i = sys.argv.index("--ecrans")
        if i + 1 >= len(sys.argv):
            raise SystemExit("--ecrans <dossier de la livraison du studio>")
        importer_ecrans(Path(sys.argv[i + 1]))
        return

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    demo = "--demo" in sys.argv
    source = Path(args[0]) if args else DEFAUT
    if not source.is_dir():
        raise SystemExit(f"dossier introuvable : {source}")

    importer_gabarit(source / "Gabarit_skin.svg")
    importer(source / "fonds_skin", "fond", "fond_*.svg", "backgrounds", "Vignette_fond_{n}.svg")
    # Les objets seuls sont recadres. Un fond, lui, est dessine AUX
    # proportions de la planche : elargir sa fenetre le deformerait, alors que
    # ce qui deborde chez lui est un fond perdu voulu, que le rendu recouvre
    # deja en « cover ».
    importer(source / "objets_skin", "objet", "objet_*.svg", "objects", recadrer=True)
    if demo:
        completer(source)
    ecrire_note("backgrounds", "Fonds de skin", "fonds")
    ecrire_note("objects", "Objets de skin", "objets")

    # On ne touche PAS a media/renders. Ce script refait le catalogue ; les
    # creations des visiteurs ne lui appartiennent pas.
    #
    # Il effacait les rendus, du temps ou une creation se refabriquait depuis
    # ses calques -- un rendu perime n'etait alors qu'un cache. Ce n'est plus
    # vrai : les calques ont disparu, l'image est la seule forme durable du
    # travail d'un visiteur. Reimporter le catalogue detruirait le salon.
    creations = MEDIA / "renders"
    if creations.is_dir():
        nb = len(list(creations.glob("*.png"))) + len(list(creations.glob("*.jpg")))
        if nb:
            print(f"creations intactes : {nb}")


if __name__ == "__main__":
    main()
