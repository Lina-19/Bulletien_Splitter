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

    text = re.sub(r'=== Page \d+ ===', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
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

