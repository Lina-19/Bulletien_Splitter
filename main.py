# arabic_legal_extractor.py
"""
Extract Arabic legal text between start and end patterns using existing logic.
Now also associates each chunk with its page number (based on page markers like '=== Page 24 ===').
"""

import re
import sys
import os
from typing import List, Dict, Optional

try:
    from start_pattern import extract_start_info, KEYWORDS
    from end_pattern import extract_signatures_from_text
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("Make sure start_pattern.py and end_pattern.py are in the same directory")
    sys.exit(1)

# 🔧 NORMALISATION MARKDOWN (solution A)
def normalize_md_headers(text: str) -> str:
    # enlève titres markdown en début de ligne: "# ", "## ", ...
    text = re.sub(r"(?m)^\s*#{1,6}\s+", "", text)

    # enlève bullets en début de ligne: "-", "•", "–", "*", ">"
    text = re.sub(r"(?m)^\s*(?:[-–—•\*>\u2022]+)\s+", "", text)

    # enlève une ligne qui est uniquement en gras markdown **...**
    text = re.sub(r"(?m)^\s*\*\*(.+?)\*\*\s*$", r"\1", text)

    return text


def extract_page_numbers(content: str) -> List[Dict]:
    """
    Extracts page numbers and their positions from the text.
    Expected format: '=== Page 12 ==='
    """
    page_positions = []
    for match in re.finditer(r"===\s*Page\s*(\d+)\s*===", content):
        page_number = int(match.group(1))
        start_pos = match.start()
        page_positions.append({"page_number": page_number, "position": start_pos})
    return page_positions


def get_page_for_position(position: int, page_positions: List[Dict]) -> Optional[int]:
    """
    Finds the page number corresponding to a given text position.
    A chunk belongs to the page where it STARTS (previous page marker).
    """
    current_page = None
    for page in page_positions:
        if position >= page["position"]:
            current_page = page["page_number"]
        else:
            break
    return current_page

def extract_legal_documents(file_path: str) -> List[Dict]:
    """
    Extract legal documents from file using existing pattern detection logic.
    Handles both documents with and without signatures.
    Associates each extracted chunk with its corresponding page number.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        print(f"✅ Successfully read file: {file_path}")
        print(f"📄 File content length: {len(content)} characters")

        # 🔧 NORMALISATION MARKDOWN (ICI EXACTEMENT)
        content = normalize_md_headers(content)

    except FileNotFoundError:
        print(f"❌ File {file_path} not found.")
        return []
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return []

    # Extract page markers
    page_positions = extract_page_numbers(content)
    print(f"📑 Found {len(page_positions)} page markers")

    start_patterns = extract_start_info(content)
    print(f"🔍 Found {len(start_patterns)} start patterns")

    # Separate patterns with and without signatures
    patterns_with_sig = [p for p in start_patterns if p.get('has_signature', True)]
    patterns_without_sig = [p for p in start_patterns if not p.get('has_signature', True)]

    print(f"   ✍️  {len(patterns_with_sig)} with signatures")
    print(f"   📋 {len(patterns_without_sig)} without signatures")

    end_patterns = extract_signatures_from_text(content)
    print(f"✍️ Found {len(end_patterns)} signature patterns")

    # Extract documents with and without signatures
    legal_documents = match_patterns_and_extract(content, patterns_with_sig, end_patterns)
    no_sig_documents = extract_no_signature_documents(content, patterns_without_sig)

    all_documents = legal_documents + no_sig_documents
    all_documents.sort(key=lambda x: x['start_position'])

    # Add page number to each document
    for i, doc in enumerate(all_documents, 1):
        doc['document_number'] = i
        doc['page_number'] = get_page_for_position(doc['start_position'], page_positions)

    print(f"📜 Extracted {len(all_documents)} complete legal documents")
    return all_documents


def extract_no_signature_documents(content: str, start_patterns: List[Dict]) -> List[Dict]:
    """
    Extract legal documents that don't have signatures.
    The end of the document is determined by finding the next legal text keyword.
    """
    documents = []
    keyword_pattern = rf"^(?P<limit>{'|'.join(KEYWORDS)})(?=\s|$|[،:؛\.\)])"

    for i, pattern in enumerate(start_patterns):
        full_match = pattern.get('full_match', '')
        if not full_match:
            continue

        start_pos = content.find(full_match)
        if start_pos == -1:
            continue

        end_pos = start_pos + len(full_match)
        remaining_text = content[end_pos:]
        next_keyword_match = re.search(keyword_pattern, remaining_text, flags=re.MULTILINE)

        if next_keyword_match:
            limit_pos = end_pos + next_keyword_match.start()
        else:
            limit_pos = min(end_pos + 2000, len(content))

        legal_text = content[start_pos:limit_pos].strip()

        if len(legal_text) > 50:
            documents.append({
                'document_number': i + 1,
                'start_pattern': pattern,
                'end_pattern': {
                    'type': 'No Signature',
                    'key_signature': 'N/A',
                    'names': 'N/A',
                    'limit': next_keyword_match.group(1) if next_keyword_match else 'End of text'
                },
                'legal_text': legal_text,
                'start_position': start_pos,
                'end_position': limit_pos,
                'text_length': len(legal_text),
                'has_signature': False
            })
    return documents


def match_patterns_and_extract(content: str, start_patterns: List[Dict], end_patterns: List[Dict]) -> List[Dict]:
    """
    Match start patterns with corresponding end patterns and extract legal text.
    """
    legal_documents = []
    start_positions = []
    for i, pattern in enumerate(start_patterns):
        full_match = pattern.get('full_match', '')
        if full_match:
            pos = content.find(full_match)
            if pos != -1:
                start_positions.append({
                    'index': i,
                    'pattern': pattern,
                    'position': pos,
                    'end_position': pos + len(full_match)
                })

    start_positions.sort(key=lambda x: x['position'])

    for i, start_info in enumerate(start_positions):
        start_pos = start_info['end_position']
        best_end = None
        min_distance = float('inf')

        for end_pattern in end_patterns:
            end_start_pos = end_pattern.get('start_position', 0)
            if end_start_pos > start_pos:
                distance = end_start_pos - start_pos
                interfering_start = any(start_pos < other['position'] < end_start_pos for other in start_positions if other != start_info)
                if not interfering_start and distance < min_distance:
                    min_distance = distance
                    best_end = end_pattern

        if best_end:
            start_pattern_pos = start_info['position']
            end_pattern_end_pos = best_end.get('end_position', len(content))
            complete_legal_text = content[start_pattern_pos:end_pattern_end_pos].strip()

            if len(complete_legal_text) > 50:
                legal_documents.append({
                    'document_number': i + 1,
                    'start_pattern': start_info['pattern'],
                    'end_pattern': best_end,
                    'legal_text': complete_legal_text,
                    'start_position': start_pattern_pos,
                    'end_position': end_pattern_end_pos,
                    'text_length': len(complete_legal_text),
                    'has_signature': True
                })
    return legal_documents


def save_extracted_documents(documents: List[Dict], output_file: str):
    """
    Save extracted legal texts with page numbers.
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for doc in documents:
                f.write(f"Page {doc.get('page_number', 'Unknown')}\n")
                f.write("-" * 40 + "\n")
                f.write(doc['legal_text'].strip() + "\n\n")
                f.write("=" * 80 + "\n\n")

        print(f"✅ Extracted texts with page numbers saved to: {output_file}")
    except Exception as e:
        print(f"❌ Error saving results: {e}")


def main():
    """
    Main entry point.
    """
    print("🕌 Arabic Legal Text Extractor (with page numbers)")
    print("=" * 50)

    if len(sys.argv) < 2:
        print("❌ Usage: python3 main.py <path_to_input_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    file_name = os.path.basename(input_file)
    output_file = os.path.join("extracted_files", f"{os.path.splitext(file_name)[0]}_extracted.txt")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    documents = extract_legal_documents(input_file)
    if documents:
        save_extracted_documents(documents, output_file)
        print(f"\n🎉 Successfully extracted {len(documents)} documents!")
        print(f"📂 Saved to: {output_file}")
    else:
        print("❌ No legal documents could be extracted.")


if __name__ == "__main__":
    main()
