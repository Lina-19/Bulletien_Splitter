import re
from typing import List, Optional, Dict

# Global variables for terms (easier to modify)
KEYWORDS = [
    "قرار", "مرسوم", "ظهير", "قانون", "ظہیر", 
    "منشور", "مذكرة", "مقرر", "اعلان", "بلاغ", "راي"
]

NUMBER_INDICATORS = ["رقم", "عدد"]

DATE_INDICATORS = ["صادر في"]

DATE_END_MARKERS = ["ب", "المتعلق", "بشأن", "حول", "المتضمن"]




# def add_keyword(keyword: str) -> None:
#     """Add a new keyword to the keywords list"""
#     if keyword not in KEYWORDS:
#         KEYWORDS.append(keyword)

# def add_number_indicator(indicator: str) -> None:
#     """Add a new number indicator to the list"""
#     if indicator not in NUMBER_INDICATORS:
#         NUMBER_INDICATORS.append(indicator)

# def add_date_indicator(indicator: str) -> None:
#     """Add a new date indicator to the list"""
#     if indicator not in DATE_INDICATORS:
#         DATE_INDICATORS.append(indicator)

# def add_date_end_marker(marker: str) -> None:
#     """Add a new date end marker to the list"""
#     if marker not in DATE_END_MARKERS:
#         DATE_END_MARKERS.append(marker)





def build_start_pattern() -> str:
    """Build the regex pattern for the start of legal texts"""
    # Create pattern components
    keywords_pattern = "|".join(KEYWORDS)
    number_indicators_pattern = "|".join(NUMBER_INDICATORS)
    date_indicators_pattern = "|".join(DATE_INDICATORS)
    date_end_markers_pattern = "|".join(DATE_END_MARKERS)
    
    # Build the complete pattern
    pattern = (
        rf"(?P<keyword>{keywords_pattern})\s*"  # keyword
        rf"(?P<text1>.*?)\s*"                   # optional text1
        rf"(?P<number_indicator>{number_indicators_pattern})\s+"  # رقم or عدد
        rf"(?P<number>[^\s]+(?:\s+[^\s]+)*?)\s+"  # text2 (number)
        rf"(?P<date_indicator>{date_indicators_pattern})\s+"  # صادر في
        rf"(?P<date>.*?)\s+"                     # date (hijri + christian)
        rf"(?P<end_marker>{date_end_markers_pattern})"  # arabic letter/word
    )
    
    return pattern

def extract_start_info(text: str) -> List[Dict]:
    """Extract information from the start patterns in the text"""
    pattern = build_start_pattern()
    matches = re.finditer(pattern, text, re.DOTALL)
    
    results = []
    for match in matches:
        result = {
            'full_match': match.group(0),
            'keyword': match.group('keyword').strip(),
            'text1': match.group('text1').strip() if match.group('text1') else '',
            'number_indicator': match.group('number_indicator').strip(),
            'number': match.group('number').strip(),
            'date_indicator': match.group('date_indicator').strip(),
            'date': match.group('date').strip(),
            'end_marker': match.group('end_marker').strip(),
            'start_position': match.start(),
            'end_position': match.end()
        }
        results.append(result)
    
    return results














def find_signature_pattern(text: str, start_pos: int = 0) -> Optional[int]:
    """Find the position of signature pattern after start_pos"""
    # Common signature patterns in Arabic legal texts
    signature_patterns = [
        r"وزير\s+.*?[،\.]",
        r"الوزير\s+الأول[،\.]",
        r"رئيس\s+الحكومة[،\.]",
        r"الملك[،\.]",
        r"جلالة\s+الملك[،\.]",
        r"توقيع",
        r"إمضاء",
    ]
    
    for pattern in signature_patterns:
        match = re.search(pattern, text[start_pos:])
        if match:
            return start_pos + match.end()
    
    return None

def extract_legal_text(text: str, start_info: Dict, signature_pos: Optional[int]) -> str:
    """Extract the complete legal text from start pattern to signature"""
    start_pos = start_info['start_position']
    
    if signature_pos:
        return text[start_pos:signature_pos].strip()
    else:
        # If no signature found, try to find next legal text start
        next_starts = extract_start_info(text[start_pos + len(start_info['full_match']):])
        if next_starts:
            next_pos = start_pos + len(start_info['full_match']) + next_starts[0]['start_position']
            return text[start_pos:next_pos].strip()
        else:
            # Return from start to end of text
            return text[start_pos:].strip()

def process_file(file_path: str) -> List[Dict]:
    """Process a text file and extract all legal texts"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except FileNotFoundError:
        print(f"File {file_path} not found.")
        return []
    except Exception as e:
        print(f"Error reading file: {e}")
        return []
    
    # Extract all start patterns
    start_infos = extract_start_info(content)
    
    results = []
    for i, start_info in enumerate(start_infos):
        # Find signature for this legal text
        search_start = start_info['end_position']
        
        # Limit search to before next legal text if exists
        search_end = len(content)
        if i + 1 < len(start_infos):
            search_end = start_infos[i + 1]['start_position']
        
        signature_pos = find_signature_pattern(
            content[:search_end], 
            search_start
        )
        
        # Extract the complete legal text
        legal_text = extract_legal_text(content, start_info, signature_pos)
        
        result = {
            **start_info,  # Include all start pattern info
            'legal_text': legal_text,
            'signature_position': signature_pos,
            'text_length': len(legal_text)
        }
        
        results.append(result)
    
    return results

def print_results(results: List[Dict]) -> None:
    """Print extracted results in a readable format"""
    for i, result in enumerate(results, 1):
        print(f"\n{'='*50}")
        print(f"Legal Text #{i}")
        print(f"{'='*50}")
        print(f"Keyword: {result['keyword']}")
        print(f"Number Indicator: {result['number_indicator']}")
        print(f"Number: {result['number']}")
        print(f"Date: {result['date']}")
        print(f"Text Length: {result['text_length']} characters")
        print(f"\nFull Text Preview (first 200 chars):")
        print(result['legal_text'][:200] + "..." if len(result['legal_text']) > 200 else result['legal_text'])






















# Example usage:
if __name__ == "__main__":
    # Add new terms if needed
    add_number_indicator("تحت")  # Example: adding a new number indicator
    add_keyword("تعليمة")        # Example: adding a new keyword
    
    # Process a file
    # results = process_file("legal_texts.txt")
    
    # Print results
    # print_results(results)
    
    # Example of testing the pattern
    sample_text = """
    قرار وزاري رقم 2.22.195 صادر في 25 من شعبان 1443 (28 مارس 2022) بشأن تنظيم الخدمات العمومية...
    
    مرسوم عدد 0025/ق/2022 صادر في 29 من شعبان 1443 (فاتح أبريل 2022) ب المتعلق بالتنظيم الإداري...
    """
    
    results = extract_start_info(sample_text)
    print_results(results)