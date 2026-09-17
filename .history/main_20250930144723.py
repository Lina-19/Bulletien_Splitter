# arabic_legal_extractor.py
"""
Extract Arabic legal text between start and end patterns using existing logic.
Handles both texts with signatures and texts without signatures.
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


def extract_legal_documents(file_path: str) -> List[Dict]:
    """
    Extract legal documents from file using existing pattern detection logic.
    Handles both documents with and without signatures.
    """
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"✅ Successfully read file: {file_path}")
        print(f"📄 File content length: {len(content)} characters")
    except FileNotFoundError:
        print(f"❌ File {file_path} not found.")
        return []
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return []
    
    start_patterns = extract_start_info(content)
    print(f"🔍 Found {len(start_patterns)} start patterns")
    
    # Separate patterns with and without signatures
    patterns_with_sig = [p for p in start_patterns if p.get('has_signature', True)]
    patterns_without_sig = [p for p in start_patterns if not p.get('has_signature', True)]
    
    print(f"   ✍️  {len(patterns_with_sig)} with signatures")
    print(f"   📋 {len(patterns_without_sig)} without signatures")
    
    end_patterns = extract_signatures_from_text(content)
    print(f"✍️ Found {len(end_patterns)} signature patterns")
    
    # Extract documents with signatures
    legal_documents = match_patterns_and_extract(content, patterns_with_sig, end_patterns)
    
    # Extract documents without signatures
    no_sig_documents = extract_no_signature_documents(content, patterns_without_sig)
    
    # Combine both types and sort by position
    all_documents = legal_documents + no_sig_documents
    all_documents.sort(key=lambda x: x['start_position'])
    
    # Renumber documents sequentially
    for i, doc in enumerate(all_documents, 1):
        doc['document_number'] = i
    
    print(f"📜 Extracted {len(all_documents)} complete legal documents")
    print(f"   ✍️  {len(legal_documents)} with signatures")
    print(f"   📋 {len(no_sig_documents)} without signatures")
    
    return all_documents


def extract_no_signature_documents(content: str, start_patterns: List[Dict]) -> List[Dict]:
    """
    Extract legal documents that don't have signatures.
    The end of the document is determined by finding the next legal text keyword.
    """
    documents = []
    
    # Build pattern to find next legal text
    keyword_pattern = rf"^(?P<limit>{'|'.join(KEYWORDS)})(?=\s|$|[،:؛\.\)])"
    
    for i, pattern in enumerate(start_patterns):
        full_match = pattern.get('full_match', '')
        if not full_match:
            continue
        
        start_pos = content.find(full_match)
        if start_pos == -1:
            continue
        
        end_pos = start_pos + len(full_match)
        
        # Find the next legal text keyword as the limit
        remaining_text = content[end_pos:]
        next_keyword_match = re.search(keyword_pattern, remaining_text, flags=re.MULTILINE)
        
        if next_keyword_match:
            # End at the next keyword
            limit_pos = end_pos + next_keyword_match.start()
        else:
            # If no next keyword, take a reasonable chunk (e.g., 2000 chars)
            limit_pos = min(end_pos + 2000, len(content))
        
        legal_text = content[start_pos:limit_pos].strip()
        
        if len(legal_text) > 50:  # Minimum threshold
            documents.append({
                'document_number': i + 1,  # Will be renumbered later
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
                
                interfering_start = False
                for j, other_start in enumerate(start_positions):
                    if j != i and start_pos < other_start['position'] < end_start_pos:
                        interfering_start = True
                        break
                
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
    Save extracted legal documents to a file.
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("EXTRACTED ARABIC LEGAL DOCUMENTS\n")
            f.write("=" * 80 + "\n\n")
            
            for doc in documents:
                f.write(f"📄 TEXT {doc['document_number']}\n")
                f.write("\n")
                
                start = doc['start_pattern']
                f.write(f"• Keyword: {start.get('keyword', 'N/A')}\n")
                
                # Show number and date for all texts (both with and without signatures)
                if start.get('number'):
                    f.write(f"• Number: {start.get('number', 'N/A')}\n")
                if start.get('date'):
                    f.write(f"• Date: {start.get('date', 'N/A')}\n")
                
                end = doc['end_pattern']
                f.write(f"• Key Signature: {end.get('key_signature', 'N/A')}\n")
                
                if end.get('key_signature') != 'N/A':
                    f.write(f"• Names: {end.get('names', 'N/A')}\n")
                
                f.write("\n")
                f.write("• LEGAL TEXT:\n")
                f.write(doc['legal_text'] + "\n\n")
                f.write("\n" + "+" * 80 + "\n\n")
        
        print(f"✅ Extracted documents saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error saving results: {e}")


def main():
    """
    Main function to extract Arabic legal documents.
    """
    print("🕌 Arabic Legal Text Extractor")
    print("=" * 50)
    
    input_file = "data/BO_7069_Ar.txt"
    output_file = "extracted_files/7069_extracted.txt"
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    documents = extract_legal_documents(input_file)
    
    if documents:
        save_extracted_documents(documents, output_file)
        
        print("\n📊 EXTRACTION SUMMARY:")
        print("-" * 30)
        for i, doc in enumerate(documents, 1):
            sig_status = "📋 No Signature" if not doc.get('has_signature', True) else "✍️  With Signature"
            print(f"Document {i}: {sig_status}")
            print(f"  📖 {doc['start_pattern'].get('keyword', 'N/A')} "
                  f"{doc['start_pattern'].get('number', 'N/A')}")
            if doc.get('has_signature', True):
                print(f"  ✍️  {doc['end_pattern'].get('key_signature', 'N/A')}")
            print()
        
        print(f"🎉 Successfully extracted {len(documents)} legal documents!")
    else:
        print("❌ No legal documents could be extracted.")


if __name__ == "__main__":
    main()