import re
from typing import Dict, Optional, List
from start_pattern import KEYWORDS


SIGNATURE_INDICATORS = ["وحرر"]

SIGNATURE_KEYWORDS_TYPE1 = ["وقعه بالعطف", "الإمضاء", "إمضاء"]
SIGNATURE_KEYWORDS_TYPE2 = ["الإمضاءات"]

SIGNATURE_LIMIT_KEYWORDS = KEYWORDS
SIGNATURE_LIMIT_SPECIALCHARS = ["\*", "=", "-", "\+", "#", ""]
SIGNATURE_LIMIT_ANNEXE_WORDS = ["annexe", "ملحق", "مرفق", "المرفق", "استدراك"]


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
            "type": "Type 1",
            "signature_indicator": indicator or "",
            "key_signature": keyword,
            "names": names_block,
            "limit": limit_val or "",
            "start_position": match.start(),      # add this
            "end_position": limit_pos or len(text) # add this
        })

    # Pattern for type2
    pattern_type2 = rf"({'|'.join(SIGNATURE_KEYWORDS_TYPE2)})\s*:?\s*"
    for match in re.finditer(pattern_type2, text, re.DOTALL):
        keyword = match.group(1)
        names_start = match.end()

        limit_pos, limit_val = find_limit(text, names_start)
        names_block = text[names_start:limit_pos].strip() if limit_pos else text[names_start:].strip()

        results.append({
            "type": "Type 2",
            "signature_indicator": "",
            "key_signature": keyword,
            "names": names_block,
            "limit": limit_val or "",
            "start_position": match.start(),      # add this
            "end_position": limit_pos or len(text) # add this
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
    file_path = "data/BO_7100_Ar.txt"   # input file
    output_file = "extracted_files/extracted_end_info_7100.txt"  # output file

    # Read file content
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract all signature blocks
    results = extract_signatures_from_text(content)
    print(f"Found {len(results)} signature patterns in the file.")

    # Write results to output file
    with open(output_file, "w", encoding="utf-8") as f_out:
        for i, res in enumerate(results, start=1):
            f_out.write(f"TEXT {i}\n")
            f_out.write(f"Type Signature : {res['type']}\n")
            f_out.write(f"Signature Indicator : {res['signature_indicator']}\n")
            f_out.write(f"Key Signature : {res['key_signature']}\n")
            f_out.write(f"Names : {res['names']}\n")
            f_out.write(f"Limit : {res['limit']}\n\n")
            f_out.write("+"*50 + "\n\n")

    print(f"Extraction completed. Results saved to: {output_file}")