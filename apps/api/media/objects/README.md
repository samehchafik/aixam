# Objets de skin

Le jeu de donnees des objets de la borne. Genere UNE FOIS par
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
