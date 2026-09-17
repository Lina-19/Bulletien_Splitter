import re
import logging

# Set up logging for debugging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def extract_legal_texts(text_content):
    """
    Enhanced extraction of legal texts with improved boundary detection.
    
    Args:
        text_content (str): The content of the official bulletin
        
    Returns:
        tuple: (list of legal texts, list of numbers, list of dates)
    """
    
    start_keywords = [
        "قرار", "مرسوم", "ظهير", "قانون", "ظہیر",
        "منشور", "مذكرة", "مقرر", "ملحق", 
        "اعلان", "بلاغ", "راي"
    ]
    
    # Enhanced pattern that looks for keyword followed by number pattern
    # start_pattern = r'\b(?:' + '|'.join(start_keywords) + r')\b'
    
    # Signature pattern (end marker)
    signature_pattern = r'الإمضاء\s*:\s*[^.]+?\.(?:\s*وقعه بالعطف\s*:.*?الإمضاء\s*:\s*[^.]+?\.)*'
    
    # Number pattern - looking for رقم followed by number
    number_pattern = r'رقم\s+([^\s]+(?:\s+[^\s]+)*?)(?=\s+صادر|\s+في|\s|$)'
    
    # Date pattern - looking for صادر في followed by date
    date_pattern = r'صادر في\s+(.+?)(?:\s*(?:ب|،|؛|\.|$))'
    
    # Combined pattern for legal text header (keyword + number + date)
    header_pattern = r'\b(?:' + '|'.join(start_keywords) + r')\b.*?رقم\s+[^\n]*?صادر في\s+[^\n]*'
    
    legal_texts = []
    numbers = []
    dates = []
    
    # Clean the text
    cleaned_text = re.sub(r'=== Page \d+ ===\s*', '', text_content)
    cleaned_text = re.sub(r'\n+', '\n', cleaned_text)
    cleaned_text = re.sub(r'###', '', cleaned_text)
    
    lines = cleaned_text.split('\n')
    text_lines = [line.strip() for line in lines if line.strip()]
    full_text = '\n'.join(text_lines)
    
    logger.info(f"Processing text of length: {len(full_text)} characters")
    
    # Find potential legal text headers (keyword + number + date pattern)
    header_matches = list(re.finditer(header_pattern, full_text, re.DOTALL))
    
    logger.info(f"Found {len(header_matches)} potential legal text headers")
    
    for i, header_match in enumerate(header_matches):
        start_pos = header_match.start()
        
        # Find the actual start of the legal text (beginning of the line containing the header)
        text_before_match = full_text[:start_pos]
        last_newline = text_before_match.rfind('\n')
        actual_start = last_newline + 1 if last_newline != -1 else 0
        
        # Define search area for this legal text
        if i + 1 < len(header_matches):
            # Search until the next legal text header
            next_header_start = header_matches[i + 1].start()
            next_text_before = full_text[:next_header_start]
            next_last_newline = next_text_before.rfind('\n')
            search_end = next_last_newline if next_last_newline != -1 else next_header_start
        else:
            # This is the last legal text, search to end of document
            search_end = len(full_text)
        
        search_text = full_text[actual_start:search_end]
        
        # Look for signature pattern in this section
        signature_matches = list(re.finditer(signature_pattern, search_text, re.DOTALL))
        
        if signature_matches:
            # Use the last signature match in case there are multiple
            signature_match = signature_matches[-1]
            end_pos = actual_start + signature_match.end()
            legal_text = full_text[actual_start:end_pos].strip()
            
            # Clean up the extracted text
            legal_text = re.sub(r'\n+', '\n', legal_text)
            legal_text = re.sub(r'^\s+|\s+$', '', legal_text, flags=re.MULTILINE)
            
            # Extract number and date from the header portion
            header_text = header_match.group(0)
            
            # Extract number
            number_match = re.search(number_pattern, header_text)
            number = number_match.group(1).strip() if number_match else "غير محدد"
            
            # Extract date
            date_match = re.search(date_pattern, header_text)
            if date_match:
                date = date_match.group(1).strip()
                date = re.sub(r'\s+', ' ', date)
                # Remove common trailing words that might be caught
                date = re.sub(r'\s*(ب|في|من)$', '', date)
            else:
                date = "غير محدد"
            
            legal_texts.append(legal_text)
            numbers.append(number)
            dates.append(date)
            
            logger.info(f"Extracted legal text {len(legal_texts)}: Number='{number}', Date='{date}'")
        else:
            logger.warning(f"No signature found for legal text starting at position {actual_start}")
    
    return legal_texts, numbers, dates

def validate_extraction(legal_texts, numbers, dates):
    """
    Validate the extracted legal texts for common issues.
    
    Args:
        legal_texts (list): List of legal texts
        numbers (list): List of numbers
        dates (list): List of dates
        
    Returns:
        dict: Validation report
    """
    report = {
        'total_texts': len(legal_texts),
        'missing_numbers': sum(1 for n in numbers if n == "غير محدد"),
        'missing_dates': sum(1 for d in dates if d == "غير محدد"),
        'duplicate_numbers': [],
        'very_short_texts': [],
        'very_long_texts': []
    }
    
    # Check for duplicate numbers
    number_counts = {}
    for i, number in enumerate(numbers):
        if number != "غير محدد":
            if number in number_counts:
                report['duplicate_numbers'].append((i, number))
            else:
                number_counts[number] = i
    
    # Check text lengths
    for i, text in enumerate(legal_texts):
        if len(text) < 200:  # Very short texts might be incomplete
            report['very_short_texts'].append((i, len(text)))
        elif len(text) > 10000:  # Very long texts might include multiple documents
            report['very_long_texts'].append((i, len(text)))
    
    return report

def extract_legal_texts_from_file(file_path):
    """
    Extract legal texts from a text file containing official bulletin.
    
    Args:
        file_path (str): Path to the text file
        
    Returns:
        tuple: (list of legal texts, list of numbers, list of dates, validation_report)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        legal_texts, numbers, dates = extract_legal_texts(content)
        validation_report = validate_extraction(legal_texts, numbers, dates)
        
        return legal_texts, numbers, dates, validation_report
    
    except FileNotFoundError:
        logger.error(f"File '{file_path}' not found.")
        return [], [], [], {}
    except Exception as e:
        logger.error(f"Error reading file: {str(e)}")
        return [], [], [], {}

def save_extracted_texts(legal_texts, numbers, dates, validation_report, output_file='extracted_legal_texts.txt'):
    """
    Save extracted legal texts with their metadata and validation report.
    """
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

def save_structured_data(legal_texts, numbers, dates, output_file='structured_legal_data.txt'):
    """
    Save extracted data in a more structured format.
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write("# Structured Legal Data\n\n")
            file.write("| Index | Number | Date | Length | Preview |\n")
            file.write("|-------|--------|------|--------|---------|\n")
            
            for i, (text, number, date) in enumerate(zip(legal_texts, numbers, dates), 1):
                preview = text.replace('\n', ' ')[:50] + "..." if len(text) > 50 else text.replace('\n', ' ')
                file.write(f"| {i} | {number} | {date} | {len(text)} | {preview} |\n")
        
        logger.info(f"Structured data saved to '{output_file}'")
    
    except Exception as e:
        logger.error(f"Error saving structured data: {str(e)}")

# Example usage and testing
if __name__ == "__main__":
    # Specify the path to your file
    file_path = "data/BO_7100_Ar.txt"
    
    # Extract legal texts with enhanced method
    legal_texts, numbers, dates, validation_report = extract_legal_texts_from_file(file_path)
    
    # Print summary
    print(f"\nExtracted {len(legal_texts)} legal texts from {file_path}")
    print("\nValidation Report:")
    print(f"  - Missing numbers: {validation_report.get('missing_numbers', 0)}")
    print(f"  - Missing dates: {validation_report.get('missing_dates', 0)}")
    print(f"  - Duplicate numbers: {len(validation_report.get('duplicate_numbers', []))}")
    print(f"  - Very short texts: {len(validation_report.get('very_short_texts', []))}")
    print(f"  - Very long texts: {len(validation_report.get('very_long_texts', []))}")
    
    print("\nExtracted Legal Texts:")
    for i, (number, date) in enumerate(zip(numbers, dates), 1):
        print(f"  {i}. Number: {number} | Date: {date}")
    
    # Save the results
    save_extracted_texts(legal_texts, numbers, dates, validation_report, "extracted_texts.txt")
    save_structured_data(legal_texts, numbers, dates, "structured_data.txt")
    
    print("\nDone! Check the output files for results.")
    
    # Show any problematic cases
    if validation_report.get('duplicate_numbers'):
        print("\nWarning: Found duplicate numbers:")
        for idx, number in validation_report['duplicate_numbers']:
            print(f"  Text {idx + 1}: {number}")
    
    if validation_report.get('very_short_texts'):
        print("\nWarning: Found very short texts (might be incomplete):")
        for idx, length in validation_report['very_short_texts']:
            print(f"  Text {idx + 1}: {length} characters")