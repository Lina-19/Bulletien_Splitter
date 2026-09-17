import re
import unicodedata

KW = [
    "قرار", "مرسوم", "ظهير", "قانون", "ظہیر",  # common
    "منشور", "مذكرة", "مقرر", "ملحق",          # less common
    "اعلان", "بلاغ", "راي"
]