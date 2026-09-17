import re
import sys
from typing import Dict, Optional, List
from pathlib import Path

# === Import your existing logic ===
from start_pattern import extract_start_info
from end_pattern import extract_signature_info


def extract_legal_text(text: str, start_info: Dict, signature_info: Optional[Dict]) -> Dict:
    """
    Extract the complete legal text between a start pattern and a signature.
    """
    start_pos = start_info.get("start_position")
    end_pos = signature_info.get("end_position") if signature_info else None

    if not start_pos:
        return {}

    if end_pos:
        full_text = text[start_pos:end_pos].strip()
    else:
        # If no signature found, take until next start keyword or end of document
        full_text = text[start_pos:].strip()

    return {
        "keyword": start_info.get("keyword", ""),
        "number": start_info.get("number", ""),
        "date": start_info.get("date", ""),
        "signature": signature_info.get("signature", "") if signature_info else "",
        "names": signature_info.get("names", []) if signature_info else [],
        "legal_text": full_text
    }


def process_file(file_path: str, output_path: str):
    """Read file, extract legal texts, and save results."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
    except FileNotFoundError:
        print(f"❌ File {file_path} not found.")
        sys.exit(1)

    # Extract start and signature patterns
    start_patterns = extract_start_info(text_content)
    signature_patterns = extract_signature_info(text_content)

    results: List[Dict] = []

    for i, start_info in enumerate(start_patterns):
        # Find nearest signature that comes after this start
        sig_info = next((s for s in signature_patterns if s["start_position"] > start_info["start_position"]), None)
        result = extract_legal_text(text_content, start_info, sig_info)
        if result:
            results.append(result)

    # Save results to file
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for i, r in enumerate(results, 1):
            f.write(f"LEGAL TEXT {i}\n")
            f.write(f"Keyword: {r['keyword']}\n")
            f.write(f"Number: {r['number']}\n")
            f.write(f"Date: {r['date']}\n")
            f.write(f"Signature: {r['signature']}\n")
            f.write(f"Names: {', '.join(r['names'])}\n")
            f.write("----- Full Legal Text -----\n")
            f.write(r['legal_text'] + "\n")
            f.write("\n" + "="*70 + "\n\n")

    print(f"✅ Extracted {len(results)} legal texts saved to {output_path}")


if __name__ == "__main__":
    input_file = "data/BO_7055_Ar.txt"
    output_file = "extracted_files/legal_texts.txt"
    process_file(input_file, output_file)
