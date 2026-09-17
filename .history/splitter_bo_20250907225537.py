import re

def extract_legal_texts(text_content):
    """
    Extract legal texts from official bulletin content.
    
    Args:
        text_content (str): The content of the official bulletin
        
    Returns:
        list: List of extracted legal texts
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
    
    legal_texts = []
    
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
            
            legal_texts.append(legal_text)
    
    return legal_texts

def extract_legal_texts_from_file(file_path):
    """
    Extract legal texts from a text file containing official bulletin.
    
    Args:
        file_path (str): Path to the text file
        
    Returns:
        list: List of extracted legal texts
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        return extract_legal_texts(content)
    
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return []
    except Exception as e:
        print(f"Error reading file: {str(e)}")
        return []

def save_extracted_texts(legal_texts, output_file='extracted_legal_texts.txt'):
    """
    Save extracted legal texts to a file.
    
    Args:
        legal_texts (list): List of legal texts
        output_file (str): Output file path
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write("# Extracted Legal Texts\n\n")
            for i, text in enumerate(legal_texts, 1):
                file.write(f"## Legal Text {i}\n\n")
                file.write(text)
                file.write("\n\n" + "="*80 + "\n\n")
        
        print(f"Extracted {len(legal_texts)} legal texts saved to '{output_file}'")
    
    except Exception as e:
        print(f"Error saving file: {str(e)}")





# Example usage and testing

if __name__ == "__main__":
    # Specify the path to your file
    file_path = "data/BO_7052_Ar.txt"
    
    # Extract legal texts
    legal_texts = extract_legal_texts_from_file(file_path)
    
    # Save the results
    save_extracted_texts(legal_texts, "extracted_legal_texts.txt")
    
    print(f"Done! Extracted {len(legal_texts)} legal texts from {file_path}")
