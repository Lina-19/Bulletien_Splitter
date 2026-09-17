import re
import logging

# Set up logging for debugging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def extract_legal_texts(text_content):
    """
    Enhanced extraction of legal texts with improved boundary detection.
    Each legal text starts with a keyword and ends with a signature.
    
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
    
    # Improved signature patterns to catch various formats
    signature_patterns = [
        r'الإمضاء\s*:\s*([^.\n]+)\.(?:\s*وقعه بالعطف\s*:\s*([^.\n]+)\.)?',  # Standard signature
        r'وقعه\s*:\s*([^.\n]+)\.',  # Alternative signature format
        r'الإمضاء\s*:\s*([^.\n]+)',
        r'الإمضاءات\s*:\s*([^.\n]+)',
            # Signature without period
    ]
    
    # Number pattern - looking for رقم followed by number
    number_pattern = r'رقم\s+([^\s]+(?:\s+[^\s]+)*?)(?=\s+صادر|\s+في|\s|$)'
    
    # date_pattern = r'صادر في\s+(.+?)(?:\s*(?:ب|،|؛|\.|$))'
    # date_pattern = r'صادر في\s+(.+?)(?=\s+ب|$)'
    date_pattern = r'صادر في\s+(.+?)(?=\s+ب|\s*$|قرر\s+ما\s+يلي)'
    
    legal_texts = []
    numbers = []
    dates = []
    
    # Clean the text
    cleaned_text = re.sub(r'=== Page \d+ ===\s*', '', text_content)
    cleaned_text = re.sub(r'\n+', '\n', cleaned_text)
    
    lines = cleaned_text.split('\n')
    text_lines = [line.strip() for line in lines if line.strip()]
    full_text = '\n'.join(text_lines)
    
    logger.info(f"Processing text of length: {len(full_text)} characters")
    
    # Find all potential starting points (keywords at beginning of lines)
    potential_starts = []
    
    # for i, line in enumerate(text_lines):
    #     for keyword in start_keywords:
    #         if line.startswith(keyword) and len(line.split()) > 1:  # Ensure it's not just the keyword alone
    #             # Check if this line contains number and date patterns
    #             if re.search(r'رقم\s+', line) and re.search(r'صادر في', line):
    #                 # Calculate position in full text
    #                 start_pos = len('\n'.join(text_lines[:i]))
    #                 if i > 0:
    #                     start_pos += 1  # Add newline character
    #                 potential_starts.append((start_pos, i, line, keyword))
    #                 break  # Only match first keyword per line
    
    # logger.info(f"Found {len(potential_starts)} potential legal text starts")

    for i, line in enumerate(text_lines):
        for keyword in start_keywords:
            if line.startswith(keyword) and len(line.split()) > 1:  # Ensure it's not just the keyword alone
                # Check if this line contains number pattern
                if re.search(r'رقم\s+', line):
                    # Look for date pattern in this line or the next few lines
                    header_text = line
                    date_found = re.search(r'صادر في', line)
                    
                    # If no date in current line, check next 3 lines
                    if not date_found and i + 3 < len(text_lines):
                        for j in range(1, 4):  # Check next 3 lines
                            next_line = text_lines[i + j]
                            header_text += '\n' + next_line
                            if re.search(r'صادر في', next_line):
                                date_found = True
                                break
                            # Stop if we hit another keyword (start of next legal text)
                            if any(next_line.startswith(kw) for kw in start_keywords):
                                break
                    
                    if date_found:
                        # Calculate position in full text
                        start_pos = len('\n'.join(text_lines[:i]))
                        if i > 0:
                            start_pos += 1  # Add newline character
                        potential_starts.append((start_pos, i, header_text, keyword))
                        break  # Only match first keyword per line
    
    logger.info(f"Found {len(potential_starts)} potential legal text starts")
    
    # Find all signatures in the document
    all_signatures = []
    for pattern in signature_patterns:
        for match in re.finditer(pattern, full_text, re.MULTILINE | re.DOTALL):
            all_signatures.append((match.start(), match.end(), match.group(0)))
    
    # Sort signatures by position
    all_signatures.sort(key=lambda x: x[0])
    logger.info(f"Found {len(all_signatures)} signatures in document")
    
    # Process each potential start
    for i, (start_pos, line_idx, start_line, keyword) in enumerate(potential_starts):
        logger.info(f"Processing potential start {i+1}: {keyword} at line {line_idx + 1}")
        
        # Extract number and date from the start line
        number_match = re.search(number_pattern, start_line)
        number = number_match.group(1).strip() if number_match else "غير محدد"
        
        date_match = re.search(date_pattern, start_line)
        if date_match:
            date = date_match.group(1).strip()
            date = re.sub(r'\s+', ' ', date)
            date = re.sub(r'\s*(ب|في|من)$', '', date)
        else:
            date = "غير محدد"
        
        # Find the next legal text start (if any) to limit search area
        next_start_pos = None
        if i + 1 < len(potential_starts):
            next_start_pos = potential_starts[i + 1][0]
        
        # Find signatures that come after this start and before the next start
        relevant_signatures = []
        for sig_start, sig_end, sig_text in all_signatures:
            if sig_start > start_pos:
                if next_start_pos is None or sig_start < next_start_pos:
                    relevant_signatures.append((sig_start, sig_end, sig_text))
        
        if relevant_signatures:
            # Use the first signature found after this start
            first_sig_start, first_sig_end, first_sig_text = relevant_signatures[0]
            
            # Extract text from start to end of first signature
            legal_text = full_text[start_pos:first_sig_end].strip()
            
            # Clean up the extracted text
            legal_text = re.sub(r'\n+', '\n', legal_text)
            legal_text = re.sub(r'^\s+|\s+$', '', legal_text, flags=re.MULTILINE)
            
            # Validate the extracted text (should be reasonable length)
            if len(legal_text) > 50:  # Minimum reasonable length
                legal_texts.append(legal_text)
                numbers.append(number)
                dates.append(date)
                
                logger.info(f"Extracted legal text {len(legal_texts)}: Number='{number}', Date='{date}', Length={len(legal_text)}")
            else:
                logger.warning(f"Skipped very short text (length: {len(legal_text)})")
        else:
            logger.warning(f"No signature found for legal text starting with: {start_line[:50]}...")
    
    return legal_texts, numbers, dates

def find_signatures_in_text(text):
    """
    Helper function to find all signatures in a given text.
    Returns list of (start_pos, end_pos, signature_text) tuples.
    """
    signature_patterns = [
        r'الإمضاء\s*:\s*([^.\n]+)\.(?:\s*وقعه بالعطف\s*:\s*([^.\n]+)\.)?',
        r'وقعه\s*:\s*([^.\n]+)\.',
        r'الإمضاء\s*:\s*([^.\n]+)',
        r'الإمضاءات\s*:\s*([^.\n]+)',
    ]
    
    signatures = []
    for pattern in signature_patterns:
        for match in re.finditer(pattern, text, re.MULTILINE | re.DOTALL):
            signatures.append((match.start(), match.end(), match.group(0)))
    
    return sorted(signatures, key=lambda x: x[0])

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
            file.write("# Structured Data\n\n")
            file.write("| Index | Number | Date |\n")
            file.write("|-------|--------|------|\n")
            
            for i, (text, number, date) in enumerate(zip(legal_texts, numbers, dates), 1):
                # preview = text.replace('\n', ' ')[:50] + "..." if len(text) > 50 else text.replace('\n', ' ')
                # file.write(f"| {i} | {number} | {date} | {len(text)} | {preview} |\n")
                file.write(f"| {i} | {number} | {date} |\n")
        
        logger.info(f"Structured data saved to '{output_file}'")
    
    except Exception as e:
        logger.error(f"Error saving structured data: {str(e)}")

# Example usage and testing
if __name__ == "__main__":
    # Specify the path to your file
    file_path = "data/BO_70_Ar.txt"
    
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