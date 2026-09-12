"""Importe les elements de skin livres par le studio.

    python3 scripts/import_assets.py [dossier] [--demo]

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

--demo ajoute des complements FABRIQUES, pour avoir de quoi montrer en
attendant la livraison complete : des fonds F6 a F12 batis sur le meme modele
que ceux du studio, et deux variantes de teinte pour chaque objet. Ils
disparaissent au prochain import sans --demo.
"""

from __future__ import annotations

import colorsys
import json
import re
import shutil
import sys
from pathlib import Path

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


def importer(source: Path, groupe: str, motif: str, cible: str, vignettes: str | None = None) -> int:
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
        shutil.copy2(svg, dossier / svg.name)
        w, h = dimensions(svg)
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
    h, s_, l = colorsys.rgb_to_hls(r, g, b)
    if s_ < 0.08:
        return couleur
    r, g, b = colorsys.hls_to_rgb((h + degres / 360) % 1.0, l, s_)
    return "#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in (r, g, b)))


def variante(svg: str, degres: float) -> str:
    """Le meme dessin, toutes ses couleurs tournees d'autant."""
    return re.sub(
        r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b",
        lambda m: tourner_teinte(m.group(0), degres),
        svg,
    )


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
    enrichi, faits = [], 0
    for item in index["items"]:
        enrichi.append(item)
        svg = (objets / item["file"]).read_text(encoding="utf-8")
        for suffixe, degres in TEINTES:
            nom = item["file"].replace(".svg", f"-{suffixe + 1}.svg")
            (objets / nom).write_text(variante(svg, degres), encoding="utf-8")
            enrichi.append({
                **item, "id": f"{item['id']}-{suffixe + 1}", "file": nom,
                "label": {lg: f"{txt} · {suffixe + 1}" for lg, txt in item["label"].items()},
                "demo": True,
            })
            faits += 1
    index["items"] = enrichi
    (objets / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{faits:2d} variantes de teinte -> {len(enrichi)} objets en tout")


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


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    demo = "--demo" in sys.argv
    source = Path(args[0]) if args else DEFAUT
    if not source.is_dir():
        raise SystemExit(f"dossier introuvable : {source}")

    importer_gabarit(source / "Gabarit_skin.svg")
    importer(source / "fonds_skin", "fond", "fond_*.svg", "backgrounds", "Vignette_fond_{n}.svg")
    importer(source / "objets_skin", "objet", "objet_*.svg", "objects")
    if demo:
        completer(source)
    ecrire_note("backgrounds", "Fonds de skin", "fonds")
    ecrire_note("objects", "Objets de skin", "objets")

    rendus = MEDIA / "renders"
    if rendus.is_dir():
        for f in rendus.glob("*.jpg"):
            f.unlink()
        print("rendus precedents effaces")


if __name__ == "__main__":
    main()
