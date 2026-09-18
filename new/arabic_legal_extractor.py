# arabic_legal_extractor.py
"""
Extraction de textes juridiques arabes entre début et fin, avec numéro de page,
et vérification optionnelle des candidats via Gemma.

Changements par rapport à l'ancienne version :
1. BUG CORRIGÉ : `match_patterns_and_extract` faisait `content.find(full_match)`
   pour retrouver la position d'un début déjà détecté. Problème : `.find()`
   renvoie la PREMIÈRE occurrence dans tout le document. Or on a justement
   trouvé un cas réel (le sommaire/فهرست du BO) où le même texte de début
   apparaît deux fois : une fois dans le sommaire, une fois comme vrai début.
   Résultat : la position pouvait pointer vers la mauvaise occurrence.
   -> Correction : `start_pattern.py` renvoie maintenant directement
   `start_position`/`end_position` calculés pendant le scan, qu'on utilise
   tels quels ici, sans jamais refaire de `.find()`.
2. AJOUT : une étape optionnelle de vérification par Gemma, qui filtre les
   faux positifs (ex: entrées de sommaire) avant le matching final.
"""

import re
import sys
import os
from typing import List, Dict, Optional

try:
    from start_pattern import extract_start_info, KEYWORDS
    from end_pattern import extract_signatures_from_text
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("Make sure start_pattern.py and end_pattern.py are in the same directory")
    sys.exit(1)

try:
    from gemma_verifier import verify_start_candidates, verify_end_candidates, clean_documents_trailing_content
    GEMMA_AVAILABLE = True
except ImportError:
    GEMMA_AVAILABLE = False


def normalize_md_headers(text: str) -> str:
    """Enlève les artefacts markdown (titres, puces, gras) qui peuvent venir de l'OCR/parsing."""
    text = re.sub(r"(?m)^\s*#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^\s*(?:[-–—•\*>\u2022]+)\s+", "", text)
    text = re.sub(r"(?m)^\s*\*\*(.+?)\*\*\s*$", r"\1", text)
    return text


def extract_page_numbers(content: str) -> List[Dict]:
    """Extrait les marqueurs '=== Page N ===' et leur position dans le texte."""
    page_positions = []
    for match in re.finditer(r"===\s*Page\s*(\d+)\s*===", content):
        page_positions.append({"page_number": int(match.group(1)), "position": match.start()})
    return page_positions


def get_page_for_position(position: int, page_positions: List[Dict]) -> Optional[int]:
    """Renvoie le numéro de page correspondant à une position donnée (page où ça COMMENCE)."""
    current_page = None
    for page in page_positions:
        if position >= page["position"]:
            current_page = page["page_number"]
        else:
            break
    return current_page


def extract_legal_documents(file_path: str, use_gemma_verification: bool = True) -> List[Dict]:
    """
    Extrait les textes juridiques d'un fichier texte brut avec marqueurs
    '=== Page N ===' (le format "historique" du pipeline).

    Pour une entrée au format JSONL (blocks OCR avec coordonnées), voir
    jsonl_adapter.py, qui construit (content, page_positions) autrement puis
    appelle extract_legal_documents_from_content ci-dessous -- c'est cette
    dernière qui contient la logique commune aux deux formats d'entrée.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        print(f"✅ Successfully read file: {file_path}")
        print(f"📄 File content length: {len(content)} characters")
        content = normalize_md_headers(content)
    except FileNotFoundError:
        print(f"❌ File {file_path} not found.")
        return []
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return []

    page_positions = extract_page_numbers(content)
    print(f"📑 Found {len(page_positions)} page markers")

    return extract_legal_documents_from_content(content, page_positions, use_gemma_verification)


def extract_legal_documents_from_content(
    content: str, page_positions: List[Dict], use_gemma_verification: bool = True
) -> List[Dict]:
    """
    Cœur du pipeline, indépendant du format d'entrée : reçoit directement le
    texte déjà assemblé et la table des pages, et fait tout le reste
    (détection, vérification Gemma optionnelle, matching, étiquetage pages).
    """
    start_patterns = extract_start_info(content)
    n_total_detected = len(start_patterns)

    # On ne garde que les textes AVEC signature (قرار/مرسوم/ظهير/قانون/منشور/
    # مذكرة/مقرر) : les entrées KEYWORDS_NO_SIGNATURE (اعلان, بلاغ, رأي, قائمة
    # أسماء...) sont écartées ici, avant même la vérification Gemma, pour ne
    # pas gaspiller des appels API sur des candidats qu'on ne veut pas garder
    # de toute façon.
    n_no_sig_dropped = sum(1 for p in start_patterns if not p.get("has_signature", True))
    start_patterns = [p for p in start_patterns if p.get("has_signature", True)]
    print(f"🔍 Found {n_total_detected} start patterns "
          f"({n_no_sig_dropped} sans signature écartés, {len(start_patterns)} retenus)")

    end_patterns = extract_signatures_from_text(content)
    print(f"✍️ Found {len(end_patterns)} signature patterns (avant vérification)")

    if use_gemma_verification:
        if not GEMMA_AVAILABLE:
            print("⚠️  gemma_verifier.py introuvable, vérification Gemma ignorée.")
        else:
            n_before = len(start_patterns)
            start_patterns = verify_start_candidates(content, start_patterns)
            print(f"🤖 Gemma : {n_before - len(start_patterns)} faux positifs de début écartés "
                  f"({len(start_patterns)} confirmés/gardés)")

            n_before = len(end_patterns)
            end_patterns = verify_end_candidates(content, end_patterns)
            print(f"🤖 Gemma : {n_before - len(end_patterns)} faux positifs de fin écartés "
                  f"({len(end_patterns)} confirmés/gardés)")
    else:
        # Sans Gemma, les candidats "flous" (fuzzy_matched -- match approximatif
        # tolérant une faute d'OCR) ne peuvent pas être confirmés : on les
        # écarte par précaution plutôt que de risquer un faux positif non
        # vérifié. Relancer avec Gemma activé permettrait de les récupérer.
        n_fuzzy = sum(1 for p in start_patterns if p.get("fuzzy_matched"))
        if n_fuzzy:
            start_patterns = [p for p in start_patterns if not p.get("fuzzy_matched")]
            print(f"⚠️  {n_fuzzy} candidat(s) flou(s) (faute d'OCR probable) écarté(s) "
                  f"car Gemma est désactivé -- relancer sans --no-gemma pour les vérifier.")

    print(f"   ✍️  {len(start_patterns)} textes avec signature retenus au total")

    legal_documents = match_patterns_and_extract(content, start_patterns, end_patterns)

    all_documents = legal_documents
    all_documents.sort(key=lambda x: x["start_position"])

    for i, doc in enumerate(all_documents, 1):
        doc["document_number"] = i
        doc["page_number"] = get_page_for_position(doc["start_position"], page_positions)
        doc["end_page_number"] = get_page_for_position(doc["end_position"], page_positions)

    print(f"📜 Extracted {len(all_documents)} complete legal documents")

    if use_gemma_verification and GEMMA_AVAILABLE:
        all_documents = clean_documents_trailing_content(content, all_documents)

    return all_documents


def extract_no_signature_documents(content: str, start_patterns: List[Dict]) -> List[Dict]:
    """Textes sans signature : la fin = le prochain mot-clé juridique, ou 2000 caractères par défaut."""
    documents = []
    keyword_pattern = rf"^(?P<limit>{'|'.join(KEYWORDS)})(?=\s|$|[،:؛\.\)])"

    for i, pattern in enumerate(start_patterns):
        start_pos = pattern.get("start_position")
        end_pos = pattern.get("end_position")
        if start_pos is None or end_pos is None:
            continue

        remaining_text = content[end_pos:]
        next_keyword_match = re.search(keyword_pattern, remaining_text, flags=re.MULTILINE)
        limit_pos = end_pos + next_keyword_match.start() if next_keyword_match else min(end_pos + 2000, len(content))

        legal_text = content[start_pos:limit_pos].strip()
        if len(legal_text) > 50:
            documents.append({
                "document_number": i + 1,
                "start_pattern": pattern,
                "end_pattern": {
                    "type": "No Signature",
                    "key_signature": "N/A",
                    "names": "N/A",
                    "limit": next_keyword_match.group(1) if next_keyword_match else "End of text",
                },
                "legal_text": legal_text,
                "start_position": start_pos,
                "end_position": limit_pos,
                "text_length": len(legal_text),
                "has_signature": False,
            })
    return documents


def _trim_trailing_page_markers(content: str, start_pos: int, end_pos: int) -> int:
    """
    Recule end_pos pour exclure tout marqueur '=== Page N ===' (et espaces
    associés) qui traînerait en fin de document.

    Pourquoi : la limite de fin d'un document est souvent l'en-tête du BO de
    la page SUIVANTE, qui se trouve forcément APRÈS le marqueur de page.
    Le marqueur était donc happé au passage. Deux effets indésirables :
    - un '=== Page N ===' orphelin collé après la signature du texte
    - un libellé de page faux ('Page: 3-4' pour un texte qui tient
      entièrement sur la page 3), puisque end_page_number est calculé
      depuis end_position.
    """
    trimmed = content[start_pos:end_pos]
    pattern = re.compile(r"(?:\s*===\s*Page\s*\d+\s*===\s*)+$")
    while True:
        match = pattern.search(trimmed)
        if not match:
            break
        trimmed = trimmed[:match.start()]
    return start_pos + len(trimmed)


def match_patterns_and_extract(content: str, start_patterns: List[Dict], end_patterns: List[Dict]) -> List[Dict]:
    """
    Associe chaque début à la signature la plus proche après lui, à condition
    qu'aucun autre début ne s'intercale entre les deux.

    (Positions prises directement depuis les patterns -- voir note en haut du
    fichier sur le bug content.find() corrigé.)
    """
    legal_documents = []
    start_positions = [
        {"index": i, "pattern": p, "position": p["start_position"], "end_position": p["end_position"]}
        for i, p in enumerate(start_patterns)
        if p.get("start_position") is not None
    ]
    start_positions.sort(key=lambda x: x["position"])

    for i, start_info in enumerate(start_positions):
        start_pos = start_info["end_position"]
        best_end = None
        min_distance = float("inf")

        for end_pattern in end_patterns:
            end_start_pos = end_pattern.get("start_position", 0)
            if end_start_pos > start_pos:
                distance = end_start_pos - start_pos
                interfering_start = any(
                    start_pos < other["position"] < end_start_pos
                    for other in start_positions if other is not start_info
                )
                if not interfering_start and distance < min_distance:
                    min_distance = distance
                    best_end = end_pattern

        if best_end:
            start_pattern_pos = start_info["position"]
            end_pattern_end_pos = best_end.get("end_position", len(content))
            end_pattern_end_pos = _trim_trailing_page_markers(content, start_pattern_pos, end_pattern_end_pos)
            complete_legal_text = content[start_pattern_pos:end_pattern_end_pos].strip()

            if len(complete_legal_text) > 50:
                legal_documents.append({
                    "document_number": i + 1,
                    "start_pattern": start_info["pattern"],
                    "end_pattern": best_end,
                    "legal_text": complete_legal_text,
                    "start_position": start_pattern_pos,
                    "end_position": end_pattern_end_pos,
                    "text_length": len(complete_legal_text),
                    "has_signature": True,
                })
    return legal_documents


def _format_page_label(doc: Dict) -> str:
    """
    Construit le libellé de page à afficher, avec le décalage +1 : la page 0
    du JSONL correspond à la page 1 du PDF réel (numérotation humaine),
    alors qu'en interne (page_positions, get_page_for_position) on garde les
    numéros du JSONL tels quels pour que les calculs de position restent
    cohérents. Le +1 n'est appliqué qu'ici, à l'affichage.
    """
    start_page = doc.get("page_number")
    end_page = doc.get("end_page_number")

    if start_page is None:
        return ""

    start_display = start_page + 1
    if end_page is None or end_page == start_page:
        return str(start_display)

    end_display = end_page + 1
    return f"{start_display}-{end_display}"


def _renumber_embedded_page_markers(legal_text: str) -> str:
    """
    Un texte multi-pages contient des marqueurs '=== Page N ===' hérités
    directement de `content` (voir jsonl_adapter.py / extract_page_numbers),
    avec le numéro de page INTERNE (0-indexé, celui du JSONL) -- alors que le
    champ '• Page:' affiché juste au-dessus utilise déjà le numéro humain
    (+1, celui du vrai PDF). Sans ce correctif, on se retrouve avec un
    marqueur '=== Page 9 ===' à l'intérieur du texte alors que '• Page:'
    annonce '10' pour ce même passage -- déroutant et incohérent.
    Cette fonction réapplique le même +1 à CHAQUE marqueur trouvé dans le
    texte, pour que la numérotation soit cohérente partout dans le fichier.
    """
    def _bump(match: re.Match) -> str:
        internal_page = int(match.group(1))
        return f"=== Page {internal_page + 1} ==="

    return re.sub(r"===\s*Page\s*(\d+)\s*===", _bump, legal_text)


def save_extracted_documents(documents: List[Dict], output_file: str):
    """
    Sauvegarde les textes extraits dans le format demandé :

    ================================================================================
    EXTRACTED ARABIC LEGAL DOCUMENTS
    ================================================================================

    📄 TEXT 1

    • Keyword: ...
    • Number: ...
    • Date: ...
    • Key Signature: ...
    • Names: ...
    • Page: ...

    • LEGAL TEXT:
    <texte intégral, avec les marqueurs de page conservés à l'intérieur pour les textes multi-pages>


    ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

    📄 TEXT 2
    ...

    Le champ "Page" est affiché pour TOUS les documents (mono ou multi-page),
    car pour un texte tenant sur une seule page, aucun marqueur '=== Page N ==='
    n'apparaît à l'intérieur du texte lui-même -- sans ce champ, impossible de
    savoir sur quelle page il se trouve. La numérotation affichée est celle du
    PDF réel (page JSONL + 1), voir _format_page_label ci-dessus.
    """
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("EXTRACTED ARABIC LEGAL DOCUMENTS\n")
            f.write("=" * 80 + "\n\n")

            for i, doc in enumerate(documents, 1):
                start = doc.get("start_pattern") or {}
                end = doc.get("end_pattern") or {}

                f.write(f"📄 TEXT {i}\n\n")
                f.write(f"• Keyword: {start.get('keyword', '')}\n")
                f.write(f"• Number: {start.get('number', '')}\n")
                f.write(f"• Date: {start.get('date', '')}\n")
                f.write(f"• Key Signature: {end.get('key_signature', '')}\n")
                f.write(f"• Names: {end.get('names', '')}\n")
                f.write(f"• Page: {_format_page_label(doc)}\n")
                f.write("\n")
                f.write("• LEGAL TEXT:\n")
                f.write(_renumber_embedded_page_markers(doc.get("legal_text", "").strip()))
                f.write("\n\n\n")
                f.write("+" * 80 + "\n\n")

        print(f"✅ Extracted texts saved to: {output_file}")
    except Exception as e:
        print(f"❌ Error saving results: {e}")


def main():
    print("🕌 Arabic Legal Text Extractor (avec vérification Gemma optionnelle)")
    print("=" * 50)

    if len(sys.argv) < 2:
        print("❌ Usage: python3 arabic_legal_extractor.py <path_to_input_file> [--no-gemma]")
        sys.exit(1)

    input_file = sys.argv[1]
    use_gemma = "--no-gemma" not in sys.argv

    file_name = os.path.basename(input_file)
    output_file = os.path.join("extracted_files", f"{os.path.splitext(file_name)[0]}_extracted.txt")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    documents = extract_legal_documents(input_file, use_gemma_verification=use_gemma)
    if documents:
        save_extracted_documents(documents, output_file)
        print(f"\n🎉 Successfully extracted {len(documents)} documents!")
        print(f"📂 Saved to: {output_file}")
    else:
        print("❌ No legal documents could be extracted.")


if __name__ == "__main__":
    main()
