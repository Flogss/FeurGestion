# FeurBot

Le bot officiel de **feurchat** : modération, logs, warns, notes, verrous anti-pub… et des blagues nulles.
Il répond « feur » quand on dit « quoi ». Évidemment.

Python 3.13 + [aiogram](https://docs.aiogram.dev/) + SQLite. Tourne en long polling (pas de serveur web, pas de domaine),
environ 180 Mo de RAM.

Fonctions inspirées de [MissKatyPyro](https://github.com/yasirarism/MissKatyPyro) (yasirarism), réécrites pour ce bot.

## Commandes

Préfixes acceptés : `.` `!` `/`. Les commandes marchent aussi en privé avec le bot.
`.help` affiche une aide à boutons (version admin) ou la liste des commandes publiques (membres).
Un non-admin qui tente une commande d'admin se fait gentiment chambrer.

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

### Fun

- Réponses automatiques (`.feur on|off`) : quoi → feur, et une fois sur deux oui → stiti, non → bril,
  hein → deux, comment → dant, qui → rikou… (10 s minimum entre deux répliques)
- `.blague`, `.pileouface`, `.de`, `.dard`, `.slot`, `.foot`, `.basket`, `.bowling`, `.boule question`, `.quoi`

### Bienvenue

- `.welcome` — voir l'état et un aperçu
- `.welcome Salut {mention} !` — changer le texte (la mise en forme Telegram est gardée)
- Photo / GIF / vidéo avec la légende `.welcome texte`, ou `.welcome texte` en réponse à un média
- `.welcome nomedia`, `.welcome on` / `.welcome off`, `.welcome reset`

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
