"""
Module: scripts/gstin_utils.py
Description: Checksum calculation, builder, and structural validator for Indian GSTINs.
Implements the official Modulo-36 algorithm (ISO/IEC 7064 Mod 36, 2) and comprehensive validation rules.
"""

import re

# Character set for GSTIN Base-36 encoding (0-9, A-Z)
CHAR_SET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MODULUS = len(CHAR_SET)  # 36

# Regex pattern for structural GSTIN validation (GN-01 to GN-05, GN-10)
GSTIN_REGEX = re.compile(
    r"^(?P<state>[0-9]{2})(?P<pan>[A-Z]{5}[0-9]{4}[A-Z])(?P<entity>[0-9A-Z])Z(?P<checksum>[0-9A-Z])$"
)

# Valid state and union territory codes under GST (GN-06)
VALID_STATE_CODES = {
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "21", "22", "23", "24", "25", "26", "27", "28", "29", "30",
    "31", "32", "33", "34", "35", "36", "37", "38", "97", "99"
}

def get_char_index(char: str) -> int:
    """Map a character to its Base-36 index value (0-35)."""
    try:
        return CHAR_SET.index(char)
    except ValueError:
        raise ValueError(f"Invalid character '{char}' found in GSTIN string. Only alphanumeric characters are allowed.")

def calculate_checksum(gstin_14: str) -> str:
    """
    Computes the 15th checksum character for a 14-character GSTIN base string
    using the standard Modulo-36 algorithm (GN-05, GN-11).
    """
    if not isinstance(gstin_14, str) or len(gstin_14) != 14:
        raise ValueError("Input must be exactly a 14-character GSTIN base string.")
    
    gstin_14 = gstin_14.upper()
    factor = 2
    total_sum = 0
    
    for char in gstin_14:
        code_point = get_char_index(char)
        digit = factor * code_point
        factor = 1 if factor == 2 else 2
        digit = (digit // MODULUS) + (digit % MODULUS)
        total_sum += digit
        
    remainder = total_sum % MODULUS
    check_code_point = (MODULUS - remainder) % MODULUS
    return CHAR_SET[check_code_point]

def build_gstin(gstin_14: str) -> str:
    """
    Builds a complete 15-character valid GSTIN by appending the computed 
    Modulo-36 checksum character to the 14-character base.
    """
    gstin_14 = gstin_14.upper()
    if len(gstin_14) != 14:
        raise ValueError("GSTIN base must be exactly 14 characters before computing checksum.")
    checksum_char = calculate_checksum(gstin_14)
    return gstin_14 + checksum_char

def validate_gstin(gstin: str) -> bool:
    """
    Comprehensive validator for Indian GSTIN:
    - GN-01 & GN-02: Length (15 chars) and uppercase normalization checks.
    - GN-03 & GN-05: Regex structural verification (State, PAN, Entity code, 'Z' marker).
    - GN-06: Valid state/UT code verification.
    - GN-11: Modulo-36 checksum integrity verification.
    """
    if not isinstance(gstin, str):
        return False
        
    gstin = gstin.strip().upper()
    
    # Check length (GN-01)
    if len(gstin) != 15:
        return False
        
    # Structural regex validation (GN-03, GN-05)
    match = GSTIN_REGEX.match(gstin)
    if not match:
        return False
        
    # Verify State Code validity (GN-06)
    state_code = match.group("state")
    if state_code not in VALID_STATE_CODES:
        return False
        
    # Verify 14th character is fixed as 'Z' (GN-10)
    if gstin[13] != 'Z':
        return False
        
    # Checksum verification (GN-11)
    try:
        base_14 = gstin[:14]
        expected_checksum = calculate_checksum(base_14)
        return gstin[14] == expected_checksum
    except (ValueError, IndexError):
        return False