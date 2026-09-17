import re
import os

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
    file_path = "data/text.txt"
    
    # Extract legal texts
    legal_texts = extract_legal_texts_from_file(file_path)
    
    # Save the results
    save_extracted_texts(legal_texts, "extracted_legal_texts.txt")
    
    print(f"Done! Extracted {len(legal_texts)} legal texts from {file_path}")

    
# if __name__ == "__main__":
#     # Test with the provided example
#     example_text = """=== Page 3 ===
# نصوص
# مرسوم رقم 2.22.45 صادر في 25 من جمادى الآخرة 1443 (28 يناير 2022) بتمديد مدة سريان مفعول حالة الطوارئ الصحية بسائر أرجاء التراب الوطني لمواجهة تفشي فيروس كورونا - كوفيد 19.
# رئيس الحكومة،
# بناء على المرسوم بقانون رقم 2.20.292 الصادر في 28 من رجب 1441 (23) مارس (2020) المتعلق بسن أحكام خاصة بحالة الطوارئ الصحية وإجراءات الإعلان عنها المصادق عليه بالقانون رقم 23.20 الصادر بتنفيذه الظهير الشريف رقم 1.20.60 بتاريخ 5 شوال 1441 (28 ماي 2020) ؛
# وبعد الاطلاع على المرسوم رقم 2.20.293 الصادر في 29 من رجب 1441 (24 مارس (2020) بإعلان حالة الطوارئ الصحية بسائر أرجاء التراب الوطني لمواجهة تفشي فيروس كورونا - كوفيد 19 ؛
# وعلى المرسوم رقم 2.21.1016 الصادر في 18 من جمادى الأولى 1443 (23) ديسمبر 2021) بتمديد مدة سريان مفعول حالة الطوارئ الصحية بسائر أرجاء التراب الوطني لمواجهة تفشي فيروس كورونا - كوفيد 19 ؛
# وبالنظر إلى ما تقتضيه الظرفية من ضرورة الاستمرار في الإجراءات اللازمة للحد من تفشي الجائحة مع الحرص على تناسب الإجراءات والتدابير المتخذة بمختلف جهات وعمالات وأقاليم المملكة مع تطور الحالة الوبائية ؛
# وباقتراح من وزير الداخلية ووزير الصحة والحماية الاجتماعية ؛
# وبعد المداولة في مجلس الحكومة المنعقد في 24 من جمادى الآخرة 1443 (27 يناير 2022).
# رسم ما يلي :
# ###المادة الأولى
# تطبيقا لأحكام الفقرة الثانية بالمادة الثانية من المرسوم بقانون المشار إليه أعلاه رقم 2.20.292 الصادر في 28 من رجب 1441 (23) مارس (2020، تمدد، من يوم الاثنين 31 يناير 2022 في الساعة السادسة مساء إلى غاية يوم الاثنين 28 فبراير 2022 في الساعة السادسة مساء، مدة سريان مفعول حالة الطوارئ الصحية بسائر أرجاء التراب الوطني المعلن عنها بموجب المرسوم رقم 2.20.293 الصادر في 29 من رجب 1441 (24) مارس (2020) بإعلان حالة الطوارئ الصحية بسائر أرجاء التراب الوطني لمواجهة تفشي فيروس كورونا - كوفيد 19.
# ###المادة الثانية
# يجوز لوزير الداخلية أن يتخذ في ضوء المعطيات المتوفرة حول الحالة الوبائية السائدة، وبتنسيق مع السلطات الحكومية المعنية، كافة التدابير المناسبة على الصعيد الوطني، بما يتلاءم وهذه المعطيات.
# كما يجوز لولاة الجهات وعمال العمالات والأقاليم، كل في نطاق اختصاصه الترابي، أن يتخذوا في ضوء المعطيات نفسها، وفي إطار تطبيق مقتضيات المادة الثالثة من المرسوم السالف الذكر رقم 2.20.293 ، كل تدبير من هذا القبيل على مستوى عمالة أو إقليم أو جماعة أو أكثر.
# ###المادة الثالثة
# ينشر هذا المرسوم بالجريدة الرسمية، ويسند تنفيذه إلى وزير الداخلية ووزير الصحة والحماية الاجتماعية، كل واحد منهما فيما يخصه.
# وحرر بالرباط في 25 من جمادى الآخرة 1443 (28 يناير 2022).
# الإمضاء : عزيز أخنوش.
# وقعه بالعطف :
# وزير الداخلية
# الإمضاء : عبد الوافي لفتيت.
# وزير الصحة والحماية الاجتماعية
# الإمضاء : خالد ايت طالب.
# === Page 4 ===
# قرار لوزير التعليم العالي والبحث العلمي والابتكار رقم 3828.21 صادر في 4 جمادى الأولى 1443 (9 ديسمبر 2021) بتحديد بعض المعادلات بين الشهادات.
# وزير التعليم العالي والبحث العلمي والابتكار، بناء على المرسوم رقم 2.01.333 الصادر في 28 من ربيع الأول 1422 (21) يونيو (2001) المتعلق بتحديد الشروط والمسطرة الخاصة بمنح معادلة شهادات التعليم العالي ؛ وعلى المرسوم رقم 2.04.89 الصادر في 18 من ربيع الآخر 1425 (7) يونيو (2004) بتحديد اختصاص المؤسسات الجامعية وأسلاك الدراسات العليا وكذا الشهادات الوطنية المطابقة، كما وقع تغييره وتتميمه ؛ وعلى المرسوم رقم 2.21.838 الصادر في 14 من ربيع الأول 1443 (21) أكتوبر (2021 المتعلق باختصاصات وزير التعليم العالي والبحث العلمي والابتكار ؛ وبعد استشارة اللجنة القطاعية للعلوم والتقنيات والهندسة والهندسة المعمارية المنعقدة بتاريخ 21 أكتوبر 2021، قرر ما يلي :
# ###المادة الأولى
# تقبل لمعادلة دبلوم مهندس دولة، الشهادة التالية في : Ingénierie automobile - Qualification master's degree program subject area motor vehicle transport educational program motor vehicle transport, délivrée par Kharkiv national automobile and highway university - Ukraine - le 31 décembre 2019, assortie de la qualification bachelor program subject area motor vehicle transport, délivrée par la même université, le 30 juin 2018, وبشهادة البكالوريا للتعليم الثانوي في إحدى الشعب العلمية أو التقنية أو ما يعادلها.
# ###المادة الثانية
# ينشر هذا القرار بالجريدة الرسمية.
# وحرر بالرباط في 4 جمادى الأولى 1443 (9) ديسمبر 2021).
# الإمضاء : عبد اللطيف ميراوي."""
    
#     # Test the extraction
#     print("Testing legal text extraction...")
#     legal_texts = extract_legal_texts(example_text)
    
#     print(f"\nFound {len(legal_texts)} legal texts:")
#     for i, text in enumerate(legal_texts, 1):
#         print(f"\n--- Legal Text {i} ---")
#         print(f"Length: {len(text)} characters")
#         print(f"Starts with: {text[:100]}...")
#         print(f"Ends with: ...{text[-100:]}")
    
#     # Usage examples:
#     print(f"\n{'='*50}")
#     print("USAGE EXAMPLES:")
#     print(f"{'='*50}")
#     print("\n1. To extract from a file:")
#     print("   legal_texts = extract_legal_texts_from_file('bulletin.txt')")
#     print("\n2. To save results:")
#     print("   save_extracted_texts(legal_texts, 'output.txt')")
#     print("\n3. To extract from string:")
#     print("   legal_texts = extract_legal_texts(text_content)")