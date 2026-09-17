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

Politique en cas d'échec d'appel Gemma (timeout, erreur API, JSON invalide) :
on garde le candidat par défaut ("fail-open") plutôt que de le supprimer
silencieusement, et on le marque `verified=False` pour que ça reste visible
dans les logs / résultats. Mieux vaut un faux positif occasionnel qu'un vrai
texte juridique supprimé silencieusement parce que l'API était indisponible.
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


def _get_context(full_text: str, start: int, end: int) -> Dict[str, str]:
    before = full_text[max(0, start - CONTEXT_CHARS_BEFORE):start]
    after = full_text[end:end + CONTEXT_CHARS_AFTER]
    return {"before": before, "after": after}


START_VERIFICATION_PROMPT = """أنت مساعد متخصص في تحليل الجريدة الرسمية المغربية.

مهمتك: تحديد ما إذا كان "المقطع المرشح" أدناه هو فعلاً بداية حقيقية لنص قانوني
رسمي (ظهير، قانون، مرسوم، قرار...)، أم أنه مجرد ذكر لهذا النص في مكان آخر:
- ضمن فهرست / جدول محتويات في بداية العدد
- ضمن إحالة داخل نص آخر ("بناء على الظهير رقم...")
- ملخص أو عنوان متكرر

مؤشرات على أنه ليس بداية حقيقية:
- النص الذي يسبقه يذكر "فهرست" أو يحتوي قائمة عناوين متتالية شبيهة
- ينتهي بشكل مفاجئ برقم يشبه رقم صفحة
- ما يتبعه لا يشبه بداية مقتضيات قانونية (فصول، مواد) بل ينتقل مباشرة لعنوان آخر مختلف تماما

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
{{"is_valid_start": true, "confidence": 0.9, "reason": "شرح قصير جدا بالعربية"}}
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
    except (GemmaClientError, ValueError) as e:
        # fail-open : on garde le candidat, mais on note l'échec
        candidate["gemma_verified"] = None
        candidate["gemma_reason"] = f"Échec de vérification Gemma : {e}"

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

    return candidate


def verify_start_candidates(full_text: str, candidates: List[Dict], drop_invalid: bool = True) -> List[Dict]:
    """
    Vérifie une liste de candidats de début, EN PARALLÈLE (voir MAX_PARALLEL_CALLS),
    avec un affichage de progression -- sur un gros BO avec 200+ candidats, les
    vérifier un par un en série peut prendre plusieurs minutes sans aucun retour
    visuel, ce qui donne l'impression que le script est bloqué.

    Si drop_invalid=True, retire ceux confirmés comme invalides (gemma_verified is False).
    Ceux non vérifiables (gemma_verified is None, échec API) sont TOUJOURS gardés (fail-open).
    """
    total = len(candidates)
    if total == 0:
        return []

    verified = [None] * total
    print(f"   🤖 Vérification Gemma de {total} candidat(s) de début (parallèle x{MAX_PARALLEL_CALLS})...")

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
        return [c for c in verified if c.get("gemma_verified") is not False]
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