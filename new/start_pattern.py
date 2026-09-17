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
NUMBER_INDICATOR_SEARCH_WINDOW = 80

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

    # 1. Indicateur de numéro (رقم / عدد), cherché seulement dans une fenêtre
    #    proche du mot-clé (voir NUMBER_INDICATOR_SEARCH_WINDOW plus haut).
    number_indicators_pattern = "|".join(NUMBER_INDICATORS)
    search_window = remaining_text[:NUMBER_INDICATOR_SEARCH_WINDOW]
    number_indicator_match = re.search(rf"({number_indicators_pattern})\s+", search_window)
    if not number_indicator_match:
        return None

    # 2. Le numéro lui-même, dans une fenêtre limitée
    number_start = number_indicator_match.end()
    number_text = remaining_text[number_start:number_start + NUMBER_LOOKAHEAD_CHARS]

    if len(re.findall(r"\d", number_text)) < 1:
        # Pas de vrai numéro trouvé après l'indicateur (ex: rencontré dans un
        # tableau ou une phrase descriptive sans référence réelle) -> ce
        # candidat n'est pas un vrai début de texte juridique avec numéro,
        # on l'écarte plutôt que de renvoyer un dict incomplet qui ferait
        # planter le reste du pipeline plus tard.
        return None

    date_indicators_pattern = "|".join(DATE_INDICATORS)
    date_search = re.search(rf"({date_indicators_pattern})", number_text)
    if not date_search:
        return None

    number = number_text[:date_search.start()].strip()
    date_indicator_pos = number_start + date_search.start()

    # 3. La date après l'indicateur de date
    date_indicator = date_search.group(1)
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

    full_match_start = keyword_start
    full_match_end = keyword_end + date_start + len(date)

    return {
        "full_match": text[full_match_start:full_match_end],
        "keyword": keyword.strip(),
        "number_indicator": number_indicator_match.group(1).strip(),
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


def extract_start_info(text: str) -> List[Dict]:
    """Parcourt le texte ligne par ligne et détecte tous les débuts de textes juridiques."""
    lines = text.split("\n")
    pattern = build_start_pattern()
    no_sig_pattern = build_no_signature_pattern()
    results = []

    line_start = 0
    for line in lines:
        stripped = line.strip()
        # décalage entre la ligne brute et la ligne strip() (espaces en début de ligne)
        leading_offset = len(line) - len(line.lstrip())

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

        line_start += len(line) + 1  # +1 pour le \n retiré par split

    return results