# arabic_legal_extractor.py
"""
Extract Arabic legal text between start and end patterns using existing logic.
This script imports and uses your existing start_pattern.py and end_pattern.py files.
"""

import sys
import os
from typing import List, Dict, Optional

# Import your existing modules
try:
    from start_pattern import extract_start_info
    from end_pattern import extract_signatures_from_text
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("Make sure start_pattern.py and end_pattern.py are in the same directory")
    sys.exit(1)


def extract_legal_documents(file_path: str) -> List[Dict]:
    """
    Extract legal documents from file using your existing pattern detection logic.
    
    Args:
        file_path: Path to the Arabic legal text file
        
    Returns:
        List of dictionaries containing extracted legal documents
    """
    
    # Read the file
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
    
    # Use your existing logic to find start patterns
    start_patterns = extract_start_info(content)
    print(f"🔍 Found {len(start_patterns)} start patterns")
    
    # Use your existing logic to find end patterns (signatures)
    end_patterns = extract_signatures_from_text(content)
    print(f"✍️ Found {len(end_patterns)} signature patterns")
    
    # Match start and end patterns to extract legal documents
    legal_documents = match_patterns_and_extract(content, start_patterns, end_patterns)
    print(f"📜 Extracted {len(legal_documents)} complete legal documents")
    
    return legal_documents


def match_patterns_and_extract(content: str, start_patterns: List[Dict], end_patterns: List[Dict]) -> List[Dict]:
    """
    Match start patterns with corresponding end patterns and extract legal text.
    """
    legal_documents = []
    
    # Create positions for start patterns
    start_positions = []
    for i, pattern in enumerate(start_patterns):
        # Find the position of this start pattern in the content
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
    
    # Sort start positions by their position in text
    start_positions.sort(key=lambda x: x['position'])
    
    # For each start pattern, find the corresponding end pattern
    for i, start_info in enumerate(start_positions):
        start_pos = start_info['end_position']  # End of start pattern
        
        # Find the best matching end pattern after this start
        best_end = None
        min_distance = float('inf')
        
        for end_pattern in end_patterns:
            end_start_pos = end_pattern.get('start_position', 0)
            
            # End pattern must come after start pattern
            if end_start_pos > start_pos:
                distance = end_start_pos - start_pos
                
                # Check if there's no other start pattern between this start and end
                interfering_start = False
                for j, other_start in enumerate(start_positions):
                    if j != i and start_pos < other_start['position'] < end_start_pos:
                        interfering_start = True
                        break
                
                # If no interfering start and this is the closest end, select it
                if not interfering_start and distance < min_distance:
                    min_distance = distance
                    best_end = end_pattern
        
        # Extract legal text if we found a matching end pattern
        if best_end:

            # end_pos = best_end.get('start_position', len(content))
            # legal_text = content[start_pos:end_pos].strip()

            # Include the complete start pattern in the legal text
            start_pattern_pos = start_info['position']  # Beginning of start pattern
    
            # Include the complete end pattern in the legal text  
            end_pattern_end_pos = best_end.get('end_position', len(content))  # End AFTER signature
    
            # Extract complete legal text (start pattern + middle content + end pattern)
            complete_legal_text = content[start_pattern_pos:end_pattern_end_pos].strip()
            
            # Only include if there's substantial content
            if len(complete_legal_text) > 50:  # Minimum threshold
                legal_documents.append({
                    'document_number': i + 1,
                    'start_pattern': start_info['pattern'],
                    'end_pattern': best_end,
                    'legal_text': complete_legal_text,
                    'start_position': start_pattern_pos,
                    'end_position': end_pattern_end_pos,
                    'text_length': len(complete_legal_text)
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
                # f.write("-" * 40 + "\n")
                
                # Start pattern info
                start = doc['start_pattern']
                # f.write("🔍 START PATTERN:\n")
                f.write(f"• Keyword: {start.get('keyword', 'N/A')}\n")
                f.write(f"• Number: {start.get('number', 'N/A')}\n")
                f.write(f"• Date: {start.get('date', 'N/A')}\n")
                # f.write(f"   Key Signature: {end.get('key_signature', 'N/A')}\n")
                # f.write(f"   Full Match: {start.get('full_match', 'N/A')}\n")
                # f.write("\n")
                
                # End pattern info
                end = doc['end_pattern']
                # f.write("✍️ END PATTERN:\n")
                # f.write(f"   Type: {end.get('type', 'N/A')}\n")
                f.write(f"• Key Signature: {end.get('key_signature', 'N/A')}\n")
                # f.write(f"   Names: {end.get('names', 'N/A')[:200]}{'...' if len(end.get('names', '')) > 200 else ''}\n")
                f.write(f"• Names: {end.get('names', 'N/A')}\n")
                f.write("\n")
                
                # Document stats
                # f.write("📊 DOCUMENT INFO:\n")
                # f.write(f"   Text Length: {doc['text_length']} characters\n")
                # f.write(f"   Position: {doc['start_position']}-{doc['end_position']}\n")
                # f.write("\n")
                
                # Legal text content
                # f.write("📜 LEGAL TEXT:\n")
                f.write("• LEGAL TEXT:\n")
                # f.write("─" * 60 + "\n")
                # f.write(doc['legal_text'])
                f.write(doc['legal_text'] + "\n\n")
                # f.write("\n" + "─" * 60 + "\n")
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
    
    # File paths - modify these as needed
    input_file = "data/BO_7100_Ar.txt"  # Change to your input file
    output_file = "extracted_files/7061_extracted.txt"
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Extract legal documents
    documents = extract_legal_documents(input_file)
    
    if documents:
        # Save results
        save_extracted_documents(documents, output_file)
        
        # Print summary
        print("\n📊 EXTRACTION SUMMARY:")
        print("-" * 30)
        for i, doc in enumerate(documents, 1):
            print(f"Document {i}:")
            print(f"  📖 {doc['start_pattern'].get('keyword', 'N/A')} "
                  f"{doc['start_pattern'].get('number', 'N/A')}")
            # print(f"  📏 {doc['text_length']} characters")
            print(f"  ✍️  {doc['end_pattern'].get('key_signature', 'N/A')}")
            print()
        
        print(f"🎉 Successfully extracted {len(documents)} legal documents!")
    else:
        print("❌ No legal documents could be extracted.")
        print("   Check if start and end patterns are being detected correctly.")


def extract_single_document_between_patterns(content: str, start_keyword: str, end_signature: str) -> Optional[str]:
    """
    Extract a single legal document between specific start and end patterns.
    Useful for targeted extraction.
    """
    start_patterns = extract_start_info(content)
    end_patterns = extract_signatures_from_text(content)
    
    # Find matching start pattern
    start_match = None
    for pattern in start_patterns:
        if start_keyword.lower() in pattern.get('keyword', '').lower():
            start_match = pattern
            break
    
    if not start_match:
        return None
    
    # Find matching end pattern
    end_match = None
    for pattern in end_patterns:
        if end_signature.lower() in pattern.get('key_signature', '').lower():
            end_match = pattern
            break
    
    if not end_match:
        return None
    
    # Extract text between patterns
    full_match = start_match.get('full_match', '')
    start_pos = content.find(full_match)
    if start_pos == -1:
        return None
    
    start_end = start_pos + len(full_match)
    end_start = end_match.get('start_position', len(content))
    
    if end_start > start_end:
        return content[start_end:end_start].strip()
    
    return None


if __name__ == "__main__":
    main()