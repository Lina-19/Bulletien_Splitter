"""
jsonl_adapter.py
----------------
Transforme le format JSONL envoyé par ton manager (une ligne = une page,
avec `blocks` = zones OCR avec coordonnées x/y et un `type`) en une entrée
exploitable par le reste du pipeline (`arabic_legal_extractor.py`), sans
avoir à modifier la logique de détection/matching existante.

Format d'une ligne du JSONL (ce qu'on utilise ici) :
{
  "page": 4,
  "text": "...",              # déjà assemblé dans l'ordre de lecture, avec du markdown
  "blocks": [
      {"top_left_x": .., "top_left_y": .., "bottom_right_x": .., "bottom_right_y": ..,
       "content": "...", "type": "header|title|text|table|list|caption|footer"},
      ...
  ],
  ...
}

Deux infos utiles vérifiées sur les vrais fichiers :
- Les `blocks` sont déjà triés dans l'ordre de lecture (colonnes RTL gérées).
- Le `type` permet de distinguer un titre de section (`title`), un en-tête de
  page (`header`), du texte normal (`text`) -- utile pour, par exemple,
  repérer et exclure une éventuelle section فهرست (sommaire) plus tard sans
  changer le regex lui-même.

On reconstruit `content` directement à partir des `blocks` (pas du champ
`text` de la page) pour pouvoir calculer, pour chaque bloc, sa position
absolue exacte dans le texte final -- utile pour du débogage ou un filtrage
plus fin par la suite.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Tuple

try:
    from arabic_legal_extractor import (
        normalize_md_headers,
        extract_page_numbers,
        extract_legal_documents_from_content,
        save_extracted_documents,
    )
except ImportError as e:
    raise ImportError(
        "jsonl_adapter.py doit être dans le même dossier que arabic_legal_extractor.py"
    ) from e


def load_jsonl_pages(file_path: str) -> List[Dict]:
    """Lit le fichier JSONL et renvoie la liste des pages triées par numéro de page."""
    pages = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pages.append(json.loads(line))
    pages.sort(key=lambda p: p["page"])
    return pages


def build_content_from_pages(pages: List[Dict]) -> Tuple[str, List[Dict], List[Dict]]:
    """
    Construit :
    - `content` : le texte complet concaténé (une string continue), avec un
      marqueur '=== Page N ===' au début de chaque page (compatible avec
      extract_page_numbers si jamais on veut revérifier avec les regex existantes)
    - `page_positions` : [{"page_number": n, "position": pos}, ...]
    - `block_positions` : [{"page_number", "type", "start_position", "end_position", "bbox"}, ...]
      -- pas utilisé par le pipeline actuel, mais gardé pour un futur filtrage
      plus fin (ex: exclure un sommaire) sans devoir tout reconstruire.
    """
    content_parts = []
    page_positions = []
    block_positions = []
    cursor = 0

    for page in pages:
        marker = f"\n=== Page {page['page']} ===\n"
        content_parts.append(marker)
        page_positions.append({"page_number": page["page"], "position": cursor})
        cursor += len(marker)

        for block in page.get("blocks", []):
            block_text = block.get("content", "")
            if not block_text:
                continue

            block_positions.append({
                "page_number": page["page"],
                "type": block.get("type"),
                "start_position": cursor,
                "end_position": cursor + len(block_text),
                "bbox": (
                    block.get("top_left_x"), block.get("top_left_y"),
                    block.get("bottom_right_x"), block.get("bottom_right_y"),
                ),
            })

            content_parts.append(block_text)
            content_parts.append("\n\n")
            cursor += len(block_text) + 2

    content = "".join(content_parts)
    return content, page_positions, block_positions


def extract_legal_documents_from_jsonl(file_path: str, use_gemma_verification: bool = True) -> List[Dict]:
    """
    Point d'entrée principal pour UN fichier : prend le chemin d'un fichier
    JSONL (comme ocr_BO_3334_Ar.jsonl / ocr_BO_3409_Ar.jsonl) et renvoie la
    liste des textes juridiques extraits, avec page de début / page de fin.
    """
    pages = load_jsonl_pages(file_path)
    print(f"✅ {len(pages)} pages chargées depuis {file_path}")

    content, page_positions, block_positions = build_content_from_pages(pages)

    # IMPORTANT : normalize_md_headers() supprime des caractères (titres
    # markdown, puces...) et donc DÉCALE toutes les positions qui suivent.
    # page_positions a été calculé sur le contenu BRUT (avant normalisation) ;
    # l'utiliser tel quel après normalisation le désynchronise progressivement
    # du contenu réellement utilisé par tout le reste du pipeline (le
    # décalage grandit au fil du document, plus on avance, plus les
    # numéros de page affichés deviennent faux). On le recalcule donc sur le
    # contenu déjà normalisé, exactement comme le fait extract_legal_documents
    # (le chemin "fichier texte brut") dans arabic_legal_extractor.py.
    content = normalize_md_headers(content)
    page_positions = extract_page_numbers(content)

    print(f"📄 Contenu assemblé : {len(content)} caractères, {len(block_positions)} blocks")

    return extract_legal_documents_from_content(content, page_positions, use_gemma_verification)


def process_folder(
    input_dir: str,
    output_dir: str = "extracted_files",
    use_gemma_verification: bool = True,
    pattern: str = "*.jsonl",
) -> Dict[str, int]:
    """
    Boucle sur tous les fichiers .jsonl d'un dossier (ex: /input), extrait les
    textes juridiques de chacun, et sauvegarde un fichier `<nom>_extracted.txt`
    par fichier source dans `output_dir`.

    Si un fichier plante (JSON invalide, page mal formée, erreur Gemma...),
    on logue l'erreur et on PASSE AU SUIVANT plutôt que d'arrêter tout le lot
    -- important pour un traitement en masse où un seul fichier corrompu ne
    doit pas bloquer les autres.

    Renvoie un résumé {nom_fichier: nombre_de_documents_extraits} (ou -1 en
    cas d'échec sur ce fichier).
    """
    input_path = Path(input_dir)
    jsonl_files = sorted(input_path.glob(pattern))

    if not jsonl_files:
        print(f"⚠️  Aucun fichier '{pattern}' trouvé dans {input_dir}")
        return {}

    print(f"📂 {len(jsonl_files)} fichier(s) trouvé(s) dans {input_dir}")
    os.makedirs(output_dir, exist_ok=True)

    summary = {}
    for i, jsonl_file in enumerate(jsonl_files, 1):
        print(f"\n{'=' * 60}")
        print(f"[{i}/{len(jsonl_files)}] Traitement de : {jsonl_file.name}")
        print("=" * 60)

        try:
            documents = extract_legal_documents_from_jsonl(str(jsonl_file), use_gemma_verification)
            output_file = os.path.join(output_dir, f"{jsonl_file.stem}_extracted.txt")
            save_extracted_documents(documents, output_file)
            summary[jsonl_file.name] = len(documents)
        except Exception as e:
            print(f"❌ Échec sur {jsonl_file.name} : {e}")
            summary[jsonl_file.name] = -1

    print(f"\n{'=' * 60}")
    print("📊 Résumé du lot :")
    for name, count in summary.items():
        status = f"{count} documents" if count >= 0 else "ÉCHEC"
        print(f"   - {name} : {status}")
    total_ok = sum(c for c in summary.values() if c >= 0)
    total_failed = sum(1 for c in summary.values() if c < 0)
    print(f"   Total : {total_ok} documents extraits, {total_failed} fichier(s) en échec")

    return summary


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  Un seul fichier :  python3 jsonl_adapter.py <fichier.jsonl> [--no-gemma]")
        print("  Un dossier entier: python3 jsonl_adapter.py <dossier/> [--no-gemma]")
        sys.exit(1)

    use_gemma = "--no-gemma" not in sys.argv
    target = sys.argv[1]

    if os.path.isdir(target):
        process_folder(target, output_dir="extracted_files", use_gemma_verification=use_gemma)
    elif os.path.isfile(target):
        from arabic_legal_extractor import save_extracted_documents

        documents = extract_legal_documents_from_jsonl(target, use_gemma_verification=use_gemma)
        file_name = os.path.basename(target)
        output_file = os.path.join("extracted_files", f"{os.path.splitext(file_name)[0]}_extracted.txt")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        save_extracted_documents(documents, output_file)
        print(f"🎉 {len(documents)} documents extraits -> {output_file}")
    else:
        print(f"❌ '{target}' n'existe pas (ni fichier, ni dossier).")
        sys.exit(1)