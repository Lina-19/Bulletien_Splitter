import re
from typing import List, Optional, Dict

# Global variables for terms (easier to modify)
KEYWORDS = ["قرار", "مرسوم", "ظهير", "قانون", "ظہیر", "منشور", "مذكرة", "مقرر", "اعلان", "بلاغ", "راي"]

NUMBER_INDICATORS = ["رقم", "عدد"]
DATE_INDICATORS = ["صادر في"]
DATE_END_MARKERS = ["و المتعلق " ,"ب", "المتعلق", "بشأن", "حول", "المتضمن"]

# Signature patterns
SIGNATURE_INDICATORS = ["وحرر ب"]
SIGNATURE_KEYWORDS = ["وقعه بالعطف", "الإمضاء", "إمضاء"]
SIGNATURE_LIMIT_KEYWORDS = KEYWORDS
SIGNATURE_LIMIT_SPECIAL_CHARS = ["*", "=", "_", "-", "+", "#"]
SIGNATURE_LIMIT_ANNEXE_WORDS = ["annexe", "ملحق", "مرفق", "المرفق"]



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


def find_signature_pattern(text: str, start_pos: int = 0) -> Optional[Dict]:
    """Find signature pattern after start_pos"""
    # Build patterns
    signature_indicators = "|".join(SIGNATURE_INDICATORS)
    signature_keywords = "|".join(SIGNATURE_KEYWORDS)
    limit_keywords = "|".join(SIGNATURE_LIMIT_KEYWORDS)
    limit_special_chars = "|".join(re.escape(char) for char in SIGNATURE_LIMIT_SPECIAL_CHARS)
    limit_annexe_words = "|".join(SIGNATURE_LIMIT_ANNEXE_WORDS)
    
    # Pattern for signature indicator line (وحرر ب + text)
    indicator_pattern = rf"(?P<indicator>{signature_indicators})\s*(?P<indicator_text>.*?)(?:\n|$)"
    
    # Find the indicator line first
    indicator_match = re.search(indicator_pattern, text[start_pos:], re.DOTALL)
    if not indicator_match:
        return None
    
    indicator_end_pos = start_pos + indicator_match.end()
    
    # Now look for the signature keyword after the indicator
    keyword_pattern = rf"(?P<keyword>{signature_keywords})\s*:\s*"
    keyword_match = re.search(keyword_pattern, text[indicator_end_pos:], re.DOTALL)
    if not keyword_match:
        return None
    
    keyword_end_pos = indicator_end_pos + keyword_match.end()
    
    # Now extract all names until we hit a limit
    names = []
    current_pos = keyword_end_pos
    
    # Look for limit patterns
    limit_pattern = rf"(?P<limit_type>keyword|special|annexe)(?P<limit_match>(?:{limit_keywords})|(?:{limit_special_chars})|(?:{limit_annexe_words}))"
    
    # Extract names until limit is found
    remaining_text = text[current_pos:]
    
    # Find the limit position
    limit_match = re.search(
        rf"(?=(?P<limit_keyword>{limit_keywords})\s)|(?P<limit_special>{limit_special_chars})|(?P<limit_annexe>{limit_annexe_words})", 
        remaining_text, 
        re.DOTALL
    )
    
    if limit_match:
        signature_end_pos = current_pos + limit_match.start()
        limit_info = {
            'type': 'keyword' if limit_match.group('limit_keyword') else 
                   'special' if limit_match.group('limit_special') else 'annexe',
            'value': limit_match.group('limit_keyword') or limit_match.group('limit_special') or limit_match.group('limit_annexe')
        }
    else:
        # If no limit found, take rest of text (or reasonable amount)
        signature_end_pos = len(text)
        limit_info = None
    
    # Extract names from the signature section
    signature_text = text[keyword_end_pos:signature_end_pos]
    
    # Pattern to find names ending with dots
    name_pattern = r"([^.]+)\."
    name_matches = re.findall(name_pattern, signature_text)
    
    # Clean up names (remove extra whitespace and newlines)
    names = [name.strip().replace('\n', ' ').replace('  ', ' ') for name in name_matches]
    
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
        return text[start_pos:signature_info['end_position']].strip()
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
    
    return results


def print_results(results: List[Dict]) -> None:
    """Print extracted results in a readable format"""
    for i, result in enumerate(results, 1):
        print(f"\n{'='*50}")
        print(f"Legal Text #{i}")
        print(f"{'='*50}")
        print(f"Keyword: {result['keyword']}")
        # print(f"Number Indicator: {result['number_indicator']}")
        print(f"Number: {result['number']}")
        print(f"Date: {result['date']}")
        
        # Print signature info if found
        if result.get('signature_info'):
            sig = result['signature_info']
            # print(f"Signature Indicator: {sig['indicator']}")
            # print(f"Signature Indicator Text: {sig['indicator_text']}")
            print(f"Signature Keyword: {sig['keyword']}")
            print(f"Names: {', '.join(sig['names'])}")
            if sig['limit_info']:
                print(f"Signature Limit: {sig['limit_info']['type']} - '{sig['limit_info']['value']}'")
            else:
                print("Signature Limit: Not found")
        else:
            print("Signature: Not found")
        
        print(f"Text Length: {result['text_length']} characters")
        # print(f"\nFull Text Preview (first 200 chars):")
        # print(result['legal_text'][:200] + "..." if len(result['legal_text']) > 200 else result['legal_text'])


def save_structured_data(legal_texts, numbers, dates, output_file='structured_legal_data.txt'):
    """Save extracted data in structured table format"""
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write("# Structured Data\n\n")
            file.write("| Index | Number | Date |\n")
            file.write("|-------|--------|------|\n")


            for i, (text, number, date) in enumerate(zip(legal_texts, numbers, dates), 1):
                # preview = text.replace('\n', ' ')[:50] + "..." if len(text) > 50 else text.replace('\n', ' ')
                # file.write(f"| {i} | {number} | {date} | {len(text)} | {preview} |\n")
                file.write(f"| {i} | {number} | {date} |\n")
            
            # for i, result in enumerate(results, 1):
            #     number = result.get('number', 'N/A')
            #     date = result.get('date', 'N/A')
            #     file.write(f"| {i} | {number} | {date} |\n")
        
        print(f"Structured data saved to '{output_file}'")
    
    except Exception as e:
        print(f"Error saving structured data: {e}")


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
                file.write("-" * 50 + "\n")
                file.write(result.get('legal_text', 'No text found'))
                file.write("\n\n" + "=" * 80 + "\n\n")
        
        print(f"Full texts saved to '{output_file}'")
    
    except Exception as e:
        print(f"Error saving text file: {e}")



# Example usage:
if __name__ == "__main__":
    # Specify the path to your file
    file_path = "data/BO_7083_Ar.txt"
    
    # Process the file
    results = process_file(file_path)
    
    # Print simple summary
    print(f"Extracted {len(results)} legal texts from {file_path}")
    
    if results:
        # Save results to files
        save_structured_data(results, "structured_data.txt")
        save_full_texts(results, "extracted_texts.txt")
        
        print("Done! Check the output files for results.")
        
        # Show extracted texts summary
        print("\nExtracted Legal Texts:")
        for i, result in enumerate(results, 1):
            print(f"  {i}. Number: {result.get('number', 'N/A')} | Date: {result.get('date', 'N/A')}")
    else:
        print("No legal texts found in the file.")














# def find_signature_pattern(text: str, start_pos: int = 0) -> Optional[int]:
#     """Find the position of signature pattern after start_pos"""
#     # Common signature patterns in Arabic legal texts
#     signature_patterns = [
#         r"وزير\s+.*?[،\.]",
#         r"الوزير\s+الأول[،\.]",
#         r"رئيس\s+الحكومة[،\.]",
#         r"الملك[،\.]",
#         r"جلالة\s+الملك[،\.]",
#         r"توقيع",
#         r"إمضاء",
#     ]
    
#     for pattern in signature_patterns:
#         match = re.search(pattern, text[start_pos:])
#         if match:
#             return start_pos + match.end()
    
#     return None


# def extract_legal_text(text: str, start_info: Dict, signature_pos: Optional[int]) -> str:
#     """Extract the complete legal text from start pattern to signature"""
#     start_pos = start_info['start_position']
    
#     if signature_pos:
#         return text[start_pos:signature_pos].strip()
#     else:
#         # If no signature found, try to find next legal text start
#         next_starts = extract_start_info(text[start_pos + len(start_info['full_match']):])
#         if next_starts:
#             next_pos = start_pos + len(start_info['full_match']) + next_starts[0]['start_position']
#             return text[start_pos:next_pos].strip()
#         else:
#             # Return from start to end of text
#             return text[start_pos:].strip()

# def process_file(file_path: str) -> List[Dict]:
#     """Process a text file and extract all legal texts"""
#     try:
#         with open(file_path, 'r', encoding='utf-8') as file:
#             content = file.read()
#     except FileNotFoundError:
#         print(f"File {file_path} not found.")
#         return []
#     except Exception as e:
#         print(f"Error reading file: {e}")
#         return []
    
#     # Extract all start patterns
#     start_infos = extract_start_info(content)
    
#     results = []
#     for i, start_info in enumerate(start_infos):
#         # Find signature for this legal text
#         search_start = start_info['end_position']
        
#         # Limit search to before next legal text if exists
#         search_end = len(content)
#         if i + 1 < len(start_infos):
#             search_end = start_infos[i + 1]['start_position']
        
#         signature_pos = find_signature_pattern(
#             content[:search_end], 
#             search_start
#         )
        
#         # Extract the complete legal text
#         legal_text = extract_legal_text(content, start_info, signature_pos)
        
#         result = {
#             **start_info,  # Include all start pattern info
#             'legal_text': legal_text,
#             'signature_position': signature_pos,
#             'text_length': len(legal_text)
#         }
        
#         results.append(result)
    
#     return results

# def print_results(results: List[Dict]) -> None:
#     """Print extracted results in a readable format"""
#     for i, result in enumerate(results, 1):
#         print(f"\n{'='*50}")
#         print(f"Legal Text #{i}")
#         print(f"{'='*50}")
#         print(f"Keyword: {result['keyword']}")
#         print(f"Number Indicator: {result['number_indicator']}")
#         print(f"Number: {result['number']}")
#         print(f"Date: {result['date']}")
#         print(f"Text Length: {result['text_length']} characters")
#         print(f"\nFull Text Preview (first 200 chars):")
#         print(result['legal_text'][:200] + "..." if len(result['legal_text']) > 200 else result['legal_text'])



# Example usage:
# if __name__ == "__main__":
#     # Add new terms if needed
#     # add_number_indicator("تحت")  # Example: adding a new number indicator
#     # add_keyword("تعليمة")        # Example: adding a new keyword
    
#     # Process a file
#     # results = process_file("legal_texts.txt")
    
#     # Print results
#     # print_results(results)
    
#     # Example of testing the pattern
#     # sample_text = """
#     # قرار وزاري رقم 2.22.195 صادر في 25 من شعبان 1443 (28 مارس 2022) بشأن تنظيم الخدمات العمومية...
    
#     # مرسوم عدد 0025/ق/2022 صادر في 29 من شعبان 1443 (فاتح أبريل 2022) ب المتعلق بالتنظيم الإداري...
#     # """
    
#     # results = extract_start_info(sample_text)
#     print('test')