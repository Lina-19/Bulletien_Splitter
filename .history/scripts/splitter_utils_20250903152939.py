import re
from typing import List, Tuple, Optional

KW = [
    "قرار", "مرسوم", "ظهير", "قانون", "ظہیر",  # common
    "منشور", "مذكرة", "مقرر", "ملحق",          # less common
    "اعلان", "بلاغ", "راي"
    ]
