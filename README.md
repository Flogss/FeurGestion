# FeurBot

Le bot officiel de **feurchat** : modération, logs, warns, notes, verrous anti-pub… et des blagues nulles.
Il répond « feur » quand on dit « quoi ». Évidemment.

Python 3.13 + [aiogram](https://docs.aiogram.dev/) + SQLite + Pillow (image du `/topflocko`).
Tourne en long polling (pas de serveur web, pas de domaine).

Fonctions inspirées de [MissKatyPyro](https://github.com/yasirarism/MissKatyPyro) (yasirarism), réécrites pour ce bot.

## Commandes

Toutes les commandes marchent avec `/`, `.` ou `!`, dans le groupe ou en privé avec le bot.
Le menu « / » de Telegram propose à chacun les commandes de son rôle (membre, modo, admin).

`/help` ouvre un menu à boutons adapté au rôle de la personne (avec une astuce au hasard) ;
`/help duel` donne l'aide d'une seule commande. Un non-admin qui tente une commande d'admin se fait gentiment chambrer.

### Rôles

- **Admins du bot** (`ADMIN_IDS`) : tout, y compris la configuration du bot et la nomination des modos.
- **Modos** (nommés avec `.mod`) : ban, mute, kick, warn, déban / démute, purge, del, pin, `.info`, `.logs`
  et les boutons « Annuler » / « Retirer ». Ils ne peuvent ni configurer le bot, ni sanctionner un autre modo ou un admin.
  Les verrous ne les bloquent pas. Ce ne sont pas des admins Telegram : avec `.lock tout`, ils ne peuvent plus écrire.

| Commande | Effet |
| --- | --- |
| `.mod @pseudo\|ID` | Nommer modo (ou en réponse) — admins du bot |
| `.unmod @pseudo\|ID` | Retirer le rôle — admins du bot |
| `.mods` | Voir l'équipe (tout le monde) |

### Modération (admins et modos)

La cible se donne en **répondant à un message**, ou avec `@pseudo` / ID.

| Commande | Effet |
| --- | --- |
| `.ban [durée] [raison]` | Bannir (sans durée = définitif) |
| `.deban` (ou `.unban`) | Débannir |
| `.mute [durée] [raison]` | Rendre muet (sans durée = définitif) |
| `.demute` (ou `.unmute`) | Rendre la parole (droits par défaut du groupe) |
| `.kick [raison]` | Expulser (peut revenir avec un lien) |

Raison et durée sont facultatives. Durées : `30s`, `10m`, `1h`, `1d` (ou `1j`), `1w`, combinables (`1h30m`).

- Au `.ban` et au `.mute` dans le groupe, la commande est supprimée, ainsi que le message auquel tu réponds
  (seulement s'il est de la personne sanctionnée). Il est d'abord transféré dans les logs comme preuve.
- Sous chaque ban / mute, un bouton **↩️ Annuler** (réservé aux admins).

### Warns (admins et modos, sauf `.warnlimit` / `.warnaction`)

| Commande | Effet |
| --- | --- |
| `.warn [raison]` | Avertir (bouton **🧽 Retirer le warn**) |
| `.unwarn` / `.resetwarns` | Retirer le dernier / tous les warns |
| `.warns [@pseudo]` | Voir les warns (tout le monde) |
| `.warnlimit 3` | Nombre de warns avant sanction |
| `.warnaction mute\|ban\|kick` | Sanction automatique à la limite (mute = 24 h) |

### Notes, filtres et règles

| Commande | Effet |
| --- | --- |
| `.save nom texte` | Créer une note (ou en réponse à un message / média) |
| `#nom` ou `.get nom` | Afficher une note (tout le monde) |
| `.notes` / `.clear nom` | Lister / supprimer |
| `.filter mot réponse` | Réponse automatique quand quelqu'un écrit le mot (`"plusieurs mots"` entre guillemets) |
| `.filters` / `.stop mot` | Lister / supprimer |
| `.setrules texte` / `.rules` | Définir / afficher les règles |

Variables utilisables (notes, filtres, règles, bienvenue) : `{mention}` `{name}` `{username}` `{id}` `{chat}` `{count}`.

### Verrous

`.lock type`, `.unlock type`, `.locks` pour l'état. Les admins ne sont jamais bloqués.

- `liens` : supprime les liens et pubs des non-admins (avec un rappel « PUB = MUTE »)
- `transferts` : supprime les messages transférés
- `medias`, `stickers`, `sondages`, `apercus` : coupe ces droits Telegram
- `tout` : groupe en lecture seule

### Infos et outils

| Commande | Effet |
| --- | --- |
| `.info [@pseudo\|ID]` | Fiche : statut, activité, sanctions, warns, historique des pseudos et des noms |
| `.logs [nombre]` | Dernières sanctions |
| `.sangmata on\|off` | Annoncer dans le groupe les changements de pseudo / nom |
| `.purge` | En réponse : efface tout jusqu'à la commande (1000 messages max) |
| `.del` | Supprime le message visé |
| `.pin [silence]` / `.unpin` | Épingler / désépingler |
| `.report` (ou `@admin` en réponse) | Signaler un message aux admins (tout le monde) |
| `.afk [raison]` (ou « brb ») | S'absenter : le bot prévient ceux qui te mentionnent (tout le monde) |
| `.id`, `.ping` | Tout le monde |

### Le feur

- Réponses automatiques (`/feur on|off`) : quoi → feur (ou quoicoubeh), et une fois sur deux oui → stiti,
  non → bril, hein → deux / apagnan, comment → dant… (10 s minimum entre deux répliques)
- « quoi (pas de feur) » → « Bien essayé. Feur. » ; quelqu'un qui écrit « feur » → « Tu fais mon travail ? »
- Réactions : 🤡 sur les « quoi », 🤣 sur les « mdr ». Un message sur 500 reçoit un easter egg.
- `/feurboard` : classement des « quoi », avec des titres débloqués à 10, 25, 50, 100 et 250.

### Jeux

| Commande | Effet |
| --- | --- |
| `/flocko` | Ton taux de flocko : un nouveau tirage toutes les 12 h |
| `/topflocko` | Classement en image style mème (bulles « quoi ? » / « feur. »), records de tous les temps, jamais remis à zéro ; ⬅️ page suivante, ➡️ page précédente |
| `/roulette` | 1 chance sur 6 d'être mute 1 minute (les admins Telegram sont immunisés) |
| `/duel @pseudo` | L'autre accepte avec un bouton, le perdant est mute 1 minute |
| `/prison` | Qui est mute / banni en ce moment, avec le temps restant |
| `/motinterdit` | Un mot secret par jour : le premier qui l'écrit explose (1 min de mute). L'admin le voit en privé |

`/jeux on|off` coupe roulette et duels, `/motinterdit on|off` le mot interdit (admins).

### Fun

- `/blague`, `/pileouface`, `/de`, `/dard`, `/slot`, `/foot`, `/basket`, `/bowling`, `/boule question`, `/quoi`
- `/couple` et `/elu` : tirés parmi les actifs de la semaine, fixes pour la journée
- `/love @a @b`, `/qi @pseudo` : scores fixes pour la journée (pas de triche)
- `/hack @pseudo` (faux piratage animé), `/clash @pseudo` (insulte vieille France), `/moqueur` en réponse

### Musique (mode inline)

Dans n'importe quelle conversation, taper `@feurzizibot` puis un titre ou un artiste, sans appuyer sur Entrée :
les morceaux de Deezer s'affichent avec leur pochette (Top France si rien n'est tapé).

Le morceau choisi part d'abord comme une carte (grande pochette + « 🎵 Titre — Artiste »), puis le bot la remplace
par l'extrait de 30 s, pochette intégrée au lecteur. Le remplacement est automatique si l'« inline feedback »
est activé dans @BotFather, sinon il se fait avec le bouton ▶️ de la carte.

Pour coller la pochette au fichier, le bot envoie l'extrait une seule fois en silence dans la conversation
privée de l'admin (`LOG_CHAT_ID`), l'efface aussitôt et garde le fichier en base pour les fois suivantes.
Utilise l'API publique de Deezer (gratuite, sans clé). Les morceaux complets ne sont pas envoyés.

### Mémoire du groupe

- `/citer` en réponse : grave le message dans le livre d'or ; `/citation`, `/citation @pseudo`, `/citation 12` ;
  `/delcitation 12` (admins et modos)
- `/top` : bavards des 7 derniers jours, avec titres et le « fantôme »
- `/anniv JJ/MM`, `/anniv off`, `/anniversaires` : le bot souhaite les anniversaires à minuit dans le groupe

### Bienvenue

À chaque arrivée, une variante est tirée au hasard (jamais deux fois la même d'affilée) et personnalisée
avec le nom et le numéro du membre. 12 variantes au second degré par défaut.

- `/welcome` — voir l'état et un aperçu
- `/welcome list`, `/welcome add texte`, `/welcome del 3` — gérer les variantes
- `/welcome Salut {mention} !` — tout remplacer par un seul texte (la mise en forme Telegram est gardée)
- Photo / GIF / vidéo avec la légende `/welcome`, ou en réponse à un média — ajoute le média
- `/welcome nomedia`, `/welcome on` / `/welcome off`, `/welcome reset`

## Données et sauvegardes

- La base SQLite est sur un volume Railway (`/data`) : elle survit aux déploiements et aux redémarrages.
- Au démarrage, le bot écrit dans les logs le nombre de lignes des tables principales.
- Chaque nuit à 4 h, une sauvegarde part en silence dans la conversation privée de l'admin.
- `/backup` : sauvegarde à la demande, envoyée en privé.
- `/restore` en privé, en réponse à un fichier de sauvegarde : remet la base dans cet état
  (la base actuelle est d'abord gardée dans `/data/avant-restauration.db`).

## Performances

- Serveur Railway à Amsterdam (`eu-west`), à côté des serveurs de Telegram.
- Réglages, filtres, AFK, modos et profils connus gardés en mémoire : un message ordinaire ne lit plus la base.
- SQLite en WAL avec `synchronous=NORMAL` ; `uvloop` et `orjson` pour la boucle et le JSON.
- `/topflocko` : image dessinée en ~15 ms (fond mis en cache, JPEG), photos de profil attendues 2 s maximum,
  et image réutilisée telle quelle tant que le classement ne change pas. Pillow n'est chargé qu'au premier appel.

## Logs

- Chaque sanction est enregistrée en base (qui, par qui, quand, durée, raison) et visible via `.info` / `.logs`.
- Un log détaillé part en privé à l'admin (ou dans `LOG_CHAT_ID`) : `#BAN #id123…`, `#WARN`, `#REPORT`…,
  avec le lien et le message visé transféré comme preuve.
- Les sanctions faites **à la main** par d'autres admins sont aussi journalisées.
- Arrivées (avec le lien d'invitation utilisé), départs, changements de pseudo et de nom sont enregistrés.
  Telegram ne donne pas l'historique d'avant : il commence quand le bot voit la personne.

## Mise en place côté Telegram

1. Ajouter le bot au groupe et le passer **admin** avec les droits **« Bannir des utilisateurs »**,
   **« Supprimer des messages »** et **« Épingler des messages »** (sans admin il ne voit pas les `.commandes`).
2. L'admin envoie `/start` au bot en privé pour recevoir les logs.
3. Pour la musique : dans @BotFather, `/setinline` (texte d'invite, ex. « Titre ou artiste… »)
   puis `/setinlinefeedback` → `Enabled` pour que l'extrait remplace la carte tout seul.

## Variables d'environnement

Voir [`.env.example`](.env.example).

| Variable | Rôle |
| --- | --- |
| `BOT_TOKEN` | Token @BotFather |
| `CHAT_ID` | ID du groupe géré (avec ou sans `-100`) |
| `ADMIN_IDS` | IDs autorisés, séparés par des virgules |
| `LOG_CHAT_ID` | Destination des logs (défaut : premier admin en privé, `off` pour couper) |
| `DB_PATH` | Fichier SQLite (Railway : `/data/feurgestion.db` sur un volume, nom historique gardé) |
| `TZ` | Fuseau des dates (défaut `Europe/Paris`) |

## Lancer en local

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
BOT_TOKEN=... CHAT_ID=... ADMIN_IDS=... .venv/bin/python -m feurbot
```

Tests (sans réseau, API Telegram simulée) :

```bash
.venv/bin/python tests/smoke.py
```

## Déploiement Railway

Service `FeurGestion` dans le projet `daring-spirit`, construit avec le `Dockerfile` (détecté tout seul), 1 seule instance,
volume monté sur `/data` pour la base. Déployer :

```bash
railway up --service FeurGestion --detach
```
