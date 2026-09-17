import re

def extract_legal_texts(text_content):
    """
    Extract legal texts from official bulletin content with their numbers and dates.
    
    Args:
        text_content (str): The content of the official bulletin
        
    Returns:
        tuple: (list of legal texts, list of numbers, list of dates)
    """
    
    # Define starting keywords for legal texts
    start_keywords = [
        "قرار", "مرسوم", "ظهير", "قانون", "ظہیر",
        "منشور", "مذكرة", "مقرر", "ملحق", 
        "اعلان", "بلاغ", "راي"
    ]
    
    # Create regex pattern for start keywords
    start_pattern = r'\b(?:' + '|'.join(start_keywords) + r')\b'
    
    # Pattern for signature section (الإمضاء followed by name)
    signature_pattern = r'الإمضاء\s*:\s*[^.]+?\.(?:\s*وقعه بالعطف\s*:.*?الإمضاء\s*:\s*[^.]+?\.)*'
    
    # Pattern for extracting number (after رقم)
    number_pattern = r'رقم\s+([^\s]+(?:\s+[^\s]+)*?)(?:\s+صادر|\s|$)'
    
    # Pattern for extracting date (after صادر في)
    date_pattern = r'صادر في\s+(.+?)(?:\s+ب|\.|$)'
    
    legal_texts = []
    numbers = []
    dates = []
    
    # Clean the text - remove page markers and extra whitespace
    cleaned_text = re.sub(r'=== Page \d+ ===\s*', '', text_content)
    cleaned_text = re.sub(r'\n+', '\n', cleaned_text)
    cleaned_text = re.sub(r'###', '', cleaned_text)  # Remove ### markers
    
    # Split text into lines and process
    lines = cleaned_text.split('\n')
    text_lines = [line.strip() for line in lines if line.strip()]
    full_text = '\n'.join(text_lines)
    
    # Find all potential starting positions
    start_matches = list(re.finditer(start_pattern, full_text))
    
    for i, start_match in enumerate(start_matches):
        start_pos = start_match.start()
        
        # Find the end position (next legal text start or end of document)
        if i + 1 < len(start_matches):
            end_search_pos = start_matches[i + 1].start()
            search_text = full_text[start_pos:end_search_pos]
        else:
            search_text = full_text[start_pos:]
        
        # Look for signature pattern in this section
        signature_match = re.search(signature_pattern, search_text, re.DOTALL)
        
        if signature_match:
            # Extract the complete legal text
            end_pos = start_pos + signature_match.end()
            legal_text = full_text[start_pos:end_pos].strip()
            
            # Clean up the extracted text
            legal_text = re.sub(r'\n+', '\n', legal_text)
            legal_text = re.sub(r'^\s+|\s+$', '', legal_text, flags=re.MULTILINE)
            
            # Extract number
            number_match = re.search(number_pattern, legal_text)
            number = number_match.group(1).strip() if number_match else "غير محدد"
            
            # Extract date
            date_match = re.search(date_pattern, legal_text)
            if date_match:
                date = date_match.group(1).strip()
                # Clean up the date by removing extra spaces and formatting
                date = re.sub(r'\s+', ' ', date)
            else:
                date = "غير محدد"
            
            legal_texts.append(legal_text)
            numbers.append(number)
            dates.append(date)
    
    return legal_texts, numbers, dates

def extract_legal_texts_from_file(file_path):
    """
    Extract legal texts from a text file containing official bulletin.
    
    Args:
        file_path (str): Path to the text file
        
    Returns:
        tuple: (list of legal texts, list of numbers, list of dates)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        return extract_legal_texts(content)
    
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return [], [], []
    except Exception as e:
        print(f"Error reading file: {str(e)}")
        return [], [], []

def save_extracted_texts(legal_texts, numbers, dates, output_file='extracted_legal_texts.txt'):
    """
    Save extracted legal texts with their numbers and dates to a file.
    
    Args:
        legal_texts (list): List of legal texts
        numbers (list): List of numbers
        dates (list): List of dates
        output_file (str): Output file path
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write("# Extracted Legal Texts with Numbers and Dates\n\n")
            
            for i, (text, number, date) in enumerate(zip(legal_texts, numbers, dates), 1):
                file.write(f"## Legal Text {i}\n")
                file.write(f"**Number:** {number}\n")
                file.write(f"**Date:** {date}\n\n")
                file.write("**Full Text:**\n")
                file.write(text)
                file.write("\n\n" + "="*80 + "\n\n")
        
        print(f"Extracted {len(legal_texts)} legal texts with numbers and dates saved to '{output_file}'")
    
    except Exception as e:
        print(f"Error saving file: {str(e)}")

def save_structured_data(legal_texts, numbers, dates, output_file='structured_legal_data.txt'):
    """
    Save extracted data in a more structured format.
    
    Args:
        legal_texts (list): List of legal texts
        numbers (list): List of numbers  
        dates (list): List of dates
        output_file (str): Output file path
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write("# Structured Legal Data\n\n")
            file.write("| Index | Number | Date | Preview |\n")
            file.write("|-------|--------|------|---------|\n")
            
            for i, (text, number, date) in enumerate(zip(legal_texts, numbers, dates), 1):
                # Get first 50 characters as preview
                preview = text.replace('\n', ' ')[:50] + "..." if len(text) > 50 else text.replace('\n', ' ')
                file.write(f"| {i} | {number} | {date} | {preview} |\n")
        
        print(f"Structured data saved to '{output_file}'")
    
    except Exception as e:
        print(f"Error saving structured data: {str(e)}")

# Example usage and testing
if __name__ == "__main__":
    # Specify the path to your file
    file_path = "data/test.txt"
    
    # Extract legal texts with numbers and dates
    legal_texts, numbers, dates = extract_legal_texts_from_file(file_path)
    
    # Print summary
    print(f"Extracted {len(legal_texts)} legal texts from {file_path}")
    print("\nSummary:")
    for i, (number, date) in enumerate(zip(numbers, dates), 1):
        print(f"  {i}. Number: {number} | Date: {date}")
    
    # Save the results
    save_extracted_texts(legal_texts, numbers, dates, "extracted_legal_texts_with_metadata.txt")
    save_structured_data(legal_texts, numbers, dates, "structured_legal_data.txt")
    
    print("Done! Check the output files for results.")
    
    # Example of accessing the data
    print(f"\nExample - First legal text:")
    if legal_texts:
        print(f"Number: {numbers[0]}")
        print(f"Date: {dates[0]}")
        print(f"Text preview: {legal_texts[0][:200]}...")