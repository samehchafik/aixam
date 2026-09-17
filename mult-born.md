# Gestion multi-borne

Plan, pas encore implemente. Ecrit le 17/09/2026.

## Le principe

- **1 machine = 1 borne.** Le poste et la borne ne font qu'un.
- **L'identite d'une borne est son client de relais**, deja minte et nomme par le
  maitre sur le serveur Debian. Rien a inventer, rien a distribuer, rien a
  appairer.
- **Le maitre estampille** chaque ligne a l'arrivee, d'apres la connexion
  authentifiee. Une ligne ne peut pas mentir sur son origine.
- **Une personne est unique par borne** : la cle de `visitors` devient
  `(email, borne)`.

## Ce qui existe deja

| Brique | Etat |
|---|---|
| `designs.kiosk_id`, `events.kiosk_id` | existent, renseignes a la creation |
| Authentification du front par `X-Kiosk-Token` | existe |
| `/api/admin/kiosks` (lister, creer avec jeton) | existe, sans ecran |
| Identite d'un poste cote maitre | existe : son client de relais |
| Remontee authentifiee par ce jeton | existe |

Le schema et l'authentification sont donc en place. Ce qui manque est l'unicite
de l'identite d'une machine a l'autre, et le fait que la remontee **efface**
aujourd'hui `kiosk_id` en arrivant sur le maitre -- avec la bonne raison : cet
identifiant n'existe pas dans sa base, la cle etrangere le refuserait.

## Cote stand : rien ne change

C'est le principal merite de la contrainte « 1 machine = 1 borne ».

La base locale garde `email` UNIQUE : une machine ne servant qu'une borne, la
cle composite y est equivalente a l'e-mail seul. L'inscription continue de
reprendre la ligne existante, `dedupe_visitors` reste valable, le front, le
`config.json` et le lanceur ne bougent pas.

La remontee non plus ne change pas : elle n'envoie aucune provenance, elle n'a
rien a envoyer.

Seul changement visible : le back-office local affiche le nom de sa borne, celui
que porte son client de relais.

## Cote maitre : deux changements de schema

**1. Une colonne de provenance** sur `visitors`, `designs` et `events` -- cle
etrangere vers `relay_clients` -- remplie a l'ingestion, jamais recue du client.

**2. La cle unique de `visitors` passe de `email` a `(email, borne)`.**

Un piege a connaitre avant de l'ecrire : PostgreSQL considere les `NULL` comme
distincts dans un index unique. Une ligne sans provenance echapperait donc
entierement a la contrainte. La colonne doit etre **NOT NULL**, ce qui impose de
rattacher les lignes deja presentes sur le maitre -- celles d'avant -- a un
client declare une fois pour l'occasion, « Poste historique ». Sans cette
reprise, la contrainte est decorative.

Tant qu'on y est : la deduplication des evenements, aujourd'hui sur
`(session_id, name, created_at)`, gagne la borne. Elle passe de chanceuse a
exacte.

## Ce que la cle composite change dans le sens des donnees

C'est le vrai sujet, et il ne se voit pas dans le schema. Le maitre cesse d'etre
un **annuaire de personnes** pour devenir un **registre de passages**. C'est plus
riche -- on saura qu'une personne est passee sur deux bornes, et quand -- mais
chaque requete qui allait de soi doit desormais dire laquelle des deux choses
elle veut. Quatre endroits, tous deja ecrits, ou ca se paie.

### Le consentement

Une meme personne peut accepter sur une borne et refuser sur l'autre. Il faut une
regle, et explicite : **la volonte la plus recente l'emporte**.

La cle composite donne gratuitement ce qu'une fusion detruirait : l'historique du
consentement, avec sa borne et sa date. En cas de controle, c'est une preuve, pas
une declaration.

### L'effacement RGPD

`delete_visitor` supprime aujourd'hui une ligne par son identifiant. Il doit
devenir « toutes les lignes de cette adresse, toutes bornes confondues », sinon
le droit a l'effacement n'est honore qu'a moitie -- et personne ne s'en
apercevra avant la demande qui compte. Non negociable.

### L'export CSV

Il sort aujourd'hui une ligne par enregistrement. Il doit sortir une ligne par
personne, avec la regle de consentement appliquee. Sinon le CRM recoit deux fois
la meme adresse.

### Les compteurs

`visitors_total` devient ambigu. Deux nombres, nommes : les **passages** (par
borne) et les **personnes** (adresses distinctes, sur le salon). Les afficher
separement vaut mieux que d'en choisir un.

### En contrepartie

Chaque creation pointe vers la ligne visiteur de sa propre borne. Aucune
reecriture d'identifiant, jamais, ni a la remontee ni plus tard.

## Les ecrans

- **Bornes** : l'ecran « Clients de relais » promu -- libelle, code, derniere
  remontee, compteurs, revocation. Rien a construire, quelque chose a renommer et
  a enrichir.
- **Filtre borne global** sur Tableau de bord, Visiteurs et Creations, garde dans
  l'URL pour qu'un lien reste partageable.
- **Tableau de bord** : par borne (passages, creations, taux de validation,
  derniere activite) et, en tete, les totaux du salon avec les deux comptages
  distincts.
- **Creations** : un badge de borne sur chaque carte, et le filtre qui va avec.
- **Visiteurs** : une colonne borne, et une bascule « regrouper par personne » --
  c'est la que la regle de consentement devient visible plutot que cachee dans
  une requete.
- **Export** : colonne borne, suit le filtre affiche, une ligne par personne par
  defaut.

## Decoupage

| Lot | Contenu | Quand |
|---|---|---|
| **0** | Provenance estampillee, cle composite, reprise des lignes historiques | avant le deuxieme stand |
| **1** | Les regles de sens : consentement, effacement, comptages, export | avec le lot 0 -- court en code, lourd en decision |
| **2** | Les ecrans | le vrai travail, livrable salon par salon |

## Par ou commencer

Un seul scenario de test les couvre tous : **deux stands, la meme personne
inscrite sur les deux, une remontee depuis chacun**. La chaine existante
(`apps/api/tests/test_sync_chain.py`) sait deja monter deux bases et faire de
vrais appels HTTP ; il suffit d'y ajouter un second stand.

L'ecrire en premier : il echoue aujourd'hui, et il echoue sur la violation de
contrainte decrite ci-dessous. La demonstration avant la correction.

## Le bug que le multi-machine revele

Independant du plan, mais bloquant des le deuxieme stand.

`visitors.email` est UNIQUE sur le maitre, et la remontee reconcilie les
visiteurs **sur leur UUID** (`ON CONFLICT (id)`). Or deux bornes qui inscrivent
la meme personne lui donnent chacune un UUID different. A la deuxieme remontee,
le maitre recoit un nouvel identifiant portant un e-mail deja pris : violation de
contrainte, erreur 500, et le stand rejoue son lot indefiniment sans jamais
passer. Un seul visiteur passe sur deux bornes bloque toute la remontee de l'une
des deux.

La cle composite `(email, borne)` est precisement ce qui le resout : les deux
lignes cohabitent, chacune chez elle.

## Ce qu'on a ecarte, et pourquoi

**Un schema PostgreSQL par borne.** Viable a 300 bornes (12 600 relations,
mesure : 42 relations par schema), intenable si le chiffre decuple. Mais surtout
inutile ici : `kiosk_id` existe deja et est deja renseigne, donc le schema par
borne n'economise qu'un `WHERE` deja ecrit et indexe. Il inverse le cout des deux
requetes -- la transversale, qui est la frequente sur un stand, devient un
`UNION ALL` a 300 branches -- et il casse l'unicite de l'e-mail, c'est-a-dire
l'actif du projet. Les migrations passent de 6 ordres DDL au demarrage a 1 800.
Le volume ne le justifie pas : 300 bornes x 1 000 creations font 300 000 lignes,
qu'une table indexee ne remarque pas.

Si une separation physique devenait necessaire, le bon outil serait le
partitionnement declaratif par borne : une table logique, N tables physiques,
requetes transversales preservees.

**Plusieurs bornes par machine.** C'etait le plan initial. Il imposait un
registre de bornes minte puis replique, un ordre de remontee (« les bornes avant
les lignes »), un controle d'appartenance cote maitre, un appairage des fenetres
Chrome par profil et un ecran de provisionnement. La contrainte « 1 machine =
1 borne » efface tout cela.

Elle ne coute pas le grand ecran : un mur n'est pas une borne, il ne produit
rien, il affiche. Une machine peut donc porter sa borne et son mur, et le lanceur
multi-fenetres garde tout son sens, avec deux fenetres dont une seule
s'authentifie.

**Un UUID de visiteur derive de l'e-mail** (UUID v5). Les deux bornes auraient
spontanement produit le meme identifiant pour la meme personne, et la
reconciliation sur l'id serait retombee juste. Ecarte au profit de la cle
composite, qui conserve l'historique par borne au lieu de fusionner.

## Decisions restant a trancher

- **La regle de consentement** : a fixer avant la collecte, c'est la seule
  irreversible du lot -- des donnees collectees sous une regle ambigue ne se
  re-consentent pas.
- **Le mur du grand ecran** affiche-t-il les creations de toutes les bornes du
  salon, ou seulement celles de la sienne ? Un reglage par mur, valeur par defaut
  « toutes », un mur etant un objet partage.
- **Le verdict de moderation ne remonte pas** : `moderation` n'est ni dans la
  charge de la remontee, ni dans l'upsert du maitre. Avec plusieurs bornes, le
  maitre devient le poste d'observation ; le travail des animateurs devrait y
  arriver.
