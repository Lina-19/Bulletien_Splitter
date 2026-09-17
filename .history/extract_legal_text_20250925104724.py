# extract_legal_text.py

from typing import Optional, Dict
from start_pattern import extract_start_info
from end_pattern import extract_signatures_from_text


def extract_legal_text(text: str, start_info: Dict, signature_info: Optional[Dict]) -> str:
    """
    Extract the complete legal text from start pattern to signature.
    """
    start_pos = start_info['start_position']

    if signature_info:
        return text[start_pos:signature_info['end_position']].strip()
    else:
        # If no signature found, extract until the end of text
        return text[start_pos:].strip()


if __name__ == "__main__":
    text_path = "data/test1.txt"

    # Read file content
    with open(text_path, "r", encoding="utf-8") as f:
        text_content = f.read()

    # Step 1: detect start
    start_info = extract_start_info(text_content)

    # Step 2: detect end (signatures)
    signature_info = extract_signatures_from_text(text_content)

    # Step 3: extract legal text between start and end
    if start_info:
        legal_text = extract_legal_text(text_content, start_info, signature_info)
        print("===== Extracted Legal Text =====")
        print(legal_text)
    else:
        print("No start pattern found.")
