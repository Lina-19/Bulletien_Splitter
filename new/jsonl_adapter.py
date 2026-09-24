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


# ---------------------------------------------------------------------------
# Réparation des défauts d'ordre de l'OCR (avant tout traitement)
# ---------------------------------------------------------------------------
# Deux défauts récurrents de l'OCR, constatés sur BO_3405 (pages 19 et 31) :
#
# 1. TITRE REJETÉ EN FIN DE PAGE. Le titre en gras d'un arrêté, en haut de sa
#    colonne sur le PDF, reçoit de fausses coordonnées et se retrouve en
#    DERNIER bloc de la page, APRÈS son propre corps. Le pipeline voit alors un
#    corps sans titre (ignoré) et un titre sans corps (écarté) : le texte
#    entier disparaît (arrêtés 9.78 et 1336.77).
#    -> Si la page commence par un corps "إن وزير X ،" sans titre, et que le
#       DERNIER bloc est un titre qui cite ce même ministre ("قرار لوزير X"),
#       on remet le titre devant le corps. Sans correspondance du ministre, on
#       ne touche à rien (une page qui commence par un corps est souvent
#       normale : le titre est en bas de la page précédente).
#
# 3. SIGNATURE RANGÉE APRÈS UN AUTRE TEXTE. Constaté sur l'arrêté 1336.77 :
#    sa signature, juste sous "ينشر هذا القرار بالجريدة الرسمية", était lue
#    après tout l'arrêté 1257.77 situé plus bas -> 1336.77 perdait sa
#    signature. Voir la règle (étroite) dans repair_page_blocks.
#
# 2. BLOC DE SIGNATURE LU DEUX FOIS. Une suite de blocs identique répétée
#    immédiatement ("الفصل الثاني ... الإمضاء : ..." ×2). On ne supprime la
#    répétition que si elle contient une signature ou "وحرر" : des annonces
#    distinctes peuvent avoir légitimement le même texte, on n'y touche pas.

import re as _re
from start_pattern import extract_start_info as _extract_start_info

_BODY_OPENER = _re.compile(r"^\s*إن\s+(?P<who>[^،,\n]{3,70}?)\s*[،,]")
_SIG_MARK = _re.compile(r"الإمضاء|الامضاء|وحرر")
_SIG_START = _re.compile(r"^\s*وحـ*رر")
_SIGNER = _re.compile(r"(?:الإمضاء|الامضاء|إمضاء|امضاء|التوقيع)\s*:")
_SIG_BLOCK = _re.compile(r"^\s*وحـ*رر|(?:الإمضاء|الامضاء|التوقيع)\s*:|وقعه\s+بالعطف")
SIG_MAX_GAP_ABOVE = 150      # écart vertical maximal avec le bloc du dessus
SIG_GAP_TOLERANCE = 30       # léger chevauchement toléré
SIG_ADJACENT_TOL = 5         # deux blocs jointifs (bas de l'un = haut de l'autre)
SIG_RUN_MAX_GAP = 60         # écart max entre deux lignes d'un même bloc de signature
SIG_RUN_MAX_BLOCKS = 4       # un bloc de signature tient en quelques lignes
SIG_RUN_MAX_LINE_CHARS = 80  # ...et ces lignes sont courtes ("الإمضاء : ...")
                             # Sans ces deux limites, le regroupement happait
                             # le texte courant qui suit (13 blocs déplacés sur
                             # BO_3405 p.34 -> l'arrêté 1262.77 disparaissait).


def _norm(s: str) -> str:
    return _re.sub(r"\s+", " ", s.replace("#", "").replace("ـ", "")).strip()


def repair_page_blocks(blocks: List[Dict]) -> Tuple[List[Dict], List[str]]:
    repairs: List[str] = []
    blocks = list(blocks)

    # --- 2. suites de blocs répétées contenant une signature ---
    i = 0
    while i < len(blocks):
        removed = False
        for k in range(min(8, (len(blocks) - i) // 2), 1, -1):
            run = [_norm(b.get("content", "")) for b in blocks[i:i + k]]
            nxt = [_norm(b.get("content", "")) for b in blocks[i + k:i + 2 * k]]
            if run == nxt and _SIG_MARK.search(" ".join(run)):
                del blocks[i + k:i + 2 * k]
                repairs.append(f"{k} blocs de signature dupliqués supprimés")
                removed = True
                break
        if not removed:
            i += 1

    # --- 3. bloc de signature rangé après un texte situé plus bas ---
    # Règle GÉOMÉTRIQUE, appliquée UNIQUEMENT aux blocs de signature (وحرر,
    # "الإمضاء :", "وقعه بالعطف") : l'OCR les range souvent avec la colonne de
    # gauche du bas de page alors qu'ils appartiennent à la bande du dessus.
    # Un bloc de signature S est déplacé si :
    #   a) tous les blocs qui le précèdent, jusqu'à un bloc P, sont ENTIÈREMENT
    #      SOUS lui (ils appartiennent donc à une bande inférieure) ;
    #   b) P se trouve juste au-dessus de S (écart vertical faible).
    # S est alors replacé juste après P.
    # Ne s'applique qu'aux signatures : la même règle appliquée à tous les
    # blocs réordonnait des milliers de blocs sur des pages normales.
    # La condition (b) protège le cas normal "signature en haut de la colonne
    # de gauche" : le bloc situé au-dessus est alors très loin (ou en dessous).
    def _top(b): return b.get("top_left_y", 0) or 0
    def _bottom(b): return b.get("bottom_right_y", 0) or 0
    j = 0
    while j < len(blocks):
        blk = blocks[j]
        txt = _norm(blk.get("content", ""))
        if _SIG_BLOCK.search(txt) and j > 0 and _top(blocks[j - 1]) > _bottom(blk):
            i = j
            while i > 0 and blocks[i - 1].get("type") not in ("header", "footer") \
                    and _top(blocks[i - 1]) >= _bottom(blk) - SIG_ADJACENT_TOL:
                i -= 1
            gap = _top(blk) - _bottom(blocks[i - 1]) if i > 0 else None
            if i < j and gap is not None and -SIG_GAP_TOLERANCE <= gap <= SIG_MAX_GAP_ABOVE:
                # Le bloc de signature s'étend sur plusieurs blocs collés
                # ("وحرر ..." / "الوزير الأول ،" / "الإمضاء : ..."). On les
                # déplace ENSEMBLE : pris isolément, "الوزير الأول ،" ne
                # ressemble pas à une signature et serait resté en arrière.
                k = j + 1
                while (k < len(blocks) and k - j < SIG_RUN_MAX_BLOCKS
                       and 0 <= _top(blocks[k]) - _bottom(blocks[k - 1]) <= SIG_RUN_MAX_GAP
                       and len(_norm(blocks[k].get("content", ""))) <= SIG_RUN_MAX_LINE_CHARS):
                    k += 1
                run = blocks[j:k]
                del blocks[j:k]
                blocks[i:i] = run
                repairs.append(f"signature ({len(run)} bloc(s)) remontée dans sa bande, "
                               f"{j - i} bloc(s) plus bas sautés : {txt[:45]}")
                j = i + len(run)
                continue
        j += 1

    # --- 1. titre rejeté en fin de page ---
    content_idx = [j for j, b in enumerate(blocks)
                   if b.get("type") not in ("header", "footer") and b.get("content", "").strip()]
    if len(content_idx) >= 3:
        first_j, last_j = content_idx[0], content_idx[-1]
        first = _norm(blocks[first_j]["content"])
        last = _norm(blocks[last_j]["content"])
        opener = _BODY_OPENER.match(first)
        if opener and _extract_start_info(last):
            who = _norm(opener.group("who"))
            if who and who in last:
                title = blocks.pop(last_j)
                blocks.insert(first_j, title)
                repairs.append(f"titre remis devant son corps : {last[:60]}")

    return blocks, repairs


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

        page_blocks, repairs = repair_page_blocks(page.get("blocks", []))
        for r in repairs:
            print(f"   🔧 Page {page['page'] + 1} : {r}")

        for block in page_blocks:
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
