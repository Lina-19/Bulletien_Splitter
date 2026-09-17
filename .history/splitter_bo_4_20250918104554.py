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
DATE_END_MARKERS = ["في", "قرر", "والمتعلق", "و المتعلق", "ب", "المتعلق", "بشأن", "حول", "المتضمن"]

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
    search_text = text[start_pos:]
    
    # Look for signature indicator "وحرر ب"
    signature_indicators_pattern = "|".join(re.escape(si) for si in SIGNATURE_INDICATORS)
    indicator_pattern = rf"({signature_indicators_pattern})"
    
    indicator_match = re.search(indicator_pattern, search_text)
    
    if not indicator_match:
        return None
    
    # Find the position where signature starts
    signature_start_pos = start_pos + indicator_match.start()
    
    # From the signature indicator, find the rest of the signature section
    remaining_text = text[signature_start_pos:]
    
    # Look for the pattern: الإمضاء : [name].
    # This handles both direct signatures and "وقعه بالعطف" signatures
    signature_end_pos = signature_start_pos
    
    # Find all instances of "الإمضاء : [name]." pattern
    signature_pattern = r"الإمضاء\s*:\s*([^.]+\.)"
    signature_matches = list(re.finditer(signature_pattern, remaining_text))
    
    if signature_matches:
        # Take the end of the last signature match
        last_signature = signature_matches[-1]
        signature_end_pos = signature_start_pos + last_signature.end()
    else:
        # If no "الإمضاء" found, look for any name ending with dot after "وحرر ب"
        # This is a fallback for different signature formats
        names_pattern = r"([^.\n]+\.)"
        names_matches = list(re.finditer(names_pattern, remaining_text))
        
        if names_matches:
            # Take the last name ending with dot
            last_name = names_matches[-1]
            signature_end_pos = signature_start_pos + last_name.end()
        else:
            # If no names with dots, take a reasonable amount after indicator
            signature_end_pos = signature_start_pos + min(500, len(remaining_text))
    
    return signature_end_pos


def extract_complete_legal_texts(text: str) -> List[Dict]:
    """Extract complete legal texts from start pattern to end of signature"""
    cleaned_text = re.sub(r'=== Page \d+ ===', '', text)

    start_infos = extract_start_info(cleaned_text)
    complete_texts = []

    for i, start_info in enumerate(start_infos):
        start_pos = start_info['start_position']

        # limit search to before next start pattern
        search_end = len(cleaned_text)
        if i + 1 < len(start_infos):
            search_end = start_infos[i + 1]['start_position']

        # find signature end
        signature_end = find_signature_end(cleaned_text[:search_end], start_pos)

        if signature_end:
            legal_text = cleaned_text[start_pos:signature_end].strip()
            # legal_text = re.sub(r'\s+', ' ', legal_text) # normalize spaces
            legal_text = re.sub(r'[ \t]+', ' ', legal_text) 

            result = {
                'number': start_info['number'],
                'date': start_info['date'],
                'legal_text': legal_text,
                'start_position': start_pos,
                'end_position': signature_end
            }
            complete_texts.append(result)
        else:
            # skip texts without proper signature
            continue

    return complete_texts


def save_overview_table(results: List[Dict], output_file: str = 'overview_table.txt'):
    """Save overview table with index, number, and date"""
    with open(output_file, 'w', encoding='utf-8') as file:
        file.write("| Index | Number | Date |\n")
        file.write("|-------|--------|------|\n")
        for i, result in enumerate(results, 1):
            file.write(f"| {i} | {result['number']} | {result['date']} |\n")


def save_full_legal_texts(results: List[Dict], output_file: str = 'full_legal_texts.txt'):
    """Save complete legal texts with metadata"""
    with open(output_file, 'w', encoding='utf-8') as file:
        for i, result in enumerate(results, 1):
            file.write(f"TEXT {i}\n")
            file.write(f"Number : {result['number']}\n")
            file.write(f"Date   : {result['date']}\n")
            # file.write(f"Full Text : {result['legal_text']}\n")
            # file.write("\n" + "+"*50 + "\n\n")

            file.write("Full Text :\n")
            file.write(result['legal_text'] + "\n")
            file.write("\n" + "+"*50 + "\n\n")

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
    file_path = "data/BO_7100_Ar.txt"
    
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