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
QUOI_ANSWERS = ["feur", "feur", "feur", "feur 😏", "FEUR.", "feur. Désolé, c'est plus fort que moi.", "quoicoubeh"]
FEUR_RULES = [
    (re.compile(r"(?:quoi+|koi+|kwa+|quoa+|koa+)"), QUOI_ANSWERS),
    (re.compile(r"pourquoi+"), ["pour feur"]),
    (re.compile(r"oui+"), ["stiti 🐒"]),
    (re.compile(r"ouai+s?"), ["stern 🤠"]),
    (re.compile(r"non+"), ["bril"]),
    (re.compile(r"hei+n+"), ["deux", "apagnan"]),
    (re.compile(r"comment"), ["dant 🫡"]),
    (re.compile(r"qui+"), ["rikou"]),
    (re.compile(r"quand"), ["dide"]),
    (re.compile(r"moi"), ["sissure 🍄"]),
    (re.compile(r"toi"), ["lette 🚽"]),
    (re.compile(r"[çcs]a"), ["pristi"]),
    (re.compile(r"mais"), ["zon 🏠"]),
    (re.compile(r"a+h+"), ["bricot 🍑"]),
]
_WORD = re.compile(r"[a-zàâçéèêëîïôûùüÿœæ]+")
_QUOI = FEUR_RULES[0][0]
# « quoi (pas de feur) », « quoi sans feur »... : les petits malins
_ANTI_FEUR = re.compile(r"\b(?:pas|sans|no|anti|stop|interdit)\s+(?:de\s+|d'|le\s+)?feur", re.I)
_LAUGH = re.compile(r"\b(?:mdr+|ptdr+|xptdr+|lol+|mort de rire|jpp+)\b", re.I)


class FeurResult:
    def __init__(self, answer: str | None = None, is_quoi: bool = False, reaction: str | None = None) -> None:
        self.answer = answer
        self.is_quoi = is_quoi
        self.reaction = reaction


def analyze(text: str) -> FeurResult:
    """Ce que le bot répond (et la réaction qu'il met) à un message ordinaire."""
    lowered = text.lower()
    words = _WORD.findall(lowered)
    laugh = "🤣" if _LAUGH.search(lowered) else None
    if not words:
        return FeurResult(reaction=laugh)
    last = words[-1]

    if _ANTI_FEUR.search(lowered) and any(_QUOI.fullmatch(word) for word in words):
        return FeurResult("Bien essayé. Feur. 😏", is_quoi=True, reaction="🤡")
    if last == "feur":
        return FeurResult("Tu fais mon travail maintenant ? 😤", reaction=laugh)
    for index, (pattern, answers) in enumerate(FEUR_RULES):
        if pattern.fullmatch(last):
            if index == 0:
                return FeurResult(random.choice(answers), is_quoi=True, reaction="🤡")
            if random.random() < 0.5:
                return FeurResult(random.choice(answers), reaction=laugh)
            break
    return FeurResult(reaction=laugh)


def feur_reply(text: str) -> str | None:
    """La chute à répondre si le message finit par un mot piège, sinon None."""
    return analyze(text).answer


def quip(kind: str) -> str:
    return random.choice(QUIPS[kind])


# Titres du feurboard : nombre de « quoi » -> titre
FEUR_TITLES = {
    10: "Victime certifiée 🎖",
    25: "Client fidèle du feur 🛒",
    50: "Abonné au feur 📰",
    100: "Légende du quoi 🏆",
    250: "Le quoi incarné 👑",
}


def feur_title(count: int) -> str:
    title = "Innocent 😇"
    for threshold, name in FEUR_TITLES.items():
        if count >= threshold:
            title = name
    return title


EASTER_EGGS = [
    "ERREUR 404 : humour introuvable.",
    "J'ai rien compris mais je rigole quand même. Ha. Ha.",
    "Ce message a été analysé par mes soins : 3/20, peut mieux faire.",
    "Je fais semblant de ne pas avoir lu ça.",
    "Message signalé à la police du bon goût. 🚓",
]

# Mot interdit du jour : assez courant pour tomber, pas trop pour durer un peu
FORBIDDEN_WORDS = [
    "demain", "jamais", "vraiment", "travail", "manger", "dormir", "bizarre", "carrément", "frérot", "wesh",
    "flemme", "sérieux", "chelou", "incroyable", "pizza", "école", "argent", "fatigué", "téléphone", "musique",
    "match", "pote", "daron", "daronne", "chaud", "frère", "insta", "tiktok", "snap", "kebab", "mcdo", "cours",
    "bac", "prof", "devoirs", "film", "série", "jeu", "console", "soirée", "voiture", "chien", "chat",
]

ROULETTE_SAFE = [
    "🔫 *clic*… Rien. Tu vis. Pour l'instant.",
    "🔫 *clic*… Ouf. Ta mère peut dormir tranquille.",
    "🔫 *clic*… Chanceux. Retente, pour voir ?",
    "🔫 *clic*… Le barillet t'aime bien. Lui.",
]
ROULETTE_DEAD = [
    "💥 PAN ! {mention} est mort. 1 minute de silence. RIP.",
    "💥 PAN ! {mention} a perdu. On se recueille 1 minute. 🕯",
    "💥 PAN ! Et {mention} rejoint le cimetière des bavards pour 1 minute.",
]
ROULETTE_ARMORED = "💥 PAN ! … mais {mention} est admin : gilet pare-balles. C'est de la triche, mais c'est la vie."

COUPLE_QUIPS = [
    "Les bans de mariage sont publiés. Enfin, les bans tout court, on verra.",
    "Ils ne le savent pas encore, mais c'est écrit.",
    "Félicitations. Ou condoléances, au choix.",
    "Le bot a parlé. Le bot ne se trompe jamais (sauf souvent).",
]
ELU_QUIPS = [
    "Bravo, c'est mérité. Personne ne sait pourquoi, mais c'est mérité.",
    "Une statue sera érigée en ton honneur. En carton.",
    "Tu peux le mettre sur ton CV.",
    "Le peuple a voté. Enfin, moi. Mais moi c'est le peuple.",
]

INSULT_NOUNS = [
    "paltoquet", "faquin", "maraud", "malotru", "gougnafier", "olibrius", "foutriquet", "freluquet", "cuistre",
    "butor", "goujat", "pignouf", "vaurien", "galopin", "bélître", "jean-foutre", "cornichon", "nigaud",
    "sagouin", "zigoto", "malandrin", "gredin", "pleutre", "fripouille", "bougre d'âne", "va-nu-pieds",
]
INSULT_ADJECTIVES = [
    "mal embouché", "de basse extraction", "à la manque", "en carton", "de pacotille", "mal dégrossi",
    "sans vergogne", "à roulettes", "de compétition", "en promotion", "du dimanche", "au rabais", "sous-cuit",
    "mal luné", "de seconde zone", "en solde", "périmé", "mal fini",
]

HACK_STEPS = [
    "💻 Connexion au cerveau de {name}…",
    "🔓 Contournement du pare-feu… 12 %",
    "📂 Récupération de l'historique de recherche… 47 %",
    "📸 Accès à la galerie (on a vu des choses)… 73 %",
    "🧠 Analyse du cerveau… 99 % (ça a été rapide)",
]
HACK_RESULTS = [
    "Historique de recherche : « comment dire quoi sans se prendre un feur »",
    "Mot de passe : feur123",
    "Dernière recherche : « est-ce que les admins me détestent »",
    "Playlist la plus écoutée : « Musique d'ascenseur vol. 3 »",
    "Dossier secret : 412 captures d'écran de feurchat",
    "Note sur son téléphone : « penser à être drôle demain »",
    "Recherche Google : « comment devenir modo de feurchat »",
    "Brouillon jamais envoyé : « quoi ? »",
]


def love_comment(score: int) -> str:
    if score <= 20:
        return "💔 Aucun avenir. Même pas en amis."
    if score <= 50:
        return "🤝 Bons potes, restez-en là."
    if score <= 80:
        return "💕 Ça pourrait le faire. Avec beaucoup d'efforts."
    if score < 100:
        return "💘 Mariez-vous. Le bot sera témoin."
    return "💍 Âmes sœurs. Même le bot est ému."


def iq_comment(score: int) -> str:
    if score < 50:
        return "Comme une huître. Mais en moins brillant."
    if score < 90:
        return "Dans la moyenne… basse. Très basse."
    if score < 130:
        return "Normal. Désolé, c'est tout ce que j'ai."
    if score < 170:
        return "Brillant ! Suspect, même."
    return "Génie. Ou bug du bot. Sûrement bug du bot."


TOP_TITLES = [
    "🥇 Pipelette en chef",
    "🥈 Moulin à paroles",
    "🥉 Bavard certifié",
    "4️⃣ Clavier en surchauffe",
    "5️⃣ Commentateur officiel",
    "6️⃣ Toujours un truc à dire",
    "7️⃣ Bavard du dimanche",
    "8️⃣ Présent, mais discret",
    "9️⃣ Figurant",
    "🔟 Juste là pour la photo",
]

BIRTHDAY_LINES = [
    "+1 an, -1 neurone. On t'aime (un peu).",
    "T'as pris un an. Nous on a pris l'habitude de te supporter.",
    "Souffle tes bougies, pas sur le gâteau des autres.",
    "Encore un an de plus à dire « quoi ». Feur.",
]

MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def flocko_comment(value: int) -> str:
    if value == 0:
        return "0 %. Pas une goutte de flocko. Impressionnant, dans l'autre sens."
    if value <= 20:
        return "Flocko en PLS. Va te reposer."
    if value <= 40:
        return "Flocko timide. Ça viendra. Peut-être."
    if value <= 60:
        return "Flocko dans la moyenne. Comme ta vie."
    if value <= 80:
        return "Ça flocko sérieusement, là. Respect."
    if value < 100:
        return "FLOCKO ULTIME. Les autres tremblent."
    return "💯 100 % FLOCKO. Plus rien à prouver. Encadre-le."
