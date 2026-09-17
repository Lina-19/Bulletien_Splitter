import re
from typing import Dict, Optional, List

# ---------------------------
# CONFIGURATION
# ---------------------------
SIGNATURE_INDICATORS = ["وحرر"]

SIGNATURE_KEYWORDS_TYPE1 = ["وقعه بالعطف", "الإمضاء", "إمضاء"]
SIGNATURE_KEYWORDS_TYPE2 = ["الإمضاءات"]

SIGNATURE_LIMIT_KEYWORDS = ["قرار", "مرسوم", "ظهير", "قانون"]
SIGNATURE_LIMIT_SPECIALCHARS = ["\*", "=", "-", "\+", "#"]
SIGNATURE_LIMIT_ANNEXE_WORDS = ["annexe", "ملحق", "مرفق", "المرفق"]


# ---------------------------
# FUNCTIONS
# ---------------------------

def extract_signatures_from_text(text: str) -> List[Dict]:
    """
    Extract all signature blocks from text (type1 or type2).
    """
    results = []

    # Pattern for type1
    pattern_type1 = rf"({'|'.join(SIGNATURE_INDICATORS)}).*?({'|'.join(SIGNATURE_KEYWORDS_TYPE1)})\s*:?\s*"
    for match in re.finditer(pattern_type1, text, re.DOTALL):
        indicator = match.group(1)
        keyword = match.group(2)
        names_start = match.end()

        limit_pos, limit_val = find_limit(text, names_start)
        names_block = text[names_start:limit_pos].strip() if limit_pos else text[names_start:].strip()

        results.append({
            "type": "type 1",
            "signature_indicator": indicator,
            "key_signature": keyword,
            "names": names_block,
            "limit": limit_val or ""
        })

    # Pattern for type2
    pattern_type2 = rf"({'|'.join(SIGNATURE_KEYWORDS_TYPE2)})\s*:?\s*"
    for match in re.finditer(pattern_type2, text, re.DOTALL):
        keyword = match.group(1)
        names_start = match.end()

        limit_pos, limit_val = find_limit(text, names_start)
        names_block = text[names_start:limit_pos].strip() if limit_pos else text[names_start:].strip()

        results.append({
            "type": "type 2",
            "signature_indicator": "",
            "key_signature": keyword,
            "names": names_block,
            "limit": limit_val or ""
        })

    return results


def find_limit(text: str, start_pos: int) -> (Optional[int], Optional[str]):
    """
    Find the position and value of the limit after a signature.
    """
    candidates = []

    # Case 1: new legal text keyword
    keyword_pattern = rf"({'|'.join(SIGNATURE_LIMIT_KEYWORDS)})"
    m1 = re.search(keyword_pattern, text[start_pos:])
    if m1:
        candidates.append((start_pos + m1.start(), m1.group(1)))

    # Case 2: special chars
    special_pattern = rf"({'|'.join(SIGNATURE_LIMIT_SPECIALCHARS)})"
    m2 = re.search(special_pattern, text[start_pos:])
    if m2:
        candidates.append((start_pos + m2.start(), m2.group(1)))

    # Case 3: annex words
    annex_pattern = rf"({'|'.join(SIGNATURE_LIMIT_ANNEXE_WORDS)})"
    m3 = re.search(annex_pattern, text[start_pos:], re.IGNORECASE)
    if m3:
        candidates.append((start_pos + m3.start(), m3.group(1)))

    if candidates:
        limit_pos, limit_val = min(candidates, key=lambda x: x[0])
        return limit_pos, limit_val

    return None, None




if __name__ == "__main__":
    file_path = "data/test.txt"   # <<< replace with your file

    # Read file content
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract all signature blocks
    results = extract_signatures_from_text(content)

    # Print results in a clear pattern
    for i, res in enumerate(results, start=1):
        print("\n" + "+"*40)
        print(f"TEXT {i}")
        print(f"type signature : {res['type']}")
        print(f"signature indicator : {res['signature_indicator']}")
        print(f"key signature : {res['key_signature']}")
        print(f"names : {res['names']}")
        print(f"limit : {res['limit']}")

    