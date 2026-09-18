"""
end_pattern.py
--------------
Détection des FINS de textes juridiques (blocs de signature).

Ce fichier changeait peu par rapport à l'original : il ne faisait pas partie
du bricolage `type('Match', ...)` (il utilise déjà re.finditer proprement et
stocke déjà start_position/end_position). On garde donc la logique telle
quelle, avec juste de la documentation en plus pour que ce soit clair pour
la couche de vérification Gemma qui vient se brancher dessus ensuite.

IMPORTANT -- deux limites DIFFÉRENTES et INDÉPENDANTES sont calculées après
une signature :
1. `end_position` du candidat de fin = limite du DOCUMENT ENTIER (utilisée
   par match_patterns_and_extract pour découper le texte juridique complet).
   Recherche NON bornée : un dahir qui publie un traité international en
   annexe peut légitimement s'étendre sur plusieurs pages après la signature
   du dahir lui-même.
2. `names` (le texte affiché dans le champ Names) doit rester COURT -- un nom
   ou une petite liste de noms, pas un traité entier. Calculé séparément,
   avec une fenêtre bornée, sans jamais influencer `end_position`.

DEUX BUGS DE TRONCATURE PRÉMATURÉE CORRIGÉS (trouvés sur BO_3405, dahir
1.76.295 qui publie la convention de La Haye en annexe -- le texte était
coupé en plein article) :

a) Les "caractères spéciaux" (*, =, -, +, #) servent à repérer des séparateurs
   visuels issus de la conversion PDF (ex: une ligne de "***"). Mais un SEUL
   de ces caractères apparaît aussi très normalement dans un texte juridique
   ordinaire -- ex: une liste numérotée "1 - ...", "2 - ..." dans un traité.
   Un seul "-" isolé déclenchait donc une coupure beaucoup trop tôt.
   -> Corrigé : on exige maintenant une SÉQUENCE d'au moins 3 caractères
   spéciaux consécutifs (voir SPECIAL_SEPARATOR_MIN_REPEAT) pour que ce soit
   considéré comme un vrai séparateur visuel.

b) Le pipeline insère lui-même des marqueurs '=== Page N ===' entre les pages
   (voir jsonl_adapter.py / arabic_legal_extractor.py). Ces marqueurs
   contiennent "===", qui matche exactement le motif de séparateur visuel
   décrit ci-dessus -- un document dont la signature tombe juste avant un
   saut de page se faisait donc couper immédiatement à CE marqueur, qui n'a
   pourtant rien à voir avec le contenu du document.
   -> Corrigé : les correspondances qui font partie d'un marqueur de page
   inséré par le pipeline sont explicitement ignorées (voir _skip_page_markers).
"""

import re
from typing import Dict, Optional, List, Tuple
from start_pattern import KEYWORDS

SIGNATURE_INDICATORS = ["وحرر", "وحــرر"]

SIGNATURE_KEYWORDS_TYPE1 = ["وقعه بالعطف", "الإمضاء", "إمضاء", "امضاء", "الامضاء"]
SIGNATURE_KEYWORDS_TYPE2 = ["الإمضاءات", "الامضاءات"]

SIGNATURE_LIMIT_KEYWORDS = KEYWORDS

# Mots qui introduisent un texte ANNEXÉ (traité, convention international...)
# publié à la suite d'un dahir/décret. Ce texte annexé n'est ni un vrai début
# de texte juridique marocain (pas dans KEYWORDS), ni quelque chose qu'on
# veut inclure dans le document du dahir qui le publie -- il doit simplement
# marquer la fin du dahir. Constaté sur BO_3405 : un dahir publiant la
# Convention de Montréal ("اتفاقية قمع جرائم...") ou celle de La Haye
# ("معاهدة قمع الاستيلاء...") en annexe voyait son texte s'étendre pour
# inclure toute l'annexe, ce qui n'est pas voulu.
ANNEX_STOP_WORDS = ["اتفاقية", "معاهدة", "بروتوكول", "ميثاق"]

# En-têtes de section/ministère qui introduisent le décret SUIVANT dans une
# série organisée par ministère (ex: "نصوص خاصة" -> "وزارة الدولة المكلفة
# بـ...\n\nمرسوم رقم..."). Constaté sur BO_3405 : une série de décrets
# consécutifs (2.77.790 à 2.77.797) laissait échapper l'en-tête du ministère
# suivant dans le texte du décret précédent, faute de mot-clé juridique
# immédiatement après leurs deux co-signatures habituelles.
SECTION_HEADER_STOP_WORDS = ["وزارة", "الإدارة العامة"]

# Combine les deux pour la recherche de fin de document (pas pour la
# détection de début dans start_pattern.py : on ne veut pas extraire ces
# annexes comme leurs propres textes juridiques, juste s'arrêter avant).
DOCUMENT_LIMIT_KEYWORDS = SIGNATURE_LIMIT_KEYWORDS + ANNEX_STOP_WORDS + SECTION_HEADER_STOP_WORDS

# L'en-tête du Bulletin Officiel lui-même ("الجريدة الرسمية" suivi de
# "عدد <numéro>") apparaît en haut de CHAQUE page réelle du document source
# (indépendamment de nos propres marqueurs '=== Page N ==='). C'est un
# signal de fin de document très fiable : constaté sur BO_3405, plusieurs
# textes se terminant juste avant un saut de page laissaient échapper cet
# en-tête (et parfois le début du texte suivant) dans leur legal_text, faute
# de mot-clé juridique immédiatement après leur signature.
_BO_HEADER_PATTERN = re.compile(r"الجريدة\s+الرسمية\s*\n+\s*عدد\s+\d+")

# Caractères considérés comme séparateurs visuels quand ils se répètent (voir
# SPECIAL_SEPARATOR_MIN_REPEAT) -- pas quand ils apparaissent isolément.
SIGNATURE_LIMIT_SPECIALCHARS = "*=\\-+#"
SPECIAL_SEPARATOR_MIN_REPEAT = 3
_SPECIAL_SEPARATOR_PATTERN = rf"[{SIGNATURE_LIMIT_SPECIALCHARS}]{{{SPECIAL_SEPARATOR_MIN_REPEAT},}}"

# Marqueur de page inséré par le pipeline lui-même (jsonl_adapter.py,
# arabic_legal_extractor.py) -- jamais un vrai séparateur de contenu.
_PAGE_MARKER_PATTERN = re.compile(r"===\s*Page\s*\d+\s*===")

# Fenêtre bornée utilisée UNIQUEMENT pour délimiter le champ d'affichage
# 'names' (jamais pour end_position -- voir note en tête de fichier).
MAX_NAMES_SEARCH_CHARS = 500


def extract_signatures_from_text(text: str) -> List[Dict]:
    """Extrait tous les blocs de signature (Type 1 : un signataire, Type 2 : plusieurs)."""
    results = []

    pattern_type1 = rf"({'|'.join(SIGNATURE_INDICATORS)}).*?({'|'.join(SIGNATURE_KEYWORDS_TYPE1)})\s*:?\s*"
    for match in re.finditer(pattern_type1, text, re.DOTALL):
        indicator = match.group(1)
        keyword = match.group(2)
        names_start = match.end()

        doc_limit_pos, doc_limit_val = find_document_limit(text, names_start)
        names_display_pos, _ = find_names_display_limit(text, names_start)
        names_block = text[names_start:names_display_pos].strip() if names_display_pos else text[names_start:].strip()

        results.append({
            "type": "Type 1",
            "signature_indicator": indicator or "",
            "key_signature": keyword,
            "names": names_block,
            "limit": doc_limit_val or "",
            "start_position": match.start(),
            "end_position": doc_limit_pos if doc_limit_pos is not None else len(text),
        })

    pattern_type2 = rf"({'|'.join(SIGNATURE_KEYWORDS_TYPE2)})\s*:?\s*"
    for match in re.finditer(pattern_type2, text, re.DOTALL):
        keyword = match.group(1)
        names_start = match.end()

        doc_limit_pos, doc_limit_val = find_document_limit(text, names_start)
        names_display_pos, _ = find_names_display_limit(text, names_start)
        names_block = text[names_start:names_display_pos].strip() if names_display_pos else text[names_start:].strip()

        results.append({
            "type": "Type 2",
            "signature_indicator": "",
            "key_signature": keyword,
            "names": names_block,
            "limit": doc_limit_val or "",
            "start_position": match.start(),
            "end_position": doc_limit_pos if doc_limit_pos is not None else len(text),
        })

    return results


def _find_special_separator(text: str, search_start: int, search_end: Optional[int] = None):
    """
    Cherche la prochaine séquence de séparateur visuel (3+ caractères spéciaux
    consécutifs) à partir de search_start, en ignorant celles qui font partie
    d'un marqueur de page inséré par le pipeline ('=== Page N ==='). Renvoie
    (position_absolue, texte_matché) ou None si rien trouvé dans la zone.
    """
    zone = text[search_start:search_end] if search_end is not None else text[search_start:]
    pos = 0
    while True:
        m = re.search(_SPECIAL_SEPARATOR_PATTERN, zone[pos:])
        if not m:
            return None
        abs_start_in_zone = pos + m.start()
        # Contexte élargi autour du match pour vérifier si c'est un marqueur de page
        context_start = max(0, abs_start_in_zone - 15)
        context = zone[context_start:abs_start_in_zone + len(m.group(0)) + 15]
        if _PAGE_MARKER_PATTERN.search(context):
            pos = abs_start_in_zone + len(m.group(0))
            continue
        return search_start + abs_start_in_zone, m.group(0)


def find_document_limit(text: str, start_pos: int) -> Tuple[Optional[int], Optional[str]]:
    """
    Cherche où s'arrête le DOCUMENT ENTIER après une signature : le prochain
    mot-clé juridique OU le début d'un texte annexé (voir ANNEX_STOP_WORDS),
    ou un vrai séparateur visuel (3+ caractères spéciaux, en ignorant les
    marqueurs de page du pipeline). Recherche NON BORNÉE volontairement pour
    les mots-clés/annexes : rien n'empêche un très long texte juridique
    normal, donc on ne borne pas cette recherche par une distance fixe --
    seuls des marqueurs de contenu réels (mot-clé, annexe, séparateur) la
    terminent.
    """
    candidates = []

    keyword_pattern = rf"^(?P<limit>{'|'.join(DOCUMENT_LIMIT_KEYWORDS)})(?=\s|$|[،:؛\.\)])"
    m1 = re.search(keyword_pattern, text[start_pos:], flags=re.MULTILINE)
    if m1:
        candidates.append((start_pos + m1.start(), m1.group(1)))

    special = _find_special_separator(text, start_pos)
    if special:
        candidates.append(special)

    bo_header_match = _BO_HEADER_PATTERN.search(text[start_pos:])
    if bo_header_match:
        candidates.append((start_pos + bo_header_match.start(), "(en-tête du BO)"))

    if candidates:
        return min(candidates, key=lambda x: x[0])
    return None, None


def find_names_display_limit(text: str, start_pos: int) -> Tuple[Optional[int], Optional[str]]:
    """
    Cherche où s'arrête le texte à afficher dans le champ 'names' -- toujours
    court. Totalement indépendant de find_document_limit : ne détermine
    JAMAIS end_position, seulement ce qui est montré dans le champ Names.
    Bornée à MAX_NAMES_SEARCH_CHARS, avec la première ligne vide ET le
    premier marqueur de page ('=== Page N ===') comme signaux d'arrêt --
    contrairement à find_document_limit, qui doit au contraire les ignorer
    pour ne pas tronquer un texte annexé. Un marqueur de page juste après un
    nom (même sans ligne vide avant) marque presque toujours la fin réelle
    du bloc de signature (constaté sur BO_3405 : 'names' débordait jusque
    dans l'en-tête de la page suivante quand un seul \\n séparait le nom du
    marqueur de page).
    """
    search_end = start_pos + MAX_NAMES_SEARCH_CHARS
    search_zone = text[start_pos:search_end]
    candidates = []

    keyword_pattern = rf"^(?P<limit>{'|'.join(SIGNATURE_LIMIT_KEYWORDS)})(?=\s|$|[،:؛\.\)])"
    m1 = re.search(keyword_pattern, search_zone, flags=re.MULTILINE)
    if m1:
        candidates.append((start_pos + m1.start(), m1.group(1)))

    special = _find_special_separator(text, start_pos, search_end)
    if special:
        candidates.append(special)

    blank_line_match = re.search(r"\n[ \t]*\n", search_zone)
    if blank_line_match:
        candidates.append((start_pos + blank_line_match.start(), "(ligne vide)"))

    page_marker_match = _PAGE_MARKER_PATTERN.search(search_zone)
    if page_marker_match:
        candidates.append((start_pos + page_marker_match.start(), "(marqueur de page)"))

    bo_header_match = _BO_HEADER_PATTERN.search(search_zone)
    if bo_header_match:
        candidates.append((start_pos + bo_header_match.start(), "(en-tête du BO)"))

    if candidates:
        return min(candidates, key=lambda x: x[0])

    return start_pos + MAX_NAMES_SEARCH_CHARS, "(limite par défaut)"