import re
from typing import List, Optional, Dict

class ArabicLegalTextExtractor:
    def __init__(self):
        # Keywords for legal documents
        self.keywords = [
            "قرار", "مرسوم", "ظهير", "قانون", "ظہیر", 
            "منشور", "مذكرة", "مقرر", "اعلان", "بلاغ", "راي"
        ]
        
        # Number indicators (terms that come before the legal text number)
        self.number_indicators = ["رقم", "عدد"]
        
        # Date indicators (terms that come before the date)
        self.date_indicators = ["صادر في"]
        
        # Arabic letters that typically follow the date
        self.date_end_markers = ["ب", "المتعلق", "بشأن", "حول", "المتضمن"]
    
    def add_keyword(self, keyword: str) -> None:
        """Add a new keyword to the keywords list"""
        if keyword not in self.keywords:
            self.keywords.append(keyword)
    
    def add_number_indicator(self, indicator: str) -> None:
        """Add a new number indicator to the list"""
        if indicator not in self.number_indicators:
            self.number_indicators.append(indicator)
    
    def add_date_indicator(self, indicator: str) -> None:
        """Add a new date indicator to the list"""
        if indicator not in self.date_indicators:
            self.date_indicators.append(indicator)
    
    def add_date_end_marker(self, marker: str) -> None:
        """Add a new date end marker to the list"""
        if marker not in self.date_end_markers:
            self.date_end_markers.append(marker)
    
    def build_start_pattern(self) -> str:
        """Build the regex pattern for the start of legal texts"""
        # Create pattern components
        keywords_pattern = "|".join(self.keywords)
        number_indicators_pattern = "|".join(self.number_indicators)
        date_indicators_pattern = "|".join(self.date_indicators)
        date_end_markers_pattern = "|".join(self.date_end_markers)
        
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
    
    def extract_start_info(self, text: str) -> List[Dict]:
        """Extract information from the start patterns in the text"""
        pattern = self.build_start_pattern()
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
    
    def find_signature_pattern(self, text: str, start_pos: int = 0) -> Optional[int]:
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
    
    def extract_legal_text(self, text: str, start_info: Dict, signature_pos: Optional[int]) -> str:
        """Extract the complete legal text from start pattern to signature"""
        start_pos = start_info['start_position']
        
        if signature_pos:
            return text[start_pos:signature_pos].strip()
        else:
            # If no signature found, try to find next legal text start
            next_starts = self.extract_start_info(text[start_pos + len(start_info['full_match']):])
            if next_starts:
                next_pos = start_pos + len(start_info['full_match']) + next_starts[0]['start_position']
                return text[start_pos:next_pos].strip()
            else:
                # Return from start to end of text
                return text[start_pos:].strip()
    
    def process_file(self, file_path: str) -> List[Dict]:
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
        start_infos = self.extract_start_info(content)
        
        results = []
        for i, start_info in enumerate(start_infos):
            # Find signature for this legal text
            search_start = start_info['end_position']
            
            # Limit search to before next legal text if exists
            search_end = len(content)
            if i + 1 < len(start_infos):
                search_end = start_infos[i + 1]['start_position']
            
            signature_pos = self.find_signature_pattern(
                content[:search_end], 
                search_start
            )
            
            # Extract the complete legal text
            legal_text = self.extract_legal_text(content, start_info, signature_pos)
            
            result = {
                **start_info,  # Include all start pattern info
                'legal_text': legal_text,
                'signature_position': signature_pos,
                'text_length': len(legal_text)
            }
            
            results.append(result)
        
        return results
    
    def print_results(self, results: List[Dict]) -> None:
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
    # Create extractor instance
    extractor = ArabicLegalTextExtractor()
    
    # Add new terms if needed
    # extractor.add_number_indicator("رقم")  # Already included
    # extractor.add_date_end_marker("بموجب")
    
    # Process a file
    # results = extractor.process_file("legal_texts.txt")
    
    # Print results
    # extractor.print_results(results)
    
    # Example of testing the pattern
    sample_text = """
    قرار وزاري رقم 2.22.195 صادر في 25 من شعبان 1443 (28 مارس 2022) بشأن تنظيم الخدمات العمومية...
    
    مرسوم عدد 0025/ق/2022 صادر في 29 من شعبان 1443 (فاتح أبريل 2022) ب المتعلق بالتنظيم الإداري...
    """
    
    results = extractor.extract_start_info(sample_text)
    extractor.print_results(results)