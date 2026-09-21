"""
start_pattern.py
-----------------
Détection des DÉBUTS de textes juridiques dans le Bulletin Officiel.

Changements par rapport à l'ancienne version :
- Suppression du bricolage `type('Match', (), {...})()` qui simulait un objet
  re.Match avec des positions recalculées : on passe maintenant des positions
  entières simples, ce qui est plus lisible et moins fragile.
- Les positions absolues (start_position / end_position) sont maintenant
  stockées directement dans le résultat, pour éviter d'avoir à refaire un
  `content.find(full_match)` plus tard (voir arabic_legal_extractor.py :
  ce `.find()` posait un vrai bug sur les textes dupliqués, comme les entrées
  de sommaire qui répètent le début d'un texte réel).
- Les limites arbitraires (nombre de caractères regardés pour le numéro, etc.)
  sont maintenant des constantes nommées en haut du fichier, pour être faciles
  à retrouver et ajuster.
"""

import re
from typing import List, Optional, Dict

# --------------------------------------------------------------------------
# Mots-clés (config)
# --------------------------------------------------------------------------

KEYWORDS_NO_SIGNATURE = [
    "بلاغات",
    "اعلان",
    "إعلان",
    "إعلانات",
    "بلاغ",
    "راي",
    "رأي",
    "قائمة أسماء",
    "قائمة اسماء",
    "سجل بأسماء",
    "سجل باسماء",
]

KEYWORDS = [
    "قرار",
    "مرسوم",
    "ظهير",
    "قانون",
    "ظہیر",
    "ظهير شريف",
    "ظہیر شريف",
    "ظهر شريف",  # variante OCR de "ظهير شريف" (le ي est parfois perdu par l'OCR --
                 # confirmé sur BO_3405 : 3 occurrences mal océrisées contre 1 correcte).
                 # On n'ajoute PAS "ظهر" seul : c'est un mot arabe courant ("dos"/"apparaître"),
                 # l'ajouter causerait beaucoup de faux positifs. "ظهر شريف" en 2 mots reste
                 # un signal fiable.
    "قرار مشترك",
    "قرار تأديبي",
    "منشور",
    "مذكرة",
    "مقرر",
]

NUMBER_INDICATORS = ["رقم", "عدد"]

DATE_INDICATORS = [
    r"صادر\s+في",
    r"صادرة\s+في",
    "صادر في",
    "صادر",
    "صادرة",
    "صادرة في",
    r"بتاريخ\s*",
    "المؤرخ في",
    "المؤرخة في",
]

DATE_END_MARKERS = [
    "و المتعلق",
    "المتعلق",
    "يتعلق",
    "والمتعلق",
    "يقضي",
    "في",
    "الحمد",
    "حول",
    "كما",
    "المتضمن",
    r"\bب\w+",
    "قرر",
]

# --------------------------------------------------------------------------
# Limites (avant : magiques et éparpillées dans le code, maintenant nommées)
# --------------------------------------------------------------------------

# Fenêtre de recherche du numéro après "رقم"/"عدد". Augmentée de 20 -> 30
# car certains numéros suivis d'un indicateur de date étaient tronqués.
NUMBER_LOOKAHEAD_CHARS = 30

# Fallback si aucun marqueur de fin de date n'est trouvé : nombre de mots pris
NO_DATE_END_MARKER_FALLBACK_WORDS = 10

# Distance maximale (en caractères) après le mot-clé où on accepte de chercher
# رقم/عدد. Sans cette limite, un mot-clé sans vrai numéro juste après (ex:
# "قرار بلدي يقضي بـ...") peut faire "sauter" la recherche jusqu'à un رقم
# sans rapport plus loin dans le texte -- par exemple l'en-tête d'un tableau
# markdown ("| بيان الملك | رقم الصك العقاري | ..."), ce qui produit un
# résultat incohérent.
NUMBER_INDICATOR_SEARCH_WINDOW = 160
# (80 -> 160 : les arrêtés conjoints citent plusieurs ministres avant "رقم" --
#  "قرار مشترك لوزير الفلاحة ... ووزير الدولة المكلف بالداخلية ووزير المالية رقم"
#  dépasse 80 caractères ; 6 textes réels perdus sur BO_3409. La fenêtre est
#  en revanche coupée à la première ligne de tableau, voir extract_sequential_info.)

# Fallback pour les textes sans signature quand l'extraction séquentielle échoue
NO_SIGNATURE_FALLBACK_CHARS = 200


def build_start_pattern() -> str:
    """Regex des mots-clés AVEC signature, ancrée en début de ligne."""
    sorted_keywords = sorted(KEYWORDS, key=len, reverse=True)
    keywords_pattern = "|".join(re.escape(k) for k in sorted_keywords)
    return rf"^(?P<keyword>{keywords_pattern})(?=\s|$|[،:؛\.\)])"


def build_no_signature_pattern() -> str:
    """Regex des mots-clés SANS signature, ancrée en début de ligne."""
    sorted_keywords = sorted(KEYWORDS_NO_SIGNATURE, key=len, reverse=True)
    keywords_pattern = "|".join(re.escape(k) for k in sorted_keywords)
    return rf"^(?P<keyword>{keywords_pattern})(?=\s|$|[،:؛\.\)])"


def _levenshtein(a: str, b: str) -> int:
    """Distance d'édition simple (insertions/suppressions/substitutions), sans dépendance externe."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = curr
    return prev[-1]


# Distance d'édition maximale tolérée pour un match "flou" (1 = une seule
# lettre en trop/en moins/substituée, comme le ي manquant de ظهير -> ظهر).
FUZZY_MAX_DISTANCE = 1
# Longueur minimale d'un mot-clé pour la tolérance floue (voir ci-dessous).
FUZZY_MIN_KEYWORD_LEN = 5


def find_fuzzy_keyword_match(stripped_line: str):
    """
    Cherche un mot-clé approximatif en début de ligne quand aucun match exact
    n'a été trouvé -- pour attraper des fautes d'OCR qu'on n'a pas anticipées
    (comme ظهر au lieu de ظهير), sans avoir à lister chaque variante possible
    à la main. Renvoie (mot_clé_canonique, longueur_du_texte_matché) ou None.

    Ces candidats sont plus risqués qu'un match exact (une distance de 1 peut
    aussi matcher un mot totalement différent par coïncidence) : ils sont
    marqués 'fuzzy_matched': True dans extract_start_info, et le pipeline les
    traite avec une politique fail-CLOSED côté Gemma (voir gemma_verifier.py) :
    contrairement aux candidats normaux, un candidat flou est écarté si Gemma
    ne le confirme pas explicitement, ou si la vérification Gemma est désactivée.
    """
    for kw in sorted(KEYWORDS, key=len, reverse=True):
        # Pas de tolérance sur les mots-clés courts : à 1 lettre près, "مقرر"
        # devient "يقرر" (« décide », dans le corps de presque tous les
        # arrêtés : "يقرر ما يلي") et "قرار" devient "قرر". Ces faux débuts
        # tombaient au milieu des textes et en faisaient perdre (BO_3407/3408).
        if len(kw) < FUZZY_MIN_KEYWORD_LEN:
            continue
        for delta in (0, -1, 1):
            length = len(kw) + delta
            if length <= 0 or length > len(stripped_line):
                continue
            prefix = stripped_line[:length]
            if prefix == kw:
                continue  # déjà géré par le match exact
            if _levenshtein(prefix, kw) <= FUZZY_MAX_DISTANCE:
                after = stripped_line[length:length + 1]
                if after == "" or after in " \t،:؛.)":
                    return kw, length
    return None


def extract_sequential_info(
    text: str, keyword: str, keyword_start: int, keyword_end: int
) -> Optional[Dict]:
    """
    Extrait numéro + date après un mot-clé trouvé à [keyword_start:keyword_end].

    Remplace l'ancienne signature `extract_sequential_info(text, keyword_match)`
    qui prenait un faux objet Match : ici on prend directement les entiers,
    plus simple et plus explicite.
    """
    remaining_text = text[keyword_end:]
    date_indicators_pattern = "|".join(DATE_INDICATORS)

    # 1. Indicateur de numéro (رقم / عدد), cherché seulement dans une fenêtre
    #    proche du mot-clé (voir NUMBER_INDICATOR_SEARCH_WINDOW plus haut).
    number_indicators_pattern = "|".join(NUMBER_INDICATORS)
    search_window = remaining_text[:NUMBER_INDICATOR_SEARCH_WINDOW]
    table_line = search_window.find("\n|")
    if table_line != -1:
        search_window = search_window[:table_line]  # jamais de "رقم" pris dans un tableau
    number_indicator_match = re.search(rf"({number_indicators_pattern})\s+", search_window)

    if number_indicator_match:
        # 2. Le numéro lui-même, dans une fenêtre limitée
        number_start = number_indicator_match.end()
        number_text = remaining_text[number_start:number_start + NUMBER_LOOKAHEAD_CHARS]
        if len(re.findall(r"\d", number_text)) < 1:
            number_indicator_match = None  # "رقم" sans chiffres : traiter comme sans numéro
        else:
            date_search = re.search(rf"({date_indicators_pattern})", number_text)
            if date_search:
                number = number_text[:date_search.start()].strip()
                date_indicator_pos = number_start + date_search.start()
            else:
                # L'OCR a parfois perdu l'indicateur de date : le numéro est
                # suivi directement de la date ("رقم 1269.77 ⏎ 12 ذي القعدة 1397").
                # On accepte si une année hégirienne/grégorienne suit de près.
                num_tok = re.match(r"\s*([\d][\d\.\-/]*)", number_text)
                after = remaining_text[number_start + num_tok.end():][:60] if num_tok else ""
                if not num_tok or not re.search(r"\b1[3-9]\d\d\b", after):
                    return None
                number = num_tok.group(1).rstrip(".-/")
                # position "virtuelle" de l'indicateur : juste après le numéro
                date_indicator_pos = number_start + num_tok.end()
                date_search = None

    if not number_indicator_match:
        # Texte SANS numéro (ex: "قرار لعامل إقليم الناضور بتاريخ ..." --
        # arrêtés de gouverneurs, présidents de conseils...). AVANT, ces
        # textes étaient tous ignorés. On les accepte si une date suit de
        # près le mot-clé ; la vérification Gemma écarte ensuite les faux
        # positifs éventuels.
        date_search = re.search(rf"({date_indicators_pattern})", search_window)
        if not date_search:
            return None
        number = ""
        date_indicator_pos = date_search.start()

    # 3. La date après l'indicateur de date (indicateur vide si perdu par l'OCR)
    date_indicator = date_search.group(1) if date_search else ""
    date_start = date_indicator_pos + len(date_indicator)
    date_text = remaining_text[date_start:].strip()

    # 4. Où s'arrête la date
    date_end_markers_pattern = "|".join(DATE_END_MARKERS)
    end_marker_match = re.search(rf"({date_end_markers_pattern})", date_text)

    if end_marker_match:
        date = date_text[:end_marker_match.start()].strip()
        end_marker = end_marker_match.group(1)
    else:
        date_words = date_text.split()[:NO_DATE_END_MARKER_FALLBACK_WORDS]
        date = " ".join(date_words)
        end_marker = ""

    # La date s'arrête à la parenthèse fermante qui contient l'année
    # grégorienne : "26 صفر 1397 (16 فبراير 1977)". Sans ça, le champ Date
    # débordait sur la suite du titre ("... 1977) تنشر الاتفاقية", "... سيجرى").
    paren_year = re.search(r"\([^()]*\d{4}\s*\)", date)
    if paren_year:
        date = date[:paren_year.end()]

    full_match_start = keyword_start
    full_match_end = keyword_end + date_start + len(date)

    return {
        "full_match": text[full_match_start:full_match_end],
        "keyword": keyword.strip(),
        "number_indicator": number_indicator_match.group(1).strip() if number_indicator_match else "",
        "number": number,
        "date_indicator": date_indicator.strip(),
        "date": date,
        "end_marker": end_marker.strip(),
        "start_position": full_match_start,
        "end_position": full_match_end,
    }


def extract_no_signature_info(
    text: str, keyword: str, keyword_start: int, keyword_end: int
) -> Optional[Dict]:
    """Idem que extract_sequential_info, mais avec fallback pour les textes sans signature."""
    result = extract_sequential_info(text, keyword, keyword_start, keyword_end)
    if result:
        result["has_signature"] = False
        return result

    remaining_text = text[keyword_end:keyword_end + NO_SIGNATURE_FALLBACK_CHARS]
    end_match = re.search(r"[\n:]", remaining_text)
    full_match_end = keyword_end + (end_match.start() if end_match else len(remaining_text))

    return {
        "full_match": text[keyword_start:full_match_end].strip(),
        "keyword": keyword.strip(),
        "has_signature": False,
        "number_indicator": "",
        "number": "",
        "date_indicator": "",
        "date": "",
        "end_marker": "",
        "start_position": keyword_start,
        "end_position": full_match_end,
    }


# Textes publiés en FORME ABRÉGÉE : "بموجب قرار لوزير ... رقم X بتاريخ ..."
# (avis d'enquête publique, fermetures de route...). Ce sont des arrêtés,
# listés comme tels dans le sommaire, mais ils commencent par "بموجب" au lieu
# du mot-clé. Sans l'article "ال" : "بموجب القرار المشار إليه" est une
# simple référence, pas un nouveau texte.
def build_abbreviated_pattern() -> str:
    sorted_keywords = sorted(KEYWORDS, key=len, reverse=True)
    keywords_pattern = "|".join(re.escape(k) for k in sorted_keywords)
    return rf"^بموجب\s+(?P<keyword>{keywords_pattern})(?=\s|$|[،:؛\.\)])"


def extract_start_info(text: str) -> List[Dict]:
    """Parcourt le texte ligne par ligne et détecte tous les débuts de textes juridiques."""
    lines = text.split("\n")
    pattern = build_start_pattern()
    no_sig_pattern = build_no_signature_pattern()
    abbreviated_pattern = build_abbreviated_pattern()
    results = []

    line_start = 0
    for line in lines:
        stripped = line.strip()
        # décalage entre la ligne brute et la ligne strip() (espaces en début de ligne)
        leading_offset = len(line) - len(line.lstrip())

        abbr_match = re.match(abbreviated_pattern, stripped)
        if abbr_match:
            kw_start = line_start + leading_offset  # le document commence à "بموجب"
            kw_end = line_start + leading_offset + abbr_match.end()
            result = extract_sequential_info(text, abbr_match.group("keyword"), kw_start, kw_end)
            if result:
                result["has_signature"] = True   # gardé par le filtre "avec signature"...
                result["abbreviated"] = True     # ...mais traité à part (pas de signature attendue)
                results.append(result)
            line_start += len(line) + 1
            continue

        no_sig_match = re.match(no_sig_pattern, stripped)
        if no_sig_match:
            kw_start = line_start + leading_offset + no_sig_match.start()
            kw_end = line_start + leading_offset + no_sig_match.end()
            result = extract_no_signature_info(text, no_sig_match.group("keyword"), kw_start, kw_end)
            if result:
                results.append(result)
            line_start += len(line) + 1
            continue

        match = re.match(pattern, stripped)
        if match:
            kw_start = line_start + leading_offset + match.start()
            kw_end = line_start + leading_offset + match.end()
            result = extract_sequential_info(text, match.group("keyword"), kw_start, kw_end)
            if result:
                result["has_signature"] = True
                results.append(result)
            line_start += len(line) + 1
            continue

        # Ni match exact avec signature, ni sans signature : on tente un match
        # flou (tolérant 1 caractère) avant d'abandonner cette ligne. Voir
        # find_fuzzy_keyword_match pour la politique de vérification associée.
        fuzzy = find_fuzzy_keyword_match(stripped)
        if fuzzy:
            canonical_kw, matched_len = fuzzy
            kw_start = line_start + leading_offset
            kw_end = line_start + leading_offset + matched_len
            result = extract_sequential_info(text, canonical_kw, kw_start, kw_end)
            if result:
                result["has_signature"] = True
                result["fuzzy_matched"] = True
                result["surface_form"] = stripped[:matched_len]
                results.append(result)

        line_start += len(line) + 1  # +1 pour le \n retiré par split

    return _drop_title_references(text, results)


# Un vrai nouveau texte ne commence qu'une fois le TITRE du texte précédent
# terminé (point final). Si un "début" apparaît à moins de
# TITLE_REFERENCE_MAX_GAP caractères d'un début précédent SANS point final
# entre les deux, c'est un texte CITÉ dans le titre du précédent (ex:
# "قرار ... رقم 144.78 ... يتم بموجبه ⏎ قرار وزير التعليم العالي رقم 385.76 ...").
# Avant ce correctif, la citation volait la signature du vrai texte, qui était
# alors réduit à son titre puis écarté (constaté sur BO_3410).
TITLE_REFERENCE_MAX_GAP = 300
_SENTENCE_END = re.compile(r"\.(?=\s|$)")


def _drop_title_references(text: str, results: List[Dict]) -> List[Dict]:
    kept: List[Dict] = []
    for r in sorted(results, key=lambda x: x["start_position"]):
        # Seul un VRAI titre de texte juridique (mot-clé avec signature, forme
        # complète) peut contenir une citation. Une rubrique ("إعلانات وبلاغات")
        # ou un avis abrégé ne doit pas faire écarter le texte qui le suit
        # (constaté : avis 1378.77 écarté à tort sur BO_3405).
        real_titles = [k for k in kept if k.get("has_signature") and not k.get("abbreviated")]
        if real_titles and not r.get("abbreviated"):
            prev = real_titles[-1]
            gap = r["start_position"] - prev["end_position"]
            between = text[prev["start_position"]:r["start_position"]]
            if 0 <= gap <= TITLE_REFERENCE_MAX_GAP and not _SENTENCE_END.search(between):
                continue  # citation dans le titre du texte précédent
        kept.append(r)
    return kept
