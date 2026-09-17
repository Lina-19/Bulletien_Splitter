import re
from typing import List, Optional, Dict
from start_pattern 




SIGNATURE_INDICATORS = [
    "وحرر"
]

SIGNATURE_KEYWORDS_TYPE1 = [
    "وقعه بالعطف", 
    "الإمضاء", 
    "إمضاء"
]

SIGNATURE_KEYWORDS_TYPE2 = [
    "الإمضاءات"
]

# Limit rules
SIGNATURE_LIMIT_KEYWORDS = KEYWORDS  # reuse from your start pattern
SIGNATURE_LIMIT_SPECIAL_CHARS = ["*", "=", "_", "-", "+", "#"]
SIGNATURE_LIMIT_ANNEXE_WORDS = ["annexe", "ملحق", "مرفق", "المرفق", "الملحق"]
