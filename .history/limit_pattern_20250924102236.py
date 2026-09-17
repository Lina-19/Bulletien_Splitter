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





def find_limit(text: str, start_pos: int) -> Optional[int]:
    """
    Detect the first occurrence of a limit condition after start_pos.
    """
    remaining_text = text[start_pos:]

    # Check for new keyword
    keyword_pattern = rf"({'|'.join(SIGNATURE_LIMIT_KEYWORDS)})"
    keyword_match = re.search(keyword_pattern, remaining_text)

    # Check for special chars
    special_pattern = rf"({'|'.join(map(re.escape, SIGNATURE_LIMIT_SPECIAL_CHARS))})"
    special_match = re.search(special_pattern, remaining_text)

    # Check for annex words
    annex_pattern = rf"({'|'.join(SIGNATURE_LIMIT_ANNEXE_WORDS)})"
    annex_match = re.search(annex_pattern, remaining_text)

    # Collect matches and return earliest
    matches = [
        (keyword_match.start(), "keyword") if keyword_match else None,
        (special_match.start(), "special") if special_match else None,
        (annex_match.start(), "annex") if annex_match else None,
    ]
    matches = [m for m in matches if m]

    if matches:
        min_pos, mtype = min(matches, key=lambda x: x[0])
        return start_pos + min_pos

    return None



if __name__ == "__main__":
    import sys

    # Ask user for the file path or use a default
    file_path = "data/test.txt"
    if not file_path:
        print("❌ No file path provided.")
        sys.exit(1)

    # Read the file content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
        print(f"✅ Successfully read file: {file_path}")
        print(f"File content length: {len(text_content)} characters")
    except FileNotFoundError:
        print(f"❌ File {file_path} not found.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)

    # Extract start info
    results = extract_start_info(text_content)
    print(f"Found {len(results)} start patterns in the file.")

    # Save results to a file
    output_file = "extracted_files/extracted_start_info_test.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, r in enumerate(results, 1):
            f.write(f"TEXT {i}\n")
            f.write(f"Keyword: {r.get('keyword', '')}\n")
            f.write(f"Number Indicator: {r.get('number_indicator', '')}\n")
            f.write(f"Number: {r.get('number', '')}\n")
            f.write(f"Date Indicator: {r.get('date_indicator', '')}\n")
            f.write(f"Date: {r.get('date', '')}\n")
            f.write(f"End Marker: {r.get('end_marker', '')}\n")
            f.write(f"Full Match: {r.get('full_match', '')}\n")
            # f.write(f"Position: {r.get('start_position', '')}-{r.get('end_position', '')}\n")





            sig_info = find_signature(text_content, r['full_match'].rfind(r['date']))
            if sig_info:
                f.write("\n--- SIGNATURE INFO ---\n")
                f.write(f"Signature Type: {sig_info.get('signature_type', '')}\n")
                f.write(f"Signature Keyword: {sig_info.get('signature_keyword', '')}\n")
                f.write(f"Names: {', '.join(sig_info.get('names', []))}\n")
            else:
                f.write("\n(No signature found)\n")

            f.write("\n" + "+"*50 + "\n\n")





    print(f"✅ Extracted start info saved to {output_file}")