import re
from typing import List, Tuple, Optional

def extract_legal_texts(document_content: str) -> List[str]:
    """
    Extract complete legal texts from Moroccan Official Bulletin documents.
    
    Args:
        document_content (str): The content of the document to process
        
    Returns:
        List[str]: List of complete legal texts, each as a separate string
    """
    
    # Keywords that indicate the start of a legal text
    kw = [
        "قرار", "مرسوم", "ظهير", "قانون", "ظہیر",
        "منشور", "مذكرة", "مقرر", "ملحق", 
        "اعلان", "بلاغ", "راي"
    ]
    
    # Clean and normalize the document
    text = clean_document(document_content)
    
    # Find all potential starting positions
    start_positions = find_start_positions(text, kw)
    
    # Find all signature positions
    signature_positions = find_signature_positions(text)
    
    # Match starts with their corresponding signatures
    legal_texts = match_starts_with_signatures(text, start_positions, signature_positions)
    
    return legal_texts

def clean_document(text: str) -> str:
    """Clean and normalize the document text."""

    text = re.sub(r'=== Page \d+ ===\s*', '', text)
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r'###', '', text)  # Remove ### markers
    
    return text

def find_start_positions(text: str, keywords: List[str]) -> List[Tuple[int, str]]:
    """
    Find all positions where legal texts might start.
    
    Returns:
        List of tuples: (position, keyword_found)
    """
    start_positions = []
    
    for keyword in keywords:
        # Look for keyword at start of text or after period/newline
        # This helps avoid matching keywords within other texts
        patterns = [
            rf'(?:^|\. |\n)({keyword}\s+)',  # After sentence end or start
            rf'(?:^)({keyword}\s+)',         # At very beginning
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.MULTILINE)
            for match in matches:
                # Get the actual start position of the keyword
                start_pos = match.start(1) if match.group(1) else match.start()
                start_positions.append((start_pos, keyword))
    
    # Remove duplicates and sort by position
    start_positions = list(set(start_positions))
    start_positions.sort(key=lambda x: x[0])
    
    return start_positions

def find_signature_positions(text: str) -> List[int]:
    """
    Find all signature positions in the text.
    
    Returns:
        List of positions where signatures end
    """
    signature_positions = []
    
    # Pattern to match "الإمضاء" followed by names
    # This looks for the signature word followed by colon and names
    signature_pattern = r'الإمضاء\s*:\s*[^.]+?\.'
    
    matches = re.finditer(signature_pattern, text)
    for match in matches:
        # Store the end position of the signature
        signature_positions.append(match.end())
    
    return sorted(signature_positions)

def match_starts_with_signatures(text: str, start_positions: List[Tuple[int, str]], 
                                signature_positions: List[int]) -> List[str]:
    """
    Match each start position with its corresponding signature to extract complete legal texts.
    """
    legal_texts = []
    
    if not start_positions or not signature_positions:
        return legal_texts
    
    for i, (start_pos, keyword) in enumerate(start_positions):
        # Find the next signature after this start position
        corresponding_signature = None
        
        for sig_pos in signature_positions:
            if sig_pos > start_pos:
                # Check if there's another legal text start between this start and signature
                has_intervening_start = False
                
                for j, (other_start_pos, _) in enumerate(start_positions):
                    if j != i and start_pos < other_start_pos < sig_pos:
                        has_intervening_start = True
                        break
                
                if not has_intervening_start:
                    corresponding_signature = sig_pos
                    break
        
        # If we found a matching signature, extract the text
        if corresponding_signature:
            legal_text = text[start_pos:corresponding_signature].strip()
            
            # Additional validation: check if this looks like a complete legal text
            if is_valid_legal_text(legal_text, keyword):
                legal_texts.append(legal_text)
    
    return legal_texts


def is_valid_legal_text(text: str, keyword: str) -> bool:
    """
    Validate if the extracted text looks like a complete legal document.
    """
    # Basic validation checks
    # if len(text) < 100:  # Too short to be a complete legal text
    #     return False
    
    if not text.startswith(keyword):  # Should start with the keyword
        return False
    
    if 'الإمضاء' not in text:  # Should contain signature
        return False
    
    # Check for common legal text patterns
    # legal_indicators = ['المادة', 'رقم', 'صادر', 'بتاريخ']
    # indicator_count = sum(1 for indicator in legal_indicators if indicator in text)
    
    # if indicator_count < 2:  # Should have at least some legal indicators
    #     return False
    
    return True

def process_document_file(file_path: str) -> List[str]:
    """
    Process a document file and extract legal texts.
    
    Args:
        file_path (str): Path to the document file
        
    Returns:
        List[str]: Extracted legal texts
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return extract_legal_texts(content)
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
        return []
    except Exception as e:
        print(f"Error processing file {file_path}: {str(e)}")
        return []

