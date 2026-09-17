import re
from typing import List, Optional, Dict
import logging

# Global variables for terms (easier to modify)
KEYWORDS = ["قرار",
            "مرسوم", 
            "ظهير", 
            "قانون", 
            "ظہیر", 
            "ظهير شريف", 
            "ظہیر شريف", 
            "قرار مشترك",
            "منشور", 
            "مذكرة", 
            "مقرر", 
            "اعلان", 
            "بلاغ", 
            "راي"
        ]

NUMBER_INDICATORS = ["رقم", "عدد"]

DATE_INDICATORS = ["صادر في", "صادر", "صادرة", "صادرة في"]

DATE_END_MARKERS = ["و المتعلق ",
                    "ب", 
                    "المتعلق", 
                    "بشأن", 
                    "حول", 
                    "المتضمن", 
                    "قرر"]


def build_start_pattern() -> str:
    """Build the regex pattern for the start of legal texts"""
    # This pattern only matches the keyword at the beginning of a line
    sorted_keywords = sorted(KEYWORDS, key=len, reverse=True)
    keywords_pattern = "|".join(re.escape(k) for k in sorted_keywords)
    pattern = rf"^(?P<keyword>{keywords_pattern})"
    return pattern

    # keywords_pattern = "|".join(KEYWORDS)
    # pattern = rf"^(?P<keyword>{keywords_pattern})\b"
    # return pattern


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
    full_match_end = search_start + date_start + len(date) + len(end_marker)
    
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


def extract_start_info(text: str) -> List[Dict]:
    """Extract information from the start patterns in the text"""
    # Split text into lines and process each line
    lines = text.split('\n')
    pattern = build_start_pattern()
    results = []
    
    for line_num, line in enumerate(lines):
        # Check if line starts with a keyword
        match = re.match(pattern, line.strip())
        if match:
            # Calculate absolute position in original text
            line_start = sum(len(lines[i]) + 1 for i in range(line_num))  # +1 for \n
            match_with_position = type('Match', (), {
                'start': lambda self: line_start + match.start(),
                'end': lambda self: line_start + match.end(),
                'group': lambda self,key: match.group(key)
            })()
            
            # Extract sequential information starting from this keyword
            result = extract_sequential_info(text, match_with_position)
            if result:
                results.append(result)
    
    return results



if __name__ == "__main__":
    import sys

    # Ask user for the file path or use a default
    file_path = "data/BO_7083_Ar.txt"
    if not file_path:
        print("❌ No file path provided.")
        sys.exit(1)

    # Read the file content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text_content = f.read()
        print(f"✅ Successfully read file: {file_path}")
        print(f"File content length: {len(text_content)} characters")
    except FileNotFoundError:
        print(f"❌ File {file_path} not found.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)

    # Extract start info
    results = extract_start_info(text_content)
    print(f"Found {len(results)} start patterns in the file.")

    # Save results to a file
    output_file = "extracted_start_info_7083.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, r in enumerate(results, 1):
            f.write(f"TEXT {i}\n")
            f.write(f"Keyword: {r.get('keyword', '')}\n")
            f.write(f"Number Indicator: {r.get('number_indicator', '')}\n")
            f.write(f"Number: {r.get('number', '')}\n")
            f.write(f"Date Indicator: {r.get('date_indicator', '')}\n")
            f.write(f"Date: {r.get('date', '')}\n")
            f.write(f"End Marker: {r.get('end_marker', '')}\n")
            f.write(f"Full Match: {r.get('full_match', '')}\n")
            # f.write(f"Position: {r.get('start_position', '')}-{r.get('end_position', '')}\n")
            f.write("\n" + "+"*50 + "\n\n")

    print(f"✅ Extracted start info saved to {output_file}")
