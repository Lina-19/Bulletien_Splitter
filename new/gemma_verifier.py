"""
gemma_verifier.py
------------------
Vérifie les candidats détectés par regex (start_pattern.py / end_pattern.py)
en demandant à Gemma de confirmer, avec le contexte autour, si c'est
vraiment un début/une fin de texte juridique ou un faux positif
(exemple concret rencontré : une entrée de sommaire/فهرست qui répète le
mot-clé et le numéro d'un texte réel, mais qui n'en est pas le vrai début).

Principe : le regex reste la première passe (rapide, gratuite). Gemma ne sert
qu'à FILTRER les candidats déjà trouvés -- il ne cherche pas lui-même les
débuts/fins depuis zéro (plus lent et plus cher que nécessaire pour un
document aussi structuré qu'un Bulletin Officiel).

Deux politiques de confiance différentes selon le type de candidat :
- Candidat normal (match exact d'un mot-clé) : fail-OPEN. Si Gemma échoue
  (timeout, erreur API, JSON invalide), on garde le candidat plutôt que de le
  supprimer silencieusement -- mieux vaut un faux positif occasionnel qu'un
  vrai texte juridique perdu parce que l'API était indisponible.
- Candidat flou (fuzzy_matched=True, voir start_pattern.py) : fail-CLOSED.
  Ces candidats viennent d'un match approximatif (tolérant une faute d'OCR)
  et sont plus susceptibles d'être des faux positifs qu'un match exact. On ne
  les garde QUE si Gemma les confirme explicitement (gemma_verified is True) ;
  en cas d'échec de vérification ou si Gemma n'est pas utilisé du tout, ils
  sont écartés.

Ce module fait aussi du nettoyage sémantique : si le champ 'names' d'une
signature semble anormalement long (voir NAMES_SUSPICIOUS_LENGTH), c'est
probablement le signe qu'il a avalé du texte qui ne lui appartient pas (ex:
un traité annexé sans mot-clé ni caractère spécial proche -- constaté sur
BO_3405). Plutôt que de dépendre uniquement d'heuristiques regex (ligne vide,
etc.) qui peuvent rater d'autres cas dans d'autres fichiers, on demande à
Gemma d'extraire directement le(s) nom(s) réel(s) à partir du contexte.
"""

from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from gemma_client import call_gemma, extract_json_object, GemmaClientError

CONTEXT_CHARS_BEFORE = 250
CONTEXT_CHARS_AFTER = 250

# Nombre d'appels Gemma en parallèle. Les appels sont uniquement I/O-bound
# (attente réseau), donc des threads suffisent -- pas besoin de multiprocessing.
# 5 est un point de départ raisonnable pour ne pas surcharger un endpoint
# interne partagé ; à ajuster selon ce que l'infra encaisse.
MAX_PARALLEL_CALLS = 5

# Au-delà de cette longueur, un champ 'names' est très probablement pollué
# par du texte qui n'a rien à voir avec un nom de signataire -- un nom ou une
# courte liste de noms tient normalement en quelques dizaines de caractères.
NAMES_SUSPICIOUS_LENGTH = 150

# Fenêtre (en caractères) prise à la fin d'un texte juridique extrait pour le
# nettoyage final (voir clean_document_trailing_content). Assez large pour
# couvrir une signature complète + un éventuel début de section suivante,
# sans envoyer tout le document à chaque appel.
TRAILING_CONTEXT_CHARS = 700


def _get_context(full_text: str, start: int, end: int) -> Dict[str, str]:
    before = full_text[max(0, start - CONTEXT_CHARS_BEFORE):start]
    after = full_text[end:end + CONTEXT_CHARS_AFTER]
    return {"before": before, "after": after}


START_VERIFICATION_PROMPT = """أنت مساعد متخصص في تحليل الجريدة الرسمية المغربية، وتعرف جيدا المصطلحات
القانونية المغربية حتى عندما يشوهها التعرف الضوئي على الحروف (OCR).

أنواع النصوص القانونية المرجعية (الشكل الصحيح) هي:
ظهير شريف - ظهير - قرار - قرار مشترك - قرار تأديبي - مرسوم - قانون - منشور - مذكرة - مقرر

مهمتك لها جزءان:

1) تحديد ما إذا كان "المقطع المرشح" أدناه هو فعلاً بداية حقيقية لنص قانوني
رسمي، أم أنه مجرد ذكر لهذا النص في مكان آخر:
- ضمن فهرست / جدول محتويات في بداية العدد
- ضمن إحالة داخل نص آخر ("بناء على الظهير رقم...")
- ملخص أو عنوان متكرر

مؤشرات على أنه ليس بداية حقيقية:
- النص الذي يسبقه يذكر "فهرست" أو يحتوي قائمة عناوين متتالية شبيهة
- ينتهي بشكل مفاجئ برقم يشبه رقم صفحة
- ما يتبعه لا يشبه بداية مقتضيات قانونية (فصول، مواد) بل ينتقل مباشرة لعنوان آخر مختلف تماما

2) إذا كان بداية حقيقية: حدد أي نوع من القائمة المرجعية أعلاه يطابقه، حتى لو
كانت الكلمة في "المقطع المرشح" مشوهة بسبب خطأ تعرف ضوئي (مثلا "ظهر شريف"
بدون الياء يعني في الواقع "ظهير شريف" -- استنتج ذلك من السياق: رقم + تاريخ +
أسلوب الصياغة القانونية، وليس فقط من شكل الكلمة نفسها). أرجع الشكل الصحيح من
القائمة المرجعية في corrected_keyword، حتى إذا كان مطابقا تماما لما كان مكتوبا.

النص قبل المقطع المرشح:
---
{before}
---

المقطع المرشح:
---
{candidate}
---

النص بعد المقطع المرشح:
---
{after}
---

أجب حصرياً بكائن JSON واحد بدون أي شرح إضافي وبدون Markdown، بهذا الشكل بالضبط:
{{"is_valid_start": true, "corrected_keyword": "ظهير شريف", "confidence": 0.9, "reason": "شرح قصير جدا بالعربية"}}
"""

END_VERIFICATION_PROMPT = """أنت مساعد متخصص في تحليل الجريدة الرسمية المغربية.

مهمتك: تحديد ما إذا كان "مقطع التوقيع" أدناه هو فعلاً نهاية حقيقية لنص قانوني
(توقيع رسمي حقيقي يختم نصا قانونيا)، أم أنه إشارة زائفة (مثلا داخل فهرست،
أو جزء من اقتباس لنص آخر، أو تكرار).

النص قبل مقطع التوقيع:
---
{before}
---

مقطع التوقيع المرشح:
---
{candidate}
---

النص بعد مقطع التوقيع:
---
{after}
---

أجب حصرياً بكائن JSON واحد بدون أي شرح إضافي وبدون Markdown، بهذا الشكل بالضبط:
{{"is_valid_end": true, "confidence": 0.9, "reason": "شرح قصير جدا بالعربية"}}
"""

NAMES_CLEANUP_PROMPT = """أنت مساعد متخصص في تحليل الجريدة الرسمية المغربية.

النص التالي تم استخراجه آليا كـ"اسم الموقع" بعد عبارة توقيع رسمي (مثل
"الإمضاء :" أو "الإمضاءات"). المشكلة: أداة الاستخراج الآلي قد تكون أخطأت
وأضافت نصا لا علاقة له بالتوقيع (مثل بداية معاهدة ملحقة، أو نص قانوني آخر)
لأنها لم تجد علامة توقف واضحة قريبة.

استخرج فقط الاسم/الأسماء الحقيقية للموقع(ين) الرسمي(ين)، بدون أي نص إضافي.
إذا كان هناك عدة أسماء، افصل بينها بفاصلة.

النص المستخرج آليا (قد يكون طويلا جدا إذا كان ملوثا):
---
{raw_names}
---

أجب حصريا بكائن JSON واحد بدون أي شرح إضافي وبدون Markdown، بهذا الشكل بالضبط:
{{"clean_names": "الاسم الحقيقي هنا", "was_polluted": true}}
"""


def verify_start_candidate(full_text: str, candidate: Dict) -> Dict:
    """Vérifie un seul candidat de début. Renvoie le candidat enrichi (ne modifie pas l'original)."""
    candidate = dict(candidate)
    start = candidate.get("start_position")
    end = candidate.get("end_position")

    if start is None or end is None:
        # Impossible de récupérer le contexte sans positions -> on ne peut pas vérifier
        candidate["gemma_verified"] = None
        candidate["gemma_reason"] = "Positions manquantes, vérification impossible"
        return candidate

    ctx = _get_context(full_text, start, end)
    prompt = START_VERIFICATION_PROMPT.format(
        before=ctx["before"], candidate=candidate.get("full_match", ""), after=ctx["after"]
    )

    try:
        raw = call_gemma([{"role": "user", "content": prompt}])
        result = extract_json_object(raw)
        candidate["gemma_verified"] = bool(result.get("is_valid_start", True))
        candidate["gemma_confidence"] = result.get("confidence")
        candidate["gemma_reason"] = result.get("reason", "")

        corrected = (result.get("corrected_keyword") or "").strip()
        if corrected and corrected != candidate.get("keyword"):
            candidate["keyword_ocr_raw"] = candidate.get("keyword")
            candidate["keyword"] = corrected
            candidate["keyword_corrected_by_gemma"] = True
    except (GemmaClientError, ValueError) as e:
        # fail-open : on garde le candidat, mais on note l'échec
        candidate["gemma_verified"] = None
        candidate["gemma_reason"] = f"Échec de vérification Gemma : {e}"

    return candidate


def clean_signature_names(candidate: Dict) -> Dict:
    """
    Si le champ 'names' semble avoir avalé du texte qui ne lui appartient pas
    (voir NAMES_SUSPICIOUS_LENGTH), demande à Gemma d'en extraire le(s) vrai(s)
    nom(s). Ne fait rien si le champ est déjà court (économise l'appel API
    pour l'immense majorité des cas, qui sont déjà propres).
    """
    raw_names = candidate.get("names", "") or ""
    if len(raw_names) <= NAMES_SUSPICIOUS_LENGTH:
        return candidate

    prompt = NAMES_CLEANUP_PROMPT.format(raw_names=raw_names[:2000])
    try:
        raw = call_gemma([{"role": "user", "content": prompt}])
        result = extract_json_object(raw)
        clean = result.get("clean_names", "").strip()
        if clean:
            candidate["names_raw_before_cleanup"] = raw_names
            candidate["names"] = clean
            candidate["names_cleaned_by_gemma"] = True
    except (GemmaClientError, ValueError) as e:
        # fail-open ici aussi : si le nettoyage échoue, on garde le champ tel
        # quel (pollué) plutôt que de perdre l'info -- c'est un problème de
        # présentation, pas une raison d'écarter le document.
        candidate["names_cleanup_error"] = str(e)

    return candidate


def verify_end_candidate(full_text: str, candidate: Dict) -> Dict:
    """Vérifie un seul candidat de fin (signature). Même logique que verify_start_candidate."""
    candidate = dict(candidate)
    start = candidate.get("start_position")
    end = candidate.get("end_position")

    if start is None or end is None:
        candidate["gemma_verified"] = None
        candidate["gemma_reason"] = "Positions manquantes, vérification impossible"
        return candidate

    ctx = _get_context(full_text, start, end)
    signature_excerpt = full_text[start:end]
    prompt = END_VERIFICATION_PROMPT.format(
        before=ctx["before"], candidate=signature_excerpt, after=ctx["after"]
    )

    try:
        raw = call_gemma([{"role": "user", "content": prompt}])
        result = extract_json_object(raw)
        candidate["gemma_verified"] = bool(result.get("is_valid_end", True))
        candidate["gemma_confidence"] = result.get("confidence")
        candidate["gemma_reason"] = result.get("reason", "")
    except (GemmaClientError, ValueError) as e:
        candidate["gemma_verified"] = None
        candidate["gemma_reason"] = f"Échec de vérification Gemma : {e}"

    candidate = clean_signature_names(candidate)
    return candidate


def _keep_start_candidate(candidate: Dict) -> bool:
    """
    Politique de décision pour un candidat de début après vérification :
    - candidat normal : gardé sauf rejet explicite (gemma_verified is False) -> fail-open
    - candidat flou (fuzzy_matched) : gardé UNIQUEMENT si confirmé explicitement
      (gemma_verified is True) -> fail-closed, car un match approximatif a
      plus de chances d'être un faux positif qu'un match exact.
    """
    if candidate.get("fuzzy_matched"):
        return candidate.get("gemma_verified") is True
    return candidate.get("gemma_verified") is not False


def verify_start_candidates(full_text: str, candidates: List[Dict], drop_invalid: bool = True) -> List[Dict]:
    """
    Vérifie une liste de candidats de début, EN PARALLÈLE (voir MAX_PARALLEL_CALLS),
    avec un affichage de progression -- sur un gros BO avec 200+ candidats, les
    vérifier un par un en série peut prendre plusieurs minutes sans aucun retour
    visuel, ce qui donne l'impression que le script est bloqué.

    Si drop_invalid=True, applique _keep_start_candidate (fail-open pour les
    candidats normaux, fail-closed pour les candidats flous -- voir plus haut).
    """
    total = len(candidates)
    if total == 0:
        return []

    verified = [None] * total
    n_fuzzy = sum(1 for c in candidates if c.get("fuzzy_matched"))
    print(f"   🤖 Vérification Gemma de {total} candidat(s) de début "
          f"({n_fuzzy} flou(s)) (parallèle x{MAX_PARALLEL_CALLS})...")

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CALLS) as executor:
        future_to_index = {
            executor.submit(verify_start_candidate, full_text, c): i
            for i, c in enumerate(candidates)
        }
        done_count = 0
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            verified[index] = future.result()
            done_count += 1
            if done_count % 10 == 0 or done_count == total:
                print(f"      ... {done_count}/{total} vérifiés")

    if drop_invalid:
        return [c for c in verified if _keep_start_candidate(c)]
    return verified


def verify_end_candidates(full_text: str, candidates: List[Dict], drop_invalid: bool = True) -> List[Dict]:
    """Idem verify_start_candidates, mais pour les candidats de fin (signatures)."""
    total = len(candidates)
    if total == 0:
        return []

    verified = [None] * total
    print(f"   🤖 Vérification Gemma de {total} candidat(s) de fin (parallèle x{MAX_PARALLEL_CALLS})...")

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CALLS) as executor:
        future_to_index = {
            executor.submit(verify_end_candidate, full_text, c): i
            for i, c in enumerate(candidates)
        }
        done_count = 0
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            verified[index] = future.result()
            done_count += 1
            if done_count % 10 == 0 or done_count == total:
                print(f"      ... {done_count}/{total} vérifiés")

    if drop_invalid:
        return [c for c in verified if c.get("gemma_verified") is not False]
    return verified


# ---------------------------------------------------------------------------
# Nettoyage final : couper tout résidu non pertinent à la fin d'un document
# déjà extrait. Complète (ne remplace pas) les heuristiques regex de
# end_pattern.py -- celles-ci gèrent déjà les cas connus (marqueurs de page,
# en-tête du BO, mots d'annexe, en-têtes de ministère), mais chaque nouveau
# fichier peut révéler une nouvelle forme de résidu qu'on n'a pas anticipée
# (constaté sur BO_3405 : une section "حركات الموظفين وتدابير التسيير" en fin
# de fichier, complètement différente des cas déjà traités). Plutôt que de
# continuer à allonger une liste de mots-clés au cas par cas, on demande à
# Gemma de trancher directement à partir du contexte, pour ce cas ET pour
# toute forme similaire dans de futurs fichiers.
# ---------------------------------------------------------------------------

TRAILING_CLEANUP_PROMPT = """أنت مساعد متخصص في تحليل الجريدة الرسمية المغربية.

المهمة: النص التالي هو نهاية نص قانوني (قرار/مرسوم/ظهير) تم استخراجه آليا.
أحيانا تلتصق بنهايته بقايا لا علاقة لها بالنص نفسه، مثل:
- عنوان قسم أو وزارة تالية (مثال: "وزارة الدولة المكلفة بـ...")
- عنوان نص ملحق (اتفاقية، معاهدة)
- عنوان فئة إدارية جديدة (مثال: "حركات الموظفين وتدابير التسيير")
- بداية نص آخر غير مرتبط

النص عادة ينتهي بشكل طبيعي بعد التوقيع الرسمي (الإمضاء : اسم الموقع)، أو بصيغة
ختامية مشابهة. أي شيء بعد ذلك يعتبر بقايا يجب إزالتها.

نهاية النص المستخرج آليا (قد تحتوي بقايا، أو قد تكون نظيفة تماما):
---
{tail}
---

إذا كانت هناك بقايا: انسخ حرفيا (بنفس الأحرف تماما) الجزء الذي يجب إزالته،
بداية من أول حرف زائد بعد النهاية الطبيعية للنص. إذا لم تكن هناك أي بقايا،
أرجع نصا فارغا.

أجب حصريا بكائن JSON واحد بدون أي شرح إضافي وبدون Markdown، بهذا الشكل بالضبط:
{{"trailing_junk": "الجزء الزائد المنسوخ حرفيا هنا، أو فارغ إذا لا شيء"}}
"""


def clean_document_trailing_content(full_text: str, doc: Dict) -> Dict:
    """
    Vérifie la fin d'UN document déjà extrait et retire, via Gemma, tout
    résidu non pertinent qui s'y serait accroché. Ne modifie pas doc en
    place -- renvoie une copie.

    Fail-open : si l'appel échoue ou si le texte renvoyé par Gemma ne se
    retrouve pas tel quel dans legal_text (correspondance de sécurité avant
    de couper quoi que ce soit), le document est renvoyé inchangé.
    """
    doc = dict(doc)
    legal_text = doc.get("legal_text", "")
    if not legal_text:
        return doc

    tail = legal_text[-TRAILING_CONTEXT_CHARS:]
    prompt = TRAILING_CLEANUP_PROMPT.format(tail=tail)

    try:
        raw = call_gemma([{"role": "user", "content": prompt}], max_tokens=400)
        result = extract_json_object(raw)
        junk = (result.get("trailing_junk") or "").strip()
    except (GemmaClientError, ValueError) as e:
        doc["trailing_cleanup_error"] = str(e)
        return doc

    if not junk:
        return doc

    # Sécurité : on ne coupe que si le texte renvoyé par Gemma correspond
    # bien mot pour mot à une portion réelle de la fin du document -- jamais
    # de coupe "à l'aveugle" sur une simple confiance dans la réponse du modèle.
    cut_pos = legal_text.rfind(junk)
    if cut_pos == -1 or cut_pos < len(legal_text) - TRAILING_CONTEXT_CHARS - 50:
        doc["trailing_cleanup_error"] = "Texte renvoyé par Gemma introuvable tel quel, coupe ignorée"
        return doc

    doc["legal_text_before_trailing_cleanup"] = legal_text
    doc["legal_text"] = legal_text[:cut_pos].rstrip()
    doc["trailing_cleaned_by_gemma"] = True
    return doc


def clean_documents_trailing_content(full_text: str, documents: List[Dict]) -> List[Dict]:
    """
    Applique clean_document_trailing_content à une liste de documents déjà
    extraits, en parallèle (voir MAX_PARALLEL_CALLS), avec affichage de
    progression -- même logique que les fonctions verify_*_candidates.
    """
    total = len(documents)
    if total == 0:
        return []

    cleaned = [None] * total
    print(f"   🤖 Nettoyage Gemma de la fin de {total} document(s)...")

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CALLS) as executor:
        future_to_index = {
            executor.submit(clean_document_trailing_content, full_text, d): i
            for i, d in enumerate(documents)
        }
        done_count = 0
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            cleaned[index] = future.result()
            done_count += 1
            if done_count % 10 == 0 or done_count == total:
                print(f"      ... {done_count}/{total} nettoyés")

    n_cleaned = sum(1 for d in cleaned if d.get("trailing_cleaned_by_gemma"))
    print(f"   🤖 Gemma : {n_cleaned} document(s) avaient des résidus en fin de texte, nettoyés")

    return cleaned
