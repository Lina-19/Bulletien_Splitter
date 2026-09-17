import re
from typing import List, Optional, Dict
import logging

# Global variables for terms (easier to modify)
KEYWORDS = ["قرار", "مرسوم", "ظهير", "قانون", "ظہیر", "منشور", "مذكرة", "مقرر", "اعلان", "بلاغ", "راي"]

NUMBER_INDICATORS = ["رقم", "عدد"]
DATE_INDICATORS = ["صادر في"]
DATE_END_MARKERS = ["و المتعلق " ,"ب", "المتعلق", "بشأن", "حول", "المتضمن"]


