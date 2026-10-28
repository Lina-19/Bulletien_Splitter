"""
gemma_start_detector.py
-----------------------
Détection HYBRIDE des débuts de textes juridiques.

Les regex (start_pattern.py) restent la détection principale : rapides,
déterministes, ~95 % de couverture mesurée. Gemma intervient EN COMPLÉMENT :
il lit chaque page et liste les titres de textes juridiques qu'il y voit.
Tout titre qu'il trouve et que les regex ont raté est ajouté comme début
supplémentaire. Objectif : ne pas rater un texte important dont le format
n'a pas été prévu (autres années du BO, OCR très abîmé, formulation inédite).

Garde-fous -- un LLM peut inventer ou se tromper de ligne. Un titre proposé
par Gemma n'est retenu QUE si :
  1. la ligne existe réellement dans la page (recherche tolérante aux
     espaces, jamais de position "devinée") ;
  2. aucun début déjà trouvé par les regex n'est au même endroit ;
  3. ce n'est pas une citation (ligne commençant par بناء على / وعلى / بمقتضى...) ;
  4. une année (13xx/14xx hégirienne ou 19xx/20xx) suit de près -- tout
     texte juridique est daté.
Si Gemma ne répond pas ou répond n'importe quoi, rien n'est ajouté : le
résultat est alors exactement celui des regex seules.
"""

import re
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from gemma_client import call_gemma, extract_json_object, GemmaClientError
from start_pattern import (KEYWORDS, extract_sequential_info, find_fuzzy_keyword_match,
                           TITLE_REFERENCE_MAX_GAP, _SENTENCE_END)

MAX_PARALLEL_CALLS = 5
MAX_PAGE_CHARS = 12000          # une page de BO fait ~4 000 caractères
DUPLICATE_DISTANCE = 80         # un début regex à moins de 80 car. = déjà trouvé
YEAR_WINDOW = 300               # l'année doit apparaître dans ces 300 caractères
MATCH_PREFIX_CHARS = 30         # caractères comparés pour retrouver la ligne
MATCH_MIN_SIMILARITY = 0.85     # tolérance si Gemma "corrige" l'OCR en recopiant

# Une page sans AUCUN de ces mots ne peut pas contenir de début de texte :
# inutile de l'envoyer à Gemma (tableaux, annonces...).
_PAGE_PREFILTER = re.compile(r"قرار|مرسوم|ظهير|ظهر|مقرر|قانون|منشور|مذكرة|بموجب")

_CITATION_PREFIXES = re.compile(r"^\s*(?:و?بناء\s+على|وعلى|و?بمقتضى|وبعد|طبقا|تطبيقا|حسب)")
_YEAR = re.compile(r"\b(?:1[34]\d\d|19\d\d|20\d\d)\b")
_KEYWORD_AT_START = re.compile(
    rf"^\s*(?:بموجب\s+)?(?P<kw>{'|'.join(sorted(KEYWORDS, key=len, reverse=True))})(?=\s|$|[،:؛\.\)])"
)
_PAGE_MARKER = re.compile(r"===\s*Page\s*(\d+)\s*===")

# --- Garde-fou "structure de titre" (le plus important) ---
# Un titre proposé par Gemma n'est retenu que s'il RESSEMBLE à un titre :
#  a) premier mot proche d'un mot-clé (seuil calibré : la déformation OCR
#     "مرصدم" pour "مرسوم" est à 0,60) ;
#  b) jamais un mot avec l'article "ال" ("القرار", "المرسوم" = référence à un
#     texte déjà cité) ni un verbe ("يقرر", "قرر", "يرسم"), qui dépassent
#     pourtant ce seuil ;
#  c) juste après : "رقم"/"عدد" + chiffres, ou un indicateur de date.
# Sans ce garde-fou, des lignes quelconques du corps signalées par erreur
# devenaient des débuts parasites (test E du banc d'essai).
TITLE_WORD_MIN_SIMILARITY = 0.6
_VERB_BLACKLIST = {"يقرر", "قرر", "تقرر", "يرسم", "رسم", "يقر", "أقر", "اقر"}
_TITLE_STRUCTURE = re.compile(r"(?:رقم|عدد)\s*\d|بتاريخ|صادر\s*في|صادرة\s*في|المؤرخ")
TITLE_STRUCTURE_WINDOW = 200
_KEYWORD_FIRST_WORDS = sorted({k.split()[0] for k in KEYWORDS})


def _first_word_is_keyword_like(line: str) -> bool:
    # Les dahirs anciens sont précédés de "الحمد لله وحده" — c'est une
    # formule connue et fiable, pas un mot-clé générique à scorer.
    if re.match(r"^\s*الحمد\s+لله\s+وحده", line):
        return True
    words = line.split()
    if words and words[0] == "بموجب":
        words = words[1:]
    if not words:
        return False
    w = re.sub(r"[^\u0600-\u06FF]", "", words[0])
    if not w or w in _VERB_BLACKLIST or w.startswith("ال"):
        return False
    return max(SequenceMatcher(None, w, k).ratio() for k in _KEYWORD_FIRST_WORDS) >= TITLE_WORD_MIN_SIMILARITY

DETECTION_PROMPT = """أنت مساعد متخصص في تحليل الجريدة الرسمية المغربية بجميع حقبها (من عهد الحماية إلى اليوم).

فيما يلي نص صفحة واحدة من الجريدة الرسمية (مستخرج بالتعرف الضوئي، وقد يحتوي أخطاء).

المهمة: استخرج عنوان كل نص قانوني يبدأ في هذه الصفحة.

أنواع النصوص القانونية الحديثة (بعد 1956):
ظهير شريف، ظهير، قانون، مرسوم، قرار، قرار مشترك، مقرر، منشور، مذكرة

أنواع النصوص القانونية القديمة (عهد الحماية، قبل 1956) — مهم جداً:
- ظهير شريف بدون رقم ولا تاريخ في العنوان، يسبقه عادةً "الحمد لله وحده"
  مثال: "الحمد لله وحده\nظهير شريف\nفي الإذن بجعل حسابات..."
- قرار وزيري (بدلاً من "قرار" المعتاد)
  مثال: "قرار وزيري في المصادقة على..."
- ظهير شريف مسبوق بـ "الحمد لله وحده" مباشرة بدون نص بينهما

علامات بداية النص القانوني القديم:
- السطر "الحمد لله وحده" يعني أن ظهيراً شريفاً يبدأ بعده مباشرة
- العبارة "يعلم من كتابنا هذا أسماه الله..." تعني بداية ظهير

لا تستخرج:
- عناوين الفهرست (جدول المحتويات في بداية العدد)
- الإحالات إلى نصوص أخرى داخل التأشيرات ("بناء على الظهير..."، "وعلى المرسوم...")
- نصاً مذكوراً داخل عنوان نص آخر
- الإعلانات والبلاغات العادية

لكل نص: انسخ السطر الأول من عنوانه حرفيا، حرفا بحرف، كما هو مكتوب في
الصفحة (حتى لو كانت فيه أخطاء). إذا كان عنوانه مسبوقاً بـ"الحمد لله وحده"،
ابدأ النسخ من هذه العبارة.

نص الصفحة:
---
{page}
---

أجب حصريا بكائن JSON واحد بدون أي شرح وبدون Markdown:
{{"titles": [{{"first_line": "السطر الأول حرفيا", "type": "قرار"}}]}}
وإذا لم يبدأ أي نص قانوني في هذه الصفحة: {{"titles": []}}
"""


def _normalize(s: str) -> str:
    s = s.replace("ـ", "")                       # tatweel
    s = re.sub(r"[#\*>\|]", " ", s)              # restes de markdown
    return re.sub(r"\s+", " ", s).strip()


def _page_segments(content: str, page_positions: List[Dict]) -> List[Tuple[int, int, int]]:
    """(numéro de page interne, début, fin) de chaque page dans content."""
    segs = []
    for i, p in enumerate(page_positions):
        end = page_positions[i + 1]["position"] if i + 1 < len(page_positions) else len(content)
        segs.append((p["page_number"], p["position"], end))
    return segs


def _locate_line(content: str, seg_start: int, seg_end: int, first_line: str) -> Optional[int]:
    """
    Position (dans content) de la ligne dont le début correspond à first_line.
    Compare les MATCH_PREFIX_CHARS premiers caractères normalisés. Renvoie
    None si la ligne n'existe pas dans la page (titre inventé par Gemma).
    """
    target = _normalize(first_line)[:MATCH_PREFIX_CHARS]
    if len(target) < 8:
        return None
    lines = []
    pos = seg_start
    for line in content[seg_start:seg_end].split("\n"):
        lines.append((pos + (len(line) - len(line.lstrip())), _normalize(line)[:len(target)]))
        pos += len(line) + 1
    for p, norm in lines:                       # 1) correspondance exacte
        if norm == target:
            return p
    best_p, best_r = None, 0.0                  # 2) tolérante : Gemma a pu "corriger" l'OCR
    for p, norm in lines:
        if len(norm) >= 8:
            r = SequenceMatcher(None, norm, target).ratio()
            if r > best_r:
                best_p, best_r = p, r
    return best_p if best_r >= MATCH_MIN_SIMILARITY else None


def _build_candidate(content: str, pos: int, gemma_type: str) -> Optional[Dict]:
    line_end = content.find("\n", pos)
    line = content[pos:line_end if line_end != -1 else len(content)]

    is_old_dahir = bool(re.match(r"^\s*الحمد\s+لله\s+وحده", line))

    if _CITATION_PREFIXES.match(line):
        return None                                  # garde-fou 3 : citation
    if not is_old_dahir and not _YEAR.search(content[pos:pos + YEAR_WINDOW]):
        return None                                  # garde-fou 4 : pas de date
    if not _first_word_is_keyword_like(line):
        return None                                  # garde-fou 5 : premier mot
    if not is_old_dahir and not _TITLE_STRUCTURE.search(content[pos:pos + TITLE_STRUCTURE_WINDOW]):
        return None                                  # garde-fou 6 : structure de titre

    abbreviated = line.lstrip().startswith("بموجب")
    m = _KEYWORD_AT_START.match(line)
    if m:
        keyword, kw_end = m.group("kw"), pos + m.end()
    else:
        fuzzy = find_fuzzy_keyword_match(line.strip())
        if fuzzy:
            keyword, kw_end = fuzzy[0], pos + len(line) - len(line.lstrip()) + fuzzy[1]
        else:
            # Mot-clé illisible à l'OCR : on se fie au type annoncé par Gemma
            keyword = gemma_type if gemma_type in KEYWORDS else "قرار"
            first_word = re.match(r"\s*\S+", line)
            kw_end = pos + (first_word.end() if first_word else 0)

    info = extract_sequential_info(content, keyword, pos, kw_end)
    if not info:
        # Pas de numéro/date au format attendu : on garde le début quand même,
        # c'est précisément le genre de texte que les regex ratent.
        info = {"full_match": line.strip(), "keyword": keyword, "number_indicator": "",
                "number": "", "date_indicator": "", "date": "", "end_marker": "",
                "start_position": pos, "end_position": pos + len(line)}
    info["start_position"] = pos
    info["has_signature"] = True
    info["abbreviated"] = abbreviated
    info["source"] = "gemma"
    return info


def _is_title_citation(content: str, pos: int, known_titles: List[Dict]) -> bool:
    """Même règle que start_pattern._drop_title_references : un début qui suit
    de près un vrai titre SANS point final entre les deux est une citation."""
    before = [t for t in known_titles if t["start_position"] < pos]
    if not before:
        return False
    prev = max(before, key=lambda t: t["start_position"])
    gap = pos - prev["end_position"]
    return 0 <= gap <= TITLE_REFERENCE_MAX_GAP and not _SENTENCE_END.search(content[prev["start_position"]:pos])


def _ask_page(page_text: str) -> List[Dict]:
    raw = call_gemma([{"role": "user", "content": DETECTION_PROMPT.format(page=page_text[:MAX_PAGE_CHARS])}],
                     max_tokens=800)
    titles = extract_json_object(raw).get("titles", [])
    return [t for t in titles if isinstance(t, dict) and t.get("first_line")]


def detect_missed_starts(content: str, page_positions: List[Dict],
                         regex_starts: List[Dict],
                         protected_spans: Optional[List[Tuple[int, int]]] = None) -> List[Dict]:
    """
    Interroge Gemma page par page (en parallèle) et renvoie les débuts de
    textes qu'il a trouvés ET que les regex avaient ratés, après garde-fous.

    protected_spans : zones des textes SIGNÉS déjà extraits par les regex. Un
    début proposé à l'intérieur est rejeté : un faux titre au milieu d'un
    texte signé lui volerait sa signature et le tronquerait (même famille de
    régression que "يقرر" pris pour "مقرر").
    """
    protected_spans = protected_spans or []
    segments = [sg for sg in _page_segments(content, page_positions)
                if _PAGE_PREFILTER.search(content[sg[1]:sg[2]])]
    if not segments:
        return []
    known = [s["start_position"] for s in regex_starts if s.get("start_position") is not None]

    print(f"   🤖 Détection Gemma page par page ({len(segments)} pages, parallèle x{MAX_PARALLEL_CALLS})...")
    answers: Dict[int, List[Dict]] = {}
    failures = 0
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CALLS) as ex:
        futures = {ex.submit(_ask_page, content[s:e]): (pn, s, e) for pn, s, e in segments}
        for fut in as_completed(futures):
            pn, s, e = futures[fut]
            try:
                answers[pn] = fut.result()
            except (GemmaClientError, ValueError):
                failures += 1

    added: List[Dict] = []
    known_titles = [r for r in regex_starts if r.get("has_signature") and not r.get("abbreviated")
                    and r.get("start_position") is not None]
    rejected = {"introuvable": 0, "déjà trouvé": 0, "garde-fou": 0,
                "dans un texte signé": 0, "citation de titre": 0}
    for pn, s, e in segments:
        for t in answers.get(pn, []):
            pos = _locate_line(content, s, e, t["first_line"])
            if pos is None:
                rejected["introuvable"] += 1
                continue
            if any(abs(pos - k) <= DUPLICATE_DISTANCE for k in known):
                rejected["déjà trouvé"] += 1
                continue
            if any(a <= pos < b for a, b in protected_spans):
                rejected["dans un texte signé"] += 1
                continue
            cand = _build_candidate(content, pos, str(t.get("type", "")))
            if cand is None:
                rejected["garde-fou"] += 1
                continue
            if not cand["abbreviated"] and _is_title_citation(content, pos, known_titles):
                rejected["citation de titre"] += 1
                continue
            known.append(pos)
            if not cand["abbreviated"]:
                known_titles.append(cand)
            added.append(cand)

    print(f"   🤖 Gemma : {len(added)} début(s) supplémentaire(s) ajouté(s) "
          f"| écartés : {rejected} | pages en échec : {failures}")
    return added