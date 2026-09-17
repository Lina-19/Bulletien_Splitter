"""
end_pattern.py
--------------
Détection des FINS de textes juridiques (blocs de signature).

Ce fichier changeait peu par rapport à l'original : il ne faisait pas partie
du bricolage `type('Match', ...)` (il utilise déjà re.finditer proprement et
stocke déjà start_position/end_position). On garde donc la logique telle
quelle, avec juste de la documentation en plus pour que ce soit clair pour
la couche de vérification Gemma qui vient se brancher dessus ensuite.
"""

import re
from typing import Dict, Optional, List, Tuple
from start_pattern import KEYWORDS

SIGNATURE_INDICATORS = ["وحرر", "وحــرر"]

SIGNATURE_KEYWORDS_TYPE1 = ["وقعه بالعطف", "الإمضاء", "إمضاء", "امضاء", "الامضاء"]
SIGNATURE_KEYWORDS_TYPE2 = ["الإمضاءات", "الامضاءات"]

SIGNATURE_LIMIT_KEYWORDS = KEYWORDS
# NB: ces caractères sont déjà échappés correctement pour être utilisés tels
# quels dans une classe de caractères / alternance regex.
SIGNATURE_LIMIT_SPECIALCHARS = [r"\*", "=", "-", r"\+", "#"]


def extract_signatures_from_text(text: str) -> List[Dict]:
    """Extrait tous les blocs de signature (Type 1 : un signataire, Type 2 : plusieurs)."""
    results = []

    # Type 1 : "وحرر ... الإمضاء" (le .*? avec DOTALL peut traverser plusieurs
    # lignes/paragraphes -- à surveiller si un document a une longue annexe
    # entre les deux, ça peut capturer plus que prévu).
    pattern_type1 = rf"({'|'.join(SIGNATURE_INDICATORS)}).*?({'|'.join(SIGNATURE_KEYWORDS_TYPE1)})\s*:?\s*"
    for match in re.finditer(pattern_type1, text, re.DOTALL):
        indicator = match.group(1)
        keyword = match.group(2)
        names_start = match.end()

        limit_pos, limit_val = find_limit(text, names_start)
        names_block = text[names_start:limit_pos].strip() if limit_pos else text[names_start:].strip()

        results.append({
            "type": "Type 1",
            "signature_indicator": indicator or "",
            "key_signature": keyword,
            "names": names_block,
            "limit": limit_val or "",
            "start_position": match.start(),
            "end_position": limit_pos or len(text),
        })

    # Type 2 : "الإمضاءات" (pluriel)
    pattern_type2 = rf"({'|'.join(SIGNATURE_KEYWORDS_TYPE2)})\s*:?\s*"
    for match in re.finditer(pattern_type2, text, re.DOTALL):
        keyword = match.group(1)
        names_start = match.end()

        limit_pos, limit_val = find_limit(text, names_start)
        names_block = text[names_start:limit_pos].strip() if limit_pos else text[names_start:].strip()

        results.append({
            "type": "Type 2",
            "signature_indicator": "",
            "key_signature": keyword,
            "names": names_block,
            "limit": limit_val or "",
            "start_position": match.start(),
            "end_position": limit_pos or len(text),
        })

    return results


def find_limit(text: str, start_pos: int) -> Tuple[Optional[int], Optional[str]]:
    """
    Cherche où s'arrête le bloc de noms après une signature : soit le prochain
    mot-clé juridique (nouveau texte qui commence), soit un caractère spécial
    (souvent un séparateur visuel introduit par la conversion PDF -> texte).
    Renvoie la limite la plus proche des deux.
    """
    candidates = []

    keyword_pattern = rf"^(?P<limit>{'|'.join(SIGNATURE_LIMIT_KEYWORDS)})(?=\s|$|[،:؛\.\)])"
    m1 = re.search(keyword_pattern, text[start_pos:], flags=re.MULTILINE)
    if m1:
        candidates.append((start_pos + m1.start(), m1.group(1)))

    special_pattern = rf"({'|'.join(SIGNATURE_LIMIT_SPECIALCHARS)})"
    m2 = re.search(special_pattern, text[start_pos:])
    if m2:
        candidates.append((start_pos + m2.start(), m2.group(1)))

    if candidates:
        return min(candidates, key=lambda x: x[0])

    return None, None
