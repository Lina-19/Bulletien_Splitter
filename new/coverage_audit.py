"""
coverage_audit.py
-----------------
Mesure la COUVERTURE de l'extraction : combien de textes juridiques présents
dans la source ont réellement été extraits, et lesquels manquent.

Pourquoi : avec des milliers de fichiers, impossible de vérifier à la main
page par page. Cet outil repère indépendamment chaque "titre" de texte
juridique dans la source (ligne commençant par un mot-clé -- قرار, مرسوم,
ظهير... -- suivi d'une date dans les caractères qui suivent) et vérifie qu'il
tombe à l'intérieur d'un document extrait.

Les entrées du sommaire (فهرست) répètent les titres des vrais textes : un
titre est donc considéré couvert si N'IMPORTE QUELLE de ses occurrences
(même numéro) est couverte.

Usage :
    python3 coverage_audit.py input/            # un dossier
    python3 coverage_audit.py fichier.jsonl     # un fichier
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List

from start_pattern import KEYWORDS
from jsonl_adapter import load_jsonl_pages, build_content_from_pages
from arabic_legal_extractor import (
    normalize_md_headers,
    extract_page_numbers,
    get_page_for_position,
    extract_legal_documents_from_content,
)

_HEADING = re.compile(
    rf"(?m)^[ \t]*(?:بموجب\s+)?(?P<kw>{'|'.join(sorted(KEYWORDS, key=len, reverse=True))}|ظهر شريف)(?=\s)"
)
_DATE_NEAR = re.compile(r"بتاريخ|صادر\s*في|صادرة\s*في|المؤرخ")
_NUMBER = re.compile(r"(?:رقم|عدد)\s+([\d][\d\.\-/]*[\d])")
HEADING_DATE_WINDOW = 160


def find_headings(content: str) -> List[Dict]:
    """Titres de textes juridiques présents dans la source (indépendamment du pipeline)."""
    out = []
    for m in _HEADING.finditer(content):
        window = content[m.end():m.end() + HEADING_DATE_WINDOW]
        if not _DATE_NEAR.search(window):
            continue
        num = _NUMBER.search(window[:160])
        if num:
            # L'OCR inverse souvent les parties du numéro entre le sommaire et
            # le corps ("1289.77" vs "77.1289") : on compare l'ensemble des
            # parties, pas leur ordre, pour reconnaître le même texte.
            key = "#" + ".".join(sorted(re.split(r"[\.\-/]", num.group(1))))
        else:
            key = re.sub(r"\s+", " ", content[m.start():m.start() + 70])
        out.append({"position": m.start(), "key": key,
                    "line": content[m.start():content.find("\n", m.start())][:110]})
    return out


def audit_file(path: str) -> Dict:
    content = build_content_from_pages(load_jsonl_pages(path))[0]
    content = normalize_md_headers(content)
    page_positions = extract_page_numbers(content)

    docs = extract_legal_documents_from_content(content, page_positions, use_gemma_verification=False)
    spans = [(d["start_position"], d["end_position"]) for d in docs]

    by_key: Dict[str, List[Dict]] = {}
    for h in find_headings(content):
        by_key.setdefault(h["key"], []).append(h)

    missing = []
    for key, occ in by_key.items():
        covered = any(s <= h["position"] < e for h in occ for s, e in spans)
        if not covered:
            real = occ[-1]  # dernière occurrence = le vrai texte (le sommaire est au début)
            page = get_page_for_position(real["position"], page_positions)
            missing.append({"page": (page + 1) if page is not None else "?", "line": real["line"]})

    return {"file": os.path.basename(path), "titles": len(by_key),
            "extracted": len(docs), "missing": missing}


def main():
    import contextlib, io
    target = sys.argv[1] if len(sys.argv) > 1 else "input/"
    files = sorted(Path(target).glob("*.jsonl")) if os.path.isdir(target) else [Path(target)]

    tot_titles = tot_missing = 0
    for f in files:
        with contextlib.redirect_stdout(io.StringIO()):
            r = audit_file(str(f))
        n_miss = len(r["missing"])
        tot_titles += r["titles"]
        tot_missing += n_miss
        cov = 100 * (r["titles"] - n_miss) / r["titles"] if r["titles"] else 100
        print(f"{r['file']:<28} titres={r['titles']:>3}  extraits={r['extracted']:>3}  "
              f"manquants={n_miss:>3}  couverture={cov:5.1f}%")
        for m in r["missing"]:
            print(f"      p.{m['page']:<4} {m['line']}")

    if tot_titles:
        print(f"\nCOUVERTURE GLOBALE : {100 * (tot_titles - tot_missing) / tot_titles:.1f}% "
              f"({tot_missing} textes manquants sur {tot_titles})")


if __name__ == "__main__":
    main()
