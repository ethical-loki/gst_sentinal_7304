import math
import re
from collections import Counter
from typing import Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd


def clean_text(text: object) -> str:
  """Strip control characters, tabs, null bytes, zero-width spaces, and standardize whitespace."""
  if text is None or (isinstance(text, float) and pd.isna(text)):
    return ""
  if not isinstance(text, str):
    text = str(text)
  # Strip non-printable ASCII control characters (\x00-\x1f, \x7f-\x9f)
  # and zero-width / BOM Unicode characters (\u200b-\u200d, \ufeff)
  text = re.sub(r"[\x00-\x1f\x7f-\x9f\u200b-\u200d\ufeff]", " ", text)
  return re.sub(r"\s+", " ", text).strip().lower()


def compute_shannon_entropy(text: object) -> float:
  """Calculates character-level Shannon entropy in bits per character.

  Formula: H = -sum(p(c) * log2(p(c)))
  """
  clean = clean_text(text)
  if not clean:
    return 0.0

  total_chars = len(clean)
  counts = Counter(clean)
  entropy = -sum(
      (count / total_chars) * math.log2(count / total_chars)
      for count in counts.values()
  )
  if abs(entropy) < 1e-9:
    return 0.0
  return round(entropy, 4)


class DynamicHSNMasterEngine:
  """Dynamic processor reading Final_hsn_sac_copy.xlsx to establish statutory

  tariffs and empirical entropy bounds.
  """

  def __init__(self, hsn_excel_path: str = "data/raw/Final_hsn_sac_copy.xlsx"):
    self.hsn_excel_path = hsn_excel_path
    self.hsn_to_desc: Dict[str, str] = {}
    self.hsn_to_rate: Dict[str, float] = {}
    self.valid_hsn_set: Set[str] = set()

    # Empirical dynamic boundaries (calibrated from master)
    self.entropy_lower_bound: float = 2.5
    self.entropy_upper_bound: float = 4.5

    self._load_master_data()

  def _normalize_code(self, val: object) -> str:
    """Cleans tariff code into a standardized string."""
    if val is None or pd.isna(val):
      return ""
    if isinstance(val, (int, np.integer)):
      val_str = str(val)
    elif isinstance(val, (float, np.floating)):
      val_str = str(int(val)) if val.is_integer() else str(val)
    else:
      val_str = str(val).strip()

    # If the string is purely integer.0 (e.g. '7306.0' or '8481.0'), strip .0
    if re.match(r"^\d+\.0+$", val_str):
      val_str = val_str.split(".")[0]

    return re.sub(r"[^0-9a-zA-Z]", "", val_str)

  def _extract_codes_from_cell(self, val: object) -> List[str]:
    """Extracts all valid HSN/SAC codes from a tariff cell."""
    if val is None or pd.isna(val):
      return []
    val_str = str(val).strip()
    if any(k in val_str.lower() for k in ["heading/tariff", "tariff item"]):
      return []

    # Strip bracketed exceptions e.g. [other than ...] or (except ...)
    main_part = re.sub(r"\[.*?\]|\(.*?\)", "", val_str).strip()
    chunks = re.split(r"[,;\n]|(?:\bor\b)", main_part)
    codes = set()
    for chunk in chunks:
      compact = re.sub(r"\s+", "", chunk.strip())
      matches = re.findall(r"\d{2,8}", compact)
      for m in matches:
        if len(m) in (3, 5, 7):
          codes.add("0" + m)
        codes.add(m)

    # Fallback to normalized code if regex didn't catch anything
    if not codes:
      norm = self._normalize_code(val)
      if norm and norm.isdigit() and 2 <= len(norm) <= 8:
        codes.add(norm)

    return list(codes)

  def _normalize_rate(self, val: object) -> float:
    """Extracts numeric rate float from strings/numbers (e.g., '18%', '0.09', 'Nil')."""
    if val is None or pd.isna(val):
      return 0.0
    if isinstance(val, (int, float, np.number)):
      rate = float(val)
      return rate / 100.0 if rate > 1.0 else rate

    val_str = str(val).strip()
    if val_str.lower() in ("nil", "exempt", "none", "zero", "na", "n/a"):
      return 0.0

    pct_match = re.search(r"(\d+(\.\d+)?)\s*%", val_str)
    if pct_match:
      return float(pct_match.group(1)) / 100.0

    # If specific non-percentage cess/duty like 'Rs.4006 per thousand', return 0.0
    if re.search(r"rs\.?\s*\d+", val_str, re.I):
      return 0.0

    match = re.search(r"\d+(\.\d+)?", val_str)
    if match:
      rate = float(match.group(0))
      return rate / 100.0 if rate > 1.0 else rate

    return 0.0

  def _load_master_data(self) -> None:
    try:
      df = pd.read_excel(self.hsn_excel_path)
    except Exception as e:
      raise FileNotFoundError(
          f"Failed to load HSN master Excel file from '{self.hsn_excel_path}': {e}"
      )

    code_col, desc_col, rate_col = None, None, None
    for col in df.columns:
      clean_name = re.sub(r"\s+", " ", str(col)).strip().lower()
      if any(
          k in clean_name
          for k in ["chapter", "tariff", "sub- heading", "heading"]
      ):
        code_col = col
      elif "description" in clean_name or "goods" in clean_name:
        desc_col = col
      elif "rate" in clean_name:
        rate_col = col

    if not code_col or not desc_col:
      raise ValueError(
          f"Required columns not detected in {self.hsn_excel_path}. Columns:"
          f" {list(df.columns)}"
      )

    descriptions_for_calibration = []
    for _, row in df.iterrows():
      extracted_codes = self._extract_codes_from_cell(row[code_col])
      clean_desc = (
          clean_text(str(row[desc_col])) if pd.notna(row[desc_col]) else ""
      )
      clean_rate = (
          self._normalize_rate(row[rate_col])
          if rate_col and pd.notna(row[rate_col])
          else 0.0
      )

      if clean_desc and len(clean_desc) >= 6:
        descriptions_for_calibration.append(clean_desc)

      for code in extracted_codes:
        self.valid_hsn_set.add(code)
        # Add 6-digit, 4-digit, and 2-digit prefixes to valid set
        if len(code) >= 6:
          self.valid_hsn_set.add(code[:6])
        if len(code) >= 4:
          self.valid_hsn_set.add(code[:4])
        if len(code) >= 2:
          self.valid_hsn_set.add(code[:2])

        # Map description
        if clean_desc:
          if code not in self.hsn_to_desc:
            self.hsn_to_desc[code] = clean_desc
          if len(code) >= 6 and code[:6] not in self.hsn_to_desc:
            self.hsn_to_desc[code[:6]] = clean_desc
          if len(code) >= 4 and code[:4] not in self.hsn_to_desc:
            self.hsn_to_desc[code[:4]] = clean_desc
          if len(code) >= 2 and code[:2] not in self.hsn_to_desc:
            self.hsn_to_desc[code[:2]] = clean_desc

        # Map rate
        if rate_col:
          if code not in self.hsn_to_rate:
            self.hsn_to_rate[code] = clean_rate
          if len(code) >= 6 and code[:6] not in self.hsn_to_rate:
            self.hsn_to_rate[code[:6]] = clean_rate
          if len(code) >= 4 and code[:4] not in self.hsn_to_rate:
            self.hsn_to_rate[code[:4]] = clean_rate
          if len(code) >= 2 and code[:2] not in self.hsn_to_rate:
            self.hsn_to_rate[code[:2]] = clean_rate

    # Dynamically calibrate bounds from official trade entries
    if descriptions_for_calibration:
      scores = [
          compute_shannon_entropy(d) for d in descriptions_for_calibration
      ]
      self.entropy_lower_bound = round(float(np.percentile(scores, 1.0)), 2)
      self.entropy_upper_bound = round(float(np.percentile(scores, 99.0)), 2)

  def check_entropy_quality(self, text: object) -> Tuple[float, bool]:
    """Gatekeeper step: Returns (entropy_score, is_valid_text)."""
    clean = clean_text(text)
    if len(clean) < 3:
      return 0.0, False

    alnum_chars = sum(1 for c in clean if c.isalnum())
    alnum_ratio = alnum_chars / len(clean)
    entropy = compute_shannon_entropy(clean)

    # 1. Reject if non-alphanumeric symbols dominate (>60% symbols)
    if alnum_ratio < 0.40:
      return entropy, False

    # 2. Gatekeeper: Valid if within empirical trade boundaries
    if self.entropy_lower_bound <= entropy <= self.entropy_upper_bound:
      return entropy, True

    # 3. Handle legitimate short trade descriptions (e.g., 'pipe', 'tea', 'valve', 'steel tubes')
    # where maximum possible entropy is constrained by log2(N)
    if len(clean) < 12 and alnum_ratio >= 0.70:
      max_entropy = math.log2(len(clean))
      if max_entropy > 0 and (entropy / max_entropy) >= 0.70 and entropy >= 1.5:
        return entropy, True

    return entropy, False

  def is_valid_hsn(self, hsn_input: object) -> int:
    code = self._normalize_code(hsn_input)
    if not code:
      return 0
    return (
        1
        if (
            code in self.valid_hsn_set
            or (len(code) >= 6 and code[:6] in self.valid_hsn_set)
            or (len(code) >= 4 and code[:4] in self.valid_hsn_set)
            or (len(code) >= 2 and code[:2] in self.valid_hsn_set)
        )
        else 0
    )

  def get_statutory_description(self, hsn_input: object) -> str:
    code = self._normalize_code(hsn_input)
    if not code:
      return ""
    if code in self.hsn_to_desc:
      return self.hsn_to_desc[code]
    if len(code) >= 6 and code[:6] in self.hsn_to_desc:
      return self.hsn_to_desc[code[:6]]
    if len(code) >= 4 and code[:4] in self.hsn_to_desc:
      return self.hsn_to_desc[code[:4]]
    if len(code) >= 2 and code[:2] in self.hsn_to_desc:
      return self.hsn_to_desc[code[:2]]
    return ""

  def get_statutory_rate(self, hsn_input: object) -> float:
    code = self._normalize_code(hsn_input)
    if not code:
      return 0.0
    if code in self.hsn_to_rate:
      return self.hsn_to_rate[code]
    if len(code) >= 6 and code[:6] in self.hsn_to_rate:
      return self.hsn_to_rate[code[:6]]
    if len(code) >= 4 and code[:4] in self.hsn_to_rate:
      return self.hsn_to_rate[code[:4]]
    if len(code) >= 2 and code[:2] in self.hsn_to_rate:
      return self.hsn_to_rate[code[:2]]
    return 0.0