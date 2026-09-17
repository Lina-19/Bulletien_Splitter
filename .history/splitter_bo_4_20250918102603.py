import re
from typing import List, Optional, Dict
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for terms
KEYWORDS = ["قرار", "مرسوم", "ظهير", "قانون", "ظہیر", "منشور", "مذكرة", "مقرر", "اعلان", "بلاغ", "راي"]
NUMBER_INDICATORS = ["رقم", "عدد"]
DATE_INDICATORS = ["صادر في"]
DATE_END_MARKERS = ["والمتعلق", "و المتعلق", "ب", "المتعلق", "بشأن", "حول", "المتضمن"]

# Signature patterns
SIGNATURE_INDICATORS = ["وحرر ب"]
SIGNATURE_KEYWORDS = ["وقعه بالعطف", "الإمضاء", "إمضاء"]


def build_start_pattern() -> str:
    """Build the regex pattern for the start of legal texts"""
    keywords_pattern = "|".join(re.escape(kw) for kw in KEYWORDS)
    number_indicators_pattern = "|".join(re.escape(ni) for ni in NUMBER_INDICATORS)
    date_indicators_pattern = "|".join(re.escape(di) for di in DATE_INDICATORS)
    date_end_markers_pattern = "|".join(re.escape(dem) for dem in DATE_END_MARKERS)
    
    # More flexible pattern to capture the complete start structure
    pattern = (
        rf"(?P<keyword>{keywords_pattern})\s+"  # keyword
        rf"(?P<text_before_number>.*?)\s+"      # text before number indicator
        rf"(?P<number_indicator>{number_indicators_pattern})\s+"  # رقم or عدد
        rf"(?P<number>[^\s]+(?:\.[^\s]+)*)\s+"  # number (allowing dots for decimals)
        rf"(?P<date_indicator>{date_indicators_pattern})\s+"  # صادر في
        rf"(?P<date>.*?)\s+"                    # date
        rf"(?P<end_marker>{date_end_markers_pattern})"  # end marker
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
            'text_before_number': match.group('text_before_number').strip(),
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


def find_signature_end(text: str, start_pos: int) -> Optional[int]:
    """Find the end position of the signature section"""
    # Look for signature indicator first
    signature_indicators_pattern = "|".join(re.escape(si) for si in SIGNATURE_INDICATORS)
    indicator_pattern = rf"({signature_indicators_pattern})\s+.*?(?:\n|$)"
    
    search_text = text[start_pos:]
    indicator_match = re.search(indicator_pattern, search_text, re.DOTALL)
    
    if not indicator_match:
        return None
    
    # Find the position after the indicator
    after_indicator_pos = start_pos + indicator_match.end()
    
    # Look for signature keywords after the indicator
    signature_keywords_pattern = "|".join(re.escape(sk) for sk in SIGNATURE_KEYWORDS)
    
    # Find all signature keywords and their positions
    remaining_text = text[after_indicator_pos:]
    
    # Look for the last signature in the section
    signature_matches = list(re.finditer(rf"({signature_keywords_pattern})\s*:\s*([^.]+\.)", remaining_text, re.DOTALL))
    
    if signature_matches:
        # Return position after the last signature
        last_match = signature_matches[-1]
        return after_indicator_pos + last_match.end()
    
    # If no signature keywords found, look for names ending with dots after the indicator
    # This handles cases where signature format might be different
    names_pattern = r"([^.\n]+\.[^\n]*)"
    names_matches = list(re.finditer(names_pattern, remaining_text))
    
    if names_matches:
        # Take the last name ending with a dot
        last_name = names_matches[-1]
        return after_indicator_pos + last_name.end()
    
    return None


def extract_complete_legal_texts(text: str) -> List[Dict]:
    """Extract complete legal texts from start pattern to end of signature"""
    # Remove page markers and other non-legal content
    cleaned_text = re.sub(r'=== Page \d+ ===', '', text)
    
    # Find all start patterns
    start_infos = extract_start_info(cleaned_text)
    
    complete_texts = []
    
    for i, start_info in enumerate(start_infos):
        start_pos = start_info['start_position']
        
        # Determine search boundary for signature (don't search beyond next legal text)
        search_end = len(cleaned_text)
        if i + 1 < len(start_infos):
            search_end = start_infos[i + 1]['start_position']
        
        # Find signature end within this boundary
        signature_end = find_signature_end(cleaned_text[:search_end], start_pos)
        
        if signature_end:
            # Extract the complete legal text from start to end of signature
            legal_text = cleaned_text[start_pos:signature_end].strip()
            
            # Clean up the text (remove excessive whitespace, normalize)
            legal_text = re.sub(r'\s+', ' ', legal_text)
            legal_text = re.sub(r'\s*\n\s*', ' ', legal_text)
            
            result = {
                'number': start_info['number'],
                'date': start_info['date'],
                'legal_text': legal_text,
                'start_position': start_pos,
                'end_position': signature_end
            }
            
            complete_texts.append(result)
            logger.info(f"Extracted complete legal text {len(complete_texts)}: {start_info['number']}")
        else:
            logger.warning(f"No signature found for legal text starting with number: {start_info['number']}")
    
    return complete_texts


def save_overview_table(results: List[Dict], output_file: str = 'overview_table.txt'):
    """Save overview table with index, number, and date"""
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write("# Legal Texts Overview\n\n")
            file.write("| Index | Number | Date |\n")
            file.write("|-------|--------|------|\n")
            
            for i, result in enumerate(results, 1):
                number = result.get('number', 'N/A')
                date = result.get('date', 'N/A')
                file.write(f"| {i} | {number} | {date} |\n")
        
        logger.info(f"Overview table saved to '{output_file}' with {len(results)} texts")
        print(f"Overview table saved to '{output_file}' with {len(results)} texts")
    
    except Exception as e:
        logger.error(f"Error saving overview table: {e}")


def save_full_legal_texts(results: List[Dict], output_file: str = 'full_legal_texts.txt'):
    """Save complete legal texts with metadata"""
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write("# Complete Legal Texts\n\n")
            
            for i, result in enumerate(results, 1):
                file.write(f"TEXT {i}\n")
                file.write(f"Number: {result.get('number', 'N/A')}\n")
                file.write(f"Date: {result.get('date', 'N/A')}\n")
                file.write(f"Full Text: {result.get('legal_text', 'No text found')}\n")
                file.write("\n" + "+"*50 + "\n\n")
        
        logger.info(f"Full legal texts saved to '{output_file}' with {len(results)} texts")
        print(f"Full legal texts saved to '{output_file}' with {len(results)} texts")
    
    except Exception as e:
        logger.error(f"Error saving full legal texts: {e}")


def process_file(file_path: str) -> List[Dict]:
    """Process a text file and extract complete legal texts"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        logger.info(f"Successfully read file: {file_path}")
    except FileNotFoundError:
        logger.error(f"File {file_path} not found.")
        return []
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return []
    
    # Extract complete legal texts
    results = extract_complete_legal_texts(content)
    
    return results


# Example usage:
if __name__ == "__main__":
    # Specify the path to your file
    file_path = "data/.txt"
    
    # Process the file
    results = process_file(file_path)
    
    # Print summary
    print(f"\nExtracted {len(results)} complete legal texts from {file_path}")
    
    if results:
        # Show summary of extracted texts
        print("\nExtracted Legal Texts Summary:")
        for i, result in enumerate(results, 1):
            print(f"  {i}. Number: {result.get('number', 'N/A')} | Date: {result.get('date', 'N/A')}")
        
        # Save results to files
        save_overview_table(results, "overview_table.txt")
        save_full_legal_texts(results, "full_legal_texts.txt")
        
        print("\nFiles saved:")
        print("- overview_table.txt (contains the summary table)")
        print("- full_legal_texts.txt (contains complete legal texts)")
        
    else:
        print("No complete legal texts found in the file.")
        print("Make sure the texts follow the pattern: [keyword] + [number] + [date] + [content] + [signature]")