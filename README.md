# FeurGestion

Bot Telegram de gestion du groupe **feurchat** : modération, fiches utilisateurs, logs et message de bienvenue.

Python 3.13 + [aiogram](https://docs.aiogram.dev/) + SQLite. Tourne en long polling (pas de serveur web, pas de domaine).

## Commandes

Réservées aux IDs de `ADMIN_IDS`. Préfixes acceptés : `.` `!` `/`.
La cible se donne en **répondant à un message**, ou avec `@pseudo` / ID.

| Commande | Effet |
| --- | --- |
| `.ban [durée] [raison]` | Bannir (sans durée = définitif) |
| `.unban` | Débannir |
| `.mute [durée] [raison]` | Rendre muet (sans durée = définitif) |
| `.unmute` | Rendre la parole (droits par défaut du groupe) |
| `.kick [raison]` | Expulser (peut revenir avec un lien) |
| `.info [@pseudo\|ID]` | Fiche : statut, activité, sanctions, historique, anciens noms |
| `.logs [nombre]` | Dernières sanctions |
| `.welcome …` | Message de bienvenue (voir plus bas) |
| `.help` | Aide |

Durées : `30s`, `10m`, `1h`, `1d` (ou `1j`), `1w`, combinables (`1h30m`). Entre 30 s et 366 j.

Exemples : `.mute @pseudo 1h spam`, `.ban 123456789 pub`, ou en réponse : `.ban insultes`.

Les commandes marchent aussi en privé avec le bot (pratique pour `.info` et `.logs`).

### `@pseudo`

Telegram ne permet pas à un bot de trouver quelqu'un par son pseudo : le bot mémorise toutes les personnes
qu'il voit écrire. Un `@pseudo` ne marche donc que si la personne a écrit au moins une fois depuis l'arrivée du bot.
Sinon : ID ou réponse à un message.

### Bienvenue

- `.welcome` — voir l'état et un aperçu
- `.welcome Salut {mention} !` — changer le texte (la mise en forme Telegram est gardée)
- Photo / GIF / vidéo avec la légende `.welcome texte`, ou `.welcome texte` en réponse à un média — avec média
- `.welcome nomedia` — retirer le média
- `.welcome on` / `.welcome off`
- `.welcome reset` — message par défaut

Variables : `{mention}` `{name}` `{username}` `{id}` `{chat}` `{count}` (nombre de membres).

## Logs

- Chaque sanction est enregistrée en base (qui, par qui, quand, durée, raison) et visible via `.info` / `.logs`.
- Un log détaillé est envoyé en privé à l'admin (ou dans `LOG_CHAT_ID`), avec `#BAN #id123…` pour chercher,
  le lien vers la commande et le message visé transféré comme preuve.
- Les sanctions faites **à la main** par d'autres admins (sans le bot) sont aussi journalisées.
- Arrivées (avec le lien d'invitation utilisé) et départs sont enregistrés en base.
- Les changements de nom / pseudo sont gardés.

## Mise en place côté Telegram

1. Ajouter le bot au groupe et le passer **admin** avec le droit **« Bannir des utilisateurs »**
   (sans ça il ne voit pas les messages `.commande` et ne peut sanctionner personne).
2. L'admin envoie `/start` au bot en privé pour recevoir les logs.

## Variables d'environnement

Voir [`.env.example`](.env.example).

| Variable | Rôle |
| --- | --- |
| `BOT_TOKEN` | Token @BotFather |
| `CHAT_ID` | ID du groupe géré (avec ou sans `-100`) |
| `ADMIN_IDS` | IDs autorisés, séparés par des virgules |
| `LOG_CHAT_ID` | Destination des logs (défaut : premier admin en privé, `off` pour couper) |
| `DB_PATH` | Fichier SQLite (Railway : `/data/feurgestion.db` sur un volume) |
| `TZ` | Fuseau des dates (défaut `Europe/Paris`) |

## Lancer en local

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
BOT_TOKEN=... CHAT_ID=... ADMIN_IDS=... .venv/bin/python -m feurgestion
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
