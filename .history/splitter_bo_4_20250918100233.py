import re
from typing import List, Optional, Dict
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables for terms (easier to modify)
KEYWORDS = ["قرار", "مرسوم", "ظهير", "قانون", "ظہیر", "منشور", "مذكرة", "مقرر", "اعلان", "بلاغ", "راي"]

NUMBER_INDICATORS = ["رقم", "عدد"]
DATE_INDICATORS = ["صادر في"]
DATE_END_MARKERS = ["والمتعلق", "و المتعلق", "ب", "المتعلق", "بشأن", "حول", "المتضمن"]

# Signature patterns
SIGNATURE_INDICATORS = ["وحرر ب"]
SIGNATURE_KEYWORDS = ["وقعه بالعطف", "الإمضاء", "إمضاء"]
SIGNATURE_LIMIT_KEYWORDS = KEYWORDS
SIGNATURE_LIMIT_SPECIAL_CHARS = ["*", "=", "_", "-", "+", "#"]
SIGNATURE_LIMIT_ANNEXE_WORDS = ["annexe", "ملحق", "مرفق", "المرفق"]


def build_start_pattern() -> str:
    """Build the regex pattern for the start of legal texts"""
    # Create pattern components
    keywords_pattern = "|".join(re.escape(kw) for kw in KEYWORDS)
    number_indicators_pattern = "|".join(re.escape(ni) for ni in NUMBER_INDICATORS)
    date_indicators_pattern = "|".join(re.escape(di) for di in DATE_INDICATORS)
    date_end_markers_pattern = "|".join(re.escape(dem) for dem in DATE_END_MARKERS)
    
    # Build the complete pattern with better matching
    pattern = (
        rf"(?P<keyword>{keywords_pattern})\s*"  # keyword
        rf"(?P<text1>.*?)\s*"                   # optional text1
        rf"(?P<number_indicator>{number_indicators_pattern})\s+"  # رقم or عدد
        rf"(?P<number>[^\s]+(?:\s+[^\s]+)*?)\s+"  # number
        rf"(?P<date_indicator>{date_indicators_pattern})\s+"  # صادر في
        rf"(?P<date>.*?)\s*"                     # date (hijri + christian)
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


def find_signature_pattern(text: str, start_pos: int = 0) -> Optional[Dict]:
    """Find signature pattern after start_pos"""
    # Build patterns with proper escaping
    signature_indicators = "|".join(re.escape(si) for si in SIGNATURE_INDICATORS)
    signature_keywords = "|".join(re.escape(sk) for sk in SIGNATURE_KEYWORDS)
    limit_keywords = "|".join(re.escape(lk) for lk in SIGNATURE_LIMIT_KEYWORDS)
    limit_special_chars = "|".join(re.escape(char) for char in SIGNATURE_LIMIT_SPECIAL_CHARS)
    limit_annexe_words = "|".join(re.escape(aw) for aw in SIGNATURE_LIMIT_ANNEXE_WORDS)
    
    # Pattern for signature indicator line (وحرر ب + text)
    indicator_pattern = rf"(?P<indicator>{signature_indicators})\s*(?P<indicator_text>.*?)(?:\n|$)"
    
    # Find the indicator line first
    search_text = text[start_pos:]
    indicator_match = re.search(indicator_pattern, search_text, re.DOTALL)
    if not indicator_match:
        return None
    
    indicator_end_pos = start_pos + indicator_match.end()
    
    # Now look for the signature keyword after the indicator
    keyword_pattern = rf"(?P<keyword>{signature_keywords})\s*:\s*"
    keyword_search_text = text[indicator_end_pos:]
    keyword_match = re.search(keyword_pattern, keyword_search_text, re.DOTALL)
    if not keyword_match:
        return None
    
    keyword_end_pos = indicator_end_pos + keyword_match.end()
    
    # Extract names until we hit a limit
    remaining_text = text[keyword_end_pos:]
    
    # Find the limit position
    limit_pattern = rf"(?P<limit_keyword>{limit_keywords})|(?P<limit_special>{limit_special_chars})|(?P<limit_annexe>{limit_annexe_words})"
    limit_match = re.search(limit_pattern, remaining_text, re.DOTALL)
    
    if limit_match:
        signature_end_pos = keyword_end_pos + limit_match.start()
        limit_info = {
            'type': 'keyword' if limit_match.group('limit_keyword') else 
                   'special' if limit_match.group('limit_special') else 'annexe',
            'value': (limit_match.group('limit_keyword') or 
                     limit_match.group('limit_special') or 
                     limit_match.group('limit_annexe'))
        }
    else:
        # If no limit found, take reasonable amount of text
        signature_end_pos = min(keyword_end_pos + 1000, len(text))
        limit_info = None
    
    # Extract names from the signature section
    signature_text = text[keyword_end_pos:signature_end_pos]
    
    # Pattern to find names ending with dots
    name_pattern = r"([^.\n]+)\."
    name_matches = re.findall(name_pattern, signature_text)
    
    # Clean up names (remove extra whitespace and newlines)
    names = [name.strip().replace('\n', ' ').replace('  ', ' ') for name in name_matches if name.strip()]
    
    return {
        'type': 'signature',
        'full_match': text[start_pos + indicator_match.start():signature_end_pos],
        'indicator': indicator_match.group('indicator').strip(),
        'indicator_text': indicator_match.group('indicator_text').strip(),
        'keyword': keyword_match.group('keyword').strip(),
        'names': names,
        'limit_info': limit_info,
        'start_position': start_pos + indicator_match.start(),
        'end_position': signature_end_pos
    }


def extract_legal_text(text: str, start_info: Dict, signature_info: Optional[Dict]) -> str:
    """Extract the complete legal text from start pattern to signature"""
    start_pos = start_info['start_position']
    
    if signature_info:
        end_pos = signature_info['start_position']  # End before signature starts
        return text[start_pos:end_pos].strip()
    else:
        # If no signature found, try to find next legal text start
        remaining_text = text[start_pos + len(start_info['full_match']):]
        next_starts = extract_start_info(remaining_text)
        if next_starts:
            next_pos = start_pos + len(start_info['full_match']) + next_starts[0]['start_position']
            return text[start_pos:next_pos].strip()
        else:
            # Return from start to end of text (with reasonable limit)
            end_pos = min(start_pos + 10000, len(text))  # Limit to avoid huge texts
            return text[start_pos:end_pos].strip()


def validate_extraction_results(results: List[Dict]) -> Dict:
    """Validate the extraction results and return a report"""
    validation_report = {
        'total_texts': len(results),
        'missing_numbers': 0,
        'missing_dates': 0,
        'duplicate_numbers': [],
        'very_short_texts': [],
        'very_long_texts': []
    }
    
    numbers_seen = {}
    
    for i, result in enumerate(results):
        # Check for missing data
        if not result.get('number') or result.get('number') == 'N/A':
            validation_report['missing_numbers'] += 1
        
        if not result.get('date') or result.get('date') == 'N/A':
            validation_report['missing_dates'] += 1
        
        # Check for duplicates
        number = result.get('number', '')
        if number and number != 'N/A':
            if number in numbers_seen:
                validation_report['duplicate_numbers'].append({
                    'number': number,
                    'indices': [numbers_seen[number], i]
                })
            else:
                numbers_seen[number] = i
        
        # Check text length
        text_length = result.get('text_length', 0)
        if text_length < 200:
            validation_report['very_short_texts'].append(i)
        elif text_length > 10000:
            validation_report['very_long_texts'].append(i)
    
    return validation_report


def process_file(file_path: str) -> List[Dict]:
    """Process a text file and extract all legal texts"""
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
    
    # Extract all start patterns
    start_infos = extract_start_info(content)
    logger.info(f"Found {len(start_infos)} start patterns")
    
    results = []
    for i, start_info in enumerate(start_infos):
        # Find signature for this legal text
        search_start = start_info['end_position']
        
        # Limit search to before next legal text if exists
        search_end = len(content)
        if i + 1 < len(start_infos):
            search_end = start_infos[i + 1]['start_position']
        
        signature_info = find_signature_pattern(
            content[:search_end], 
            search_start
        )
        
        # Extract the complete legal text
        legal_text = extract_legal_text(content, start_info, signature_info)
        
        result = {
            **start_info,  # Include all start pattern info
            'legal_text': legal_text,
            'signature_info': signature_info,
            'text_length': len(legal_text)
        }
        
        results.append(result)
        logger.info(f"Processed legal text {i+1}: {result.get('number', 'N/A')}")
    
    return results


def save_extracted_texts(results: List[Dict], output_file: str = 'extracted_legal_texts.txt'):
    """Save extracted legal texts with their metadata and validation report."""
    # Extract data for compatibility with the original function signature
    legal_texts = [result.get('legal_text', '') for result in results]
    numbers = [result.get('number', 'N/A') for result in results]
    dates = [result.get('date', 'N/A') for result in results]
    
    # Generate validation report
    validation_report = validate_extraction_results(results)
    
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write("# Extracted Legal Texts with Numbers and Dates\n\n")
            
            # Write validation report
            file.write("## Validation Report\n")
            file.write(f"- Total texts extracted: {validation_report.get('total_texts', 0)}\n")
            file.write(f"- Missing numbers: {validation_report.get('missing_numbers', 0)}\n")
            file.write(f"- Missing dates: {validation_report.get('missing_dates', 0)}\n")
            file.write(f"- Duplicate numbers: {len(validation_report.get('duplicate_numbers', []))}\n")
            file.write(f"- Very short texts (<200 chars): {len(validation_report.get('very_short_texts', []))}\n")
            file.write(f"- Very long texts (>10000 chars): {len(validation_report.get('very_long_texts', []))}\n\n")
            
            # Write legal texts
            for i, (text, number, date) in enumerate(zip(legal_texts, numbers, dates), 1):
                file.write(f"## Legal Text {i}\n")
                file.write(f"**Number:** {number}\n")
                file.write(f"**Date:** {date}\n")
                file.write(f"**Length:** {len(text)} characters\n\n")
                file.write("**Full Text:**\n")
                file.write(text)
                file.write("\n\n" + "="*80 + "\n\n")
        
        logger.info(f"Extracted {len(legal_texts)} legal texts saved to '{output_file}'")
    
    except Exception as e:
        logger.error(f"Error saving file: {str(e)}")


def save_structured_data(results: List[Dict], output_file: str = 'structured_legal_data.txt'):
    """Save extracted data in structured table format"""
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write("# Structured Data\n\n")
            file.write("| Index | Number | Date | Length | Preview |\n")
            file.write("|-------|--------|------|--------|----------|\n")

            for i, result in enumerate(results, 1):
                number = result.get('number', 'N/A')
                date = result.get('date', 'N/A')
                text = result.get('legal_text', '')
                length = len(text)
                preview = text.replace('\n', ' ')[:50] + "..." if len(text) > 50 else text.replace('\n', ' ')
                file.write(f"| {i} | {number} | {date} | {length} | {preview} |\n")
        
        logger.info(f"Structured data saved to '{output_file}'")
    
    except Exception as e:
        logger.error(f"Error saving structured data: {e}")


def save_full_texts(results: List[Dict], output_file: str = 'extracted_texts.txt') -> None:
    """Save full extracted texts with number and date"""
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write("=" * 80 + "\n")
            file.write("EXTRACTED LEGAL TEXTS\n")
            file.write("=" * 80 + "\n\n")
            
            for i, result in enumerate(results, 1):
                file.write(f"TEXT #{i}\n")
                file.write(f"Number: {result.get('number', 'N/A')}\n")
                file.write(f"Date: {result.get('date', 'N/A')}\n")
                file.write(f"Length: {result.get('text_length', 0)} characters\n")
                if result.get('signature_info'):
                    file.write(f"Has Signature: Yes\n")
                else:
                    file.write(f"Has Signature: No\n")
                file.write("-" * 50 + "\n")
                file.write(result.get('legal_text', 'No text found'))
                file.write("\n\n" + "=" * 80 + "\n\n")
        
        logger.info(f"Full texts saved to '{output_file}'")
    
    except Exception as e:
        logger.error(f"Error saving text file: {e}")


# Example usage:
if __name__ == "__main__":
    # Specify the path to your file
    file_path = "data/BO_7083_Ar.txt"
    
    # Process the file
    results = process_file(file_path)
    
    # Print simple summary
    print(f"Extracted {len(results)} legal texts from {file_path}")
    
    if results:
        # Generate validation report
        validation_report = validate_extraction_results(results)
        
        # Print validation summary
        print("\nValidation Summary:")
        print(f"- Total texts: {validation_report['total_texts']}")
        print(f"- Missing numbers: {validation_report['missing_numbers']}")
        print(f"- Missing dates: {validation_report['missing_dates']}")
        print(f"- Duplicate numbers: {len(validation_report['duplicate_numbers'])}")
        
        # Save results to files
        save_extracted_texts(results, "extracted_legal_texts.txt")
        save_structured_data(results, "structured_data.txt")
        save_full_texts(results, "extracted_texts.txt")
        
        print("Done! Check the output files for results.")
        
        # Show extracted texts summary
        print("\nExtracted Legal Texts:")
        for i, result in enumerate(results, 1):
            print(f"  {i}. Number: {result.get('number', 'N/A')} | Date: {result.get('date', 'N/A')} | Length: {result.get('text_length', 0)}")
    else:
        print("No legal texts found in the file.")