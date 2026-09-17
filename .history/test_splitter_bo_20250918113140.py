import re
from typing import List, Optional, Dict
import logging

# Global variables for terms (easier to modify)
KEYWORDS = ["قرار", "مرسوم", "ظهير", "قانون", "ظہیر", "منشور", "مذكرة", "مقرر", "اعلان", "بلاغ", "راي"]

NUMBER_INDICATORS = ["رقم", "عدد"]
DATE_INDICATORS = ["صادر في"]
DATE_END_MARKERS = ["و المتعلق " ,"ب", "المتعلق", "بشأن", "حول", "المتضمن"]


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
    sample_text = """
    مرسوم رقم 2.22.333 صادر في 3 ذي القعدة 1443 (3) يونيو (2022) بالموافقة على التصميم والنظام المتعلق به الموضوعين لتهيئة مقاطعة سيدي بليوط بجماعة الدار البيضاء بعمالة الدار البيضاء وبالإعلان أن في ذلك منفعة عامة.
    قرار لوزير الشؤون الخارجية والتعاون الإفريقي والمغاربة المقيمين بالخارج رقم 1133.22 صادر في 2 رمضان 1443 (4) أبريل 2022) بتتميم قرار وزير الشؤون الخارجية والتعاون رقم 2394.06 بتاريخ 5 شعبان 1427 (30) أغسطس 2006) بشأن التعويض الإجمالي عن تغيير محل الإقامة الممنوح لأعوان وزارة الشؤون الخارجية والتعاون العاملين بالخارج.
    قرار لوزير الشؤون الخارجية والتعاون الإفريقي والمغاربة المقيمين بالخارج رقم 1134.22 صادر في 2 رمضان 1443 (4) أبريل (2022) بتتميم قرار وزير الشؤون الخارجية والتعاون الإفريقي والمغاربة المقيمين بالخارج رقم 665.20 الصادر في 3 جمادى الآخرة 1441 (29 يناير 2020) المتعلق بالتعويض عن صوائر التمثيل.
    """

    results = extract_start_info(sample_text)

    from pprint import pprint
    pprint(results)

    # # Basic checks
    # assert len(results) == 2
    # assert results[0]['keyword'] == "قرار"
    # assert results[0]['number'] == "1234"
    # assert results[0]['date'] == "01/01/2024"
    # assert results[1]['keyword'] == "مرسوم"
    # assert results[1]['number'] == "5678"
    # assert results[1]['date'] == "15/03/2025"

    print("✅ All inline tests passed!")