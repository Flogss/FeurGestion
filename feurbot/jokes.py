"""Blagues, répliques au second degré et l'art ancestral du « quoi → feur »."""

import random
import re

# Petite phrase ajoutée sous les messages du bot, selon la situation
QUIPS = {
    "ban": [
        "Il est parti acheter des clopes. Pour toujours.",
        "Allez, ouste ! Et on ne revient pas.",
        "Banni. C'est triste. Enfin non, pas vraiment.",
        "La porte, c'est par là. Ah, trop tard, elle est fermée.",
        "Feur-mé définitivement. 🔒",
        "Il a demandé « quoi ? ». On a répondu « dehors ».",
    ],
    "mute": [
        "Chut. On t'a assez entendu.",
        "Mode avion activé ✈️",
        "Le silence est d'or. Profite, t'es riche maintenant.",
        "Tu peux toujours lire. C'est déjà ça.",
        "Bouche cousue, comme un « quoi » sans « feur ».",
        "Ton clavier est en vacances. Pas toi.",
    ],
    "kick": [
        "Dehors ! Mais la porte reste entrouverte.",
        "Petit tour à l'extérieur, ça va te faire du bien.",
        "Kické avec amour. Enfin, avec un pied.",
        "Va prendre l'air, reviens quand t'es calmé.",
    ],
    "unban": [
        "Pardonné. Pour cette fois.",
        "Tout le monde a droit à une deuxième chance. Pas à une troisième.",
        "Il peut revenir avec un lien. S'il ose.",
    ],
    "unmute": [
        "Tu peux reparler. Choisis bien tes mots (évite « quoi »).",
        "Le micro est rallumé 🎙",
        "Liberté d'expression restaurée. Ne la gâche pas.",
    ],
    "warn": [
        "Carton jaune 🟨",
        "On te surveille. 👀",
        "Attention, ça commence à sentir le roussi.",
        "Ceci est un avertissement. Le prochain sera moins sympa.",
    ],
    "warn_limit": [
        "Le compteur a explosé 💥",
        "Carton rouge 🟥 Fallait lire les règles.",
        "Trop de warns tue le warn.",
    ],
    "undo": [
        "Fausse alerte, on rembobine ⏪",
        "Ctrl+Z appliqué.",
        "On a rien vu, circulez.",
    ],
    "not_admin": [
        "😂 T'as cru t'étais admin ? Retourne jouer.",
        "🚫 Bien essayé. Mais non.",
        "Tu n'as pas le pouvoir. Ni le charisme, d'ailleurs.",
        "Commande réservée aux admins. Toi tu peux faire <code>.blague</code>, c'est déjà pas mal.",
        "Je vais faire comme si j'avais rien vu. 👀",
        "Erreur 403 : t'es pas admin. Quoi ? Feur.",
    ],
}

JOKES = [
    "Que dit une imprimante dans l'eau ? J'ai papier.",
    "Pourquoi les plongeurs plongent-ils toujours en arrière ? Parce que sinon ils tombent dans le bateau.",
    "Quel est le comble pour un électricien ? De ne pas être au courant.",
    "Qu'est-ce qui est jaune et qui attend ? Jonathan.",
    "Que fait une fraise sur un cheval ? Tagada, tagada.",
    "Pourquoi le livre de maths est triste ? Parce qu'il a trop de problèmes.",
    "Qu'est-ce qu'un canif ? Un petit fien.",
    "Que dit un oignon quand il se cogne ? Aïe-gnon.",
    "Qu'est-ce qui est petit, carré et jaune ? Un petit carré jaune.",
    "Quel est le comble pour un jardinier ? De raconter des salades.",
    "Comment appelle-t-on un boomerang qui ne revient pas ? Un bout de bois.",
    "Qu'est-ce qu'un yaourt dans la forêt ? Un yaourt nature.",
    "Tu connais la blague du chauffeur de bus ? Moi non plus, j'étais à l'arrière.",
    "Quel est le fruit préféré des profs d'histoire ? Les dattes.",
    "Que dit un citron qui fait un braquage ? Les mains en l'air, plus un zeste !",
    "Quel est l'animal le plus heureux ? Le hibou, parce que sa femme est chouette.",
    "Comment s'appelle un chat qui va dans l'espace ? Un chatellite.",
    "Pourquoi les canards sont toujours à l'heure ? Parce qu'ils sont dans l'étang.",
    "Qu'est-ce qui est vert et qui se déplace sous l'eau ? Un chou marin.",
    "Que dit une noisette quand elle tombe à l'eau ? Je me noix.",
    "Quel est le comble pour un marin ? D'avoir le nez qui coule.",
    "Que dit un escargot quand il croise une limace ? Oh, un naturiste.",
    "Comment appelle-t-on un chien qui n'a pas de pattes ? On ne l'appelle pas, on va le chercher.",
    "Pourquoi les poissons n'aiment pas jouer au tennis ? Parce qu'ils ont peur du filet.",
    "Qu'est-ce qu'un crocodile qui surveille la pharmacie ? Un Lacoste garde.",
    "Quelle est la différence entre un pigeon ? Il a les deux pattes de la même longueur, surtout la gauche.",
    "Tu sais pourquoi on répond « feur » quand quelqu'un dit « quoi » ? Moi non plus, mais ça marche à chaque fois.",
    "Un jour, quelqu'un a dit « quoi » dans feurchat. On ne l'a jamais revu. Enfin si, il a été mute 1h.",
]

EIGHTBALL = [
    "Oui. Enfin je crois. Enfin j'en sais rien, je suis un bot.",
    "Non. Et arrête de me poser des questions pareilles.",
    "Clairement oui.",
    "Absolument pas.",
    "Les astres disent oui, mon serveur dit non.",
    "Peut-être. Ou feur.",
    "C'est écrit dans les étoiles. Et dans la bio du groupe.",
    "Je préfère ne pas répondre, j'ai un avocat.",
    "Repose la question après un café.",
    "100 % oui, 0 % sûr.",
    "Non, mais j'admire ton optimisme.",
    "Évidemment. Qui en doutait ?",
    "Mon petit doigt me dit que non. Mon grand doigt aussi.",
    "Demande à un admin. Ils savent tout. Enfin, ils font semblant.",
]

# Dernier mot du message -> chute. Le « quoi » répond toujours, le reste une fois sur deux.
FEUR_RULES = [
    (re.compile(r"(?:quoi+|koi+|kwa+|quoa+|koa+)"), ["feur", "feur", "feur", "feur 😏", "FEUR.", "feur. Désolé, c'est plus fort que moi."]),
    (re.compile(r"pourquoi+"), ["pour feur"]),
    (re.compile(r"oui+"), ["stiti 🐒"]),
    (re.compile(r"ouai+s?"), ["stern 🤠"]),
    (re.compile(r"non+"), ["bril"]),
    (re.compile(r"hei+n+"), ["deux"]),
    (re.compile(r"comment"), ["dant 🫡"]),
    (re.compile(r"qui+"), ["rikou"]),
    (re.compile(r"quand"), ["dide"]),
    (re.compile(r"moi"), ["sissure 🍄"]),
    (re.compile(r"toi"), ["lette 🚽"]),
    (re.compile(r"[çcs]a"), ["pristi"]),
    (re.compile(r"mais"), ["zon 🏠"]),
    (re.compile(r"a+h+"), ["bricot 🍑"]),
]
_LAST_WORD = re.compile(r"[a-zàâçéèêëîïôûùüÿœæ]+")


def quip(kind: str) -> str:
    return random.choice(QUIPS[kind])


def feur_reply(text: str) -> str | None:
    """La chute à répondre si le message finit par un mot piège, sinon None."""
    words = _LAST_WORD.findall(text.lower())
    if not words:
        return None
    last = words[-1]
    for index, (pattern, answers) in enumerate(FEUR_RULES):
        if pattern.fullmatch(last):
            if index > 0 and random.random() < 0.5:
                return None
            return random.choice(answers)
    return None
