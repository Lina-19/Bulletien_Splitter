import re
from typing import List, Optional, Dict
import logging

# Global variables for terms (easier to modify)
KEYWORDS = ["قرار", "مرسوم", "ظهير", "قانون", "ظہیر",
            "منشور", "مذكرة", "مقرر", "اعلان", "بلاغ", "راي"]

NUMBER_INDICATORS = ["رقم", "عدد"]
DATE_INDICATORS = ["صادر في"]
DATE_END_MARKERS = ["و المتعلق ", "ب", "المتعلق", "بشأن", "حول", "المتضمن"]





def build_start_pattern() -> str:
    """Build the regex pattern for the start of legal texts"""
    # This pattern only matches the keyword at the beginning of a line
    keywords_pattern = "|".join(KEYWORDS)
    pattern = rf"^(?P<keyword>{keywords_pattern})\b"
    return pattern


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


if __name__ == "__main__":
    file_path = "data/test1.txt"
    
    # Read the file content first
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            text_content = file.read()
        print(f"✅ Successfully read file: {file_path}")
        print(f"File content length: {len(text_content)} characters")
    except FileNotFoundError:
        print(f"❌ File {file_path} not found.")
        exit(1)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        exit(1)

    # Extract start info from the text content
    results = extract_start_info(text_content)
    print(f"Found {len(results)} start patterns")

    # Save the start info results
    output_file = "extracted_start_info.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        for i, r in enumerate(results, 1):
            f.write(f"TEXT {i}\n")
            f.write(f"Keyword: {r['keyword']}\n")
            f.write(f"Number: {r['number']}\n")
            f.write(f"Date: {r['date']}\n")
            f.write(f"Text before number: {r.get('text_before_number', r.get('text1', ''))}\n")
            f.write(f"Number indicator: {r['number_indicator']}\n")
            f.write(f"Date indicator: {r['date_indicator']}\n")
            f.write(f"End marker: {r['end_marker']}\n")
            f.write(f"Full match: {r['full_match']}\n")
            f.write("\n" + "+"*50 + "\n\n")

    print(f"✅ Extracted start info saved to {output_file}")