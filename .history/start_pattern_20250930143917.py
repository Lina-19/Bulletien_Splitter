import re
from typing import List, Optional, Dict
import logging

KEYWORDS_NO_SIGNATURE = ["بموجب مقرر",
                         "بلاغات",
                         "إعلانات",
                         "اعلانات",
                         "قائمة أسماء",
                         "قائمة اسماء",
                         "سجل بأسماء",
                         "سجل باسماء"
                         ]
# Global variables for terms (easier to modify)
KEYWORDS = ["قرار",
            "مرسوم", 
            "ظهير", 
            "قانون", 
            "ظہیر", 
            "ظهير شريف", 
            "ظہیر شريف", 
            "قرار مشترك",
            "قرار تأديبي",
            "منشور", 
            "مذكرة", 
            "مقرر",
            "اعلان", 
            "إعلان",
            "بلاغ", 
            "راي",
            "رأي",
            "قرار"
        ]

NUMBER_INDICATORS = ["رقم",
                     "عدد"
                    ]

DATE_INDICATORS = [
                r"صادر\s+في",
                r"صادرة\s+في",
                "صادر في",
                "صادر", 
                "صادرة", 
                "صادرة في"
                    ]

DATE_END_MARKERS = ["و المتعلق",
                    "المتعلق",
                    "يتعلق",
                    "والمتعلق",
                    "يقضي" ,
                    "في" ,
                    "الحمد",
                    # "بشأن",
                    "حول", 
                    "كما",
                    "المتضمن",
                    r"\bب\w+",
                    # r"\bي\w+",
                    "قرر"
                    
                    ]


def build_start_pattern() -> str:
    """Build the regex pattern for the start of legal texts"""
    # This pattern only matches the keyword at the beginning of a line
    sorted_keywords = sorted(KEYWORDS, key=len, reverse=True)
    keywords_pattern = "|".join(re.escape(k) for k in sorted_keywords)
    # pattern = rf"^(?P<keyword>{keywords_pattern})"
    pattern = rf"^(?P<keyword>{keywords_pattern})(?=\s|$|[،:؛\.\)])"
    return pattern


def build_no_signature_pattern() -> str:
    """Build the regex pattern for legal texts without signatures"""
    sorted_keywords = sorted(KEYWORDS_NO_SIGNATURE, key=len, reverse=True)
    keywords_pattern = "|".join(re.escape(k) for k in sorted_keywords)
    pattern = rf"^(?P<keyword>{keywords_pattern})(?=\s|$|[،:؛\.\)])"
    return pattern



def extract_sequential_info(text: str, keyword_match) -> Optional[Dict]:
    """Extract information sequentially after finding a keyword"""
    # Start searching after the keyword
    search_start = keyword_match.end()
    remaining_text = text[search_start:]
    
    # 1. Look for the first number indicator
    number_indicators_pattern = "|".join(NUMBER_INDICATORS)
    number_indicator_match = re.search(rf"({number_indicators_pattern})\s+", remaining_text)
    
    if not number_indicator_match:
        return None
    
    # 2. Extract the number that comes after the number indicator
    number_start = number_indicator_match.end()

    # Look for text until we find a date indicator or whitespace/newline pattern


    number_text = remaining_text[number_start:number_start + 20]
    # number_text = remaining_text[number_start:]

    if len(re.findall(r"\d", number_text)) < 1:
        return {
            "number_text": number_text.strip()
        }

    # Find where the number ends (before date indicator or natural break)
    date_indicators_pattern = "|".join(DATE_INDICATORS)
    date_search = re.search(rf"({date_indicators_pattern})", number_text)
    
    if date_search:
        number = number_text[:date_search.start()].strip()
        date_indicator_pos = number_start + date_search.start()
    else:
        return None
    
    # 3. Extract date after date indicator
    date_indicator = date_search.group(1)
    date_start = date_indicator_pos + len(date_indicator)
    date_text = remaining_text[date_start:].strip()
    
    # 4. Find the first end marker after the date to close the date
    date_end_markers_pattern = "|".join(DATE_END_MARKERS)
    end_marker_match = re.search(rf"({date_end_markers_pattern})", date_text)
    
    if end_marker_match:
        date = date_text[:end_marker_match.start()].strip()
        end_marker = end_marker_match.group(1)
    else:
        # If no end marker found, take reasonable amount of date text
        date_words = date_text.split()[:10]  # Limit to first 10 words as fallback
        date = " ".join(date_words)
        end_marker = ""
    
    # Calculate absolute positions
    full_match_start = keyword_match.start()
    full_match_end = search_start + date_start + len(date)

    
    return {
        'full_match': text[full_match_start:full_match_end],
        'keyword': keyword_match.group('keyword').strip(),
        'number_indicator': number_indicator_match.group(1).strip(),
        'number': number,
        'date_indicator': date_indicator.strip(),
        'date': date,
        'end_marker': end_marker.strip(),
        # 'start_position': full_match_start,
        # 'end_position': full_match_end
    }


def extract_no_signature_info(text: str, keyword_match) -> Optional[Dict]:
    """Extract information for legal texts without signatures (simpler pattern)"""
    full_match_start = keyword_match.start()
    full_match_end = keyword_match.end()
    
    # Get a reasonable amount of text after the keyword (e.g., next 200 characters or until newline)
    remaining_text = text[full_match_end:full_match_end + 200]
    
    # Find first newline or colon to end the match
    end_match = re.search(r'[\n:]', remaining_text)
    if end_match:
        full_match_end += end_match.start()
    else:
        full_match_end += len(remaining_text)
    
    return {
        'full_match': text[full_match_start:full_match_end].strip(),
        'keyword': keyword_match.group('keyword').strip(),
        'has_signature': False,  # Flag to indicate this text has no signature
        'number_indicator': '',
        'number': '',
        'date_indicator': '',
        'date': '',
        'end_marker': ''
    }



# def extract_start_info(text: str) -> List[Dict]:
#     """Extract information from the start patterns in the text"""
#     # Split text into lines and process each line
#     lines = text.split('\n')
#     pattern = build_start_pattern()
#     results = []
    
#     for line_num, line in enumerate(lines):
#         # Check if line starts with a keyword
#         match = re.match(pattern, line.strip())
#         if match:
#             # Calculate absolute position in original text
#             line_start = sum(len(lines[i]) + 1 for i in range(line_num))  # +1 for \n
#             match_with_position = type('Match', (), {
#                 'start': lambda self: line_start + match.start(),
#                 'end': lambda self: line_start + match.end(),
#                 'group': lambda self,key: match.group(key)
#             })()
            
#             # Extract sequential information starting from this keyword
#             result = extract_sequential_info(text, match_with_position)
#             if result:
#                 results.append(result)
    
#     return results

def extract_start_info(text: str) -> List[Dict]:
    """Extract information from the start patterns in the text"""
    lines = text.split('\n')
    pattern = build_start_pattern()
    no_sig_pattern = build_no_signature_pattern()
    results = []
    
    for line_num, line in enumerate(lines):
        line_start = sum(len(lines[i]) + 1 for i in range(line_num))
        
        # First, check for no-signature keywords
        no_sig_match = re.match(no_sig_pattern, line.strip())
        if no_sig_match:
            match_with_position = type('Match', (), {
                'start': lambda self: line_start + no_sig_match.start(),
                'end': lambda self: line_start + no_sig_match.end(),
                'group': lambda self, key: no_sig_match.group(key)
            })()
            
            result = extract_no_signature_info(text, match_with_position)
            if result:
                results.append(result)
            continue  # Skip checking regular pattern if no-signature matched
        
        # Check regular keywords with signatures
        match = re.match(pattern, line.strip())
        if match:
            match_with_position = type('Match', (), {
                'start': lambda self: line_start + match.start(),
                'end': lambda self: line_start + match.end(),
                'group': lambda self, key: match.group(key)
            })()
            
            result = extract_sequential_info(text, match_with_position)
            if result:
                result['has_signature'] = True  # Flag for texts with signatures
                results.append(result)
    
    return results

# if __name__ == "__main__":
#     import sys

#     # Ask user for the file path or use a default
#     file_path = "data/BO_7055_Ar.txt"
#     if not file_path:
#         print("❌ No file path provided.")
#         sys.exit(1)

#     # Read the file content
#     try:
#         with open(file_path, 'r', encoding='utf-8') as f:
#             text_content = f.read()
#         print(f"✅ Successfully read file: {file_path}")
#         print(f"File content length: {len(text_content)} characters")
#     except FileNotFoundError:
#         print(f"❌ File {file_path} not found.")
#         sys.exit(1)
#     except Exception as e:
#         print(f"❌ Error reading file: {e}")
#         sys.exit(1)

#     # Extract start info
#     results = extract_start_info(text_content)
#     print(f"Found {len(results)} start patterns in the file.")

#     # Save results to a file
#     output_file = "extracted_files/extracted_start_info_7055.txt"
#     with open(output_file, 'w', encoding='utf-8') as f:
#         for i, r in enumerate(results, 1):
#             f.write(f"TEXT {i}\n")
#             f.write(f"Keyword: {r.get('keyword', '')}\n")
#             f.write(f"Number Indicator: {r.get('number_indicator', '')}\n")
#             f.write(f"Number: {r.get('number', '')}\n")
#             f.write(f"Date Indicator: {r.get('date_indicator', '')}\n")
#             f.write(f"Date: {r.get('date', '')}\n")
#             f.write(f"End Marker: {r.get('end_marker', '')}\n")
#             f.write(f"Full Match: {r.get('full_match', '')}\n")
#             # f.write(f"Position: {r.get('start_position', '')}-{r.get('end_position', '')}\n")
#             f.write("\n" + "+"*50 + "\n\n")

#     print(f"✅ Extracted start info saved to {output_file}")
