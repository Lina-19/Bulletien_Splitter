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

def extract_signature_and_limit(text: str) -> Optional[Dict]:
    """
    Extract signature info (type, indicator, keyword, names) and limit.
    """
    # --- Type 1 pattern (with indicator before signature keyword) ---
    pattern_type1 = rf"({'|'.join(SIGNATURE_INDICATORS)})[\s\S]*?({'|'.join(SIGNATURE_KEYWORDS_TYPE1)})\s*:?\s*(.+)"
    match1 = re.search(pattern_type1, text)

    if match1:
        indicator = match1.group(1)
        keyword = match1.group(2)
        names_start = match1.end(2)

        # everything after the keyword until the limit
        limit_pos, limit_val = find_limit(text, names_start)
        names_block = text[names_start:limit_pos].strip() if limit_pos else text[names_start:].strip()

        return {
            "type": "type 1",
            "signature_indicator": indicator,
            "key_signature": keyword,
            "names": names_block,
            "limit": limit_val or ""
        }

    # --- Type 2 pattern (only keyword, no indicator) ---
    pattern_type2 = rf"({'|'.join(SIGNATURE_KEYWORDS_TYPE2)})\s*:?\s*(.+)"
    match2 = re.search(pattern_type2, text)

    if match2:
        keyword = match2.group(1)
        names_start = match2.end(1)

        limit_pos, limit_val = find_limit(text, names_start)
        names_block = text[names_start:limit_pos].strip() if limit_pos else text[names_start:].strip()

        return {
            "type": "type 2",
            "signature_indicator": "",
            "key_signature": keyword,
            "names": names_block,
            "limit": limit_val or ""
        }

    return None


def find_limit(text: str, start_pos: int) -> (Optional[int], Optional[str]):
    """
    Find the position and value of the limit.
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
        # return the earliest limit found
        limit_pos, limit_val = min(candidates, key=lambda x: x[0])
        return limit_pos, limit_val

    return None, None


# ---------------------------
# DEMO
# ---------------------------
if __name__ == "__main__":
    text1 = """وحرر بالرباط في 25 من جمادى الآخرة 1443 (28 يناير 2022).
الإمضاء : عزيز أخنوش.
وقعه بالعطف :
وزير الداخلية
الإمضاء : عبد الوافي لفتيت.
وزير الصحة والحماية الاجتماعية
الإمضاء : خالد ايت طالب.
="""

    text2 = """الإمضاءات :
أحمد رحو.
جيهان بنيوسف.
عبد الغني أسنينة.
عبد اللطيف المقدم.
حسن أبو عبد المجيد."""

    for i, txt in enumerate([text1, text2], start=1):
        result = extract_signature_and_limit(txt)
        print(f"\nTEXT {i}")
        for k, v in result.items():
            print(f"{k}: {v}")
