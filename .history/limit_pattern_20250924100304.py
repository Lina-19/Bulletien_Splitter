import re
from typing import List, Optional, Dict
from start_pattern import KEYWORDS



SIGNATURE_INDICATORS = [
    "وحرر"
]

SIGNATURE_KEYWORDS_TYPE1 = [
    "وقعه بالعطف", 
    "الإمضاء", 
    "إمضاء"
]

SIGNATURE_KEYWORDS_TYPE2 = [
    "الإمضاءات"
]

# Limit rules
SIGNATURE_LIMIT_KEYWORDS = KEYWORDS  # reuse from your start pattern
SIGNATURE_LIMIT_SPECIAL_CHARS = ["*", "=", "_", "-", "+", "#"]
SIGNATURE_LIMIT_ANNEXE_WORDS = ["annexe", "ملحق", "مرفق", "المرفق", "الملحق"]



def find_signature(text: str, start_pos: int) -> Optional[Dict]:
    """
    Find the signature pattern (type1 or type2) after a given start position.
    """
    remaining_text = text[start_pos:]

    # Type 1: indicator + signature keyword
    type1_pattern = rf"({'|'.join(SIGNATURE_INDICATORS)}).*?({'|'.join(SIGNATURE_KEYWORDS_TYPE1)})\s*:?([\s\S]+?)"
    match1 = re.search(type1_pattern, remaining_text)

    if match1:
        sig_start = start_pos + match1.start()
        sig_keyword = match1.group(2)
        names_block = extract_names(match1.group(3))
        return {
            "signature_type": "type1",
            "signature_keyword": sig_keyword,
            "names": names_block,
            "start_position": sig_start,
            "end_position": start_pos + match1.end()
        }

    # Type 2: only signature keyword (no indicator)
    type2_pattern = rf"({'|'.join(SIGNATURE_KEYWORDS_TYPE2)})\s*:?([\s\S]+?)"
    match2 = re.search(type2_pattern, remaining_text)

    if match2:
        sig_start = start_pos + match2.start()
        sig_keyword = match2.group(1)
        names_block = extract_names(match2.group(2))
        return {
            "signature_type": "type2",
            "signature_keyword": sig_keyword,
            "names": names_block,
            "start_position": sig_start,
            "end_position": start_pos + match2.end()
        }

    return None


def extract_names(names_block: str) -> List[str]:
    """
    Extract names from the signature block. Names usually end with a dot.
    """
    # Match sequences ending with a dot, allowing multiple lines
    names = re.findall(r"([^\n]+?\.)", names_block)
    return [n.strip() for n in names]