"""
src/ml/qwen_description_enricher.py
Alias and wrapper forwarding to DeepSeekDescriptionEnricher for backwards compatibility.
"""

from src.ml.deepseek_description_enricher import (
    DeepSeekDescriptionEnricher,
    get_deepseek_description_enricher,
    FactGroundingValidator,
    AddedFact,
    EnrichmentOutput,
    PROMPT_ID,
    PROMPT_VERSION,
    SCHEMA_VERSION,
)

# Backwards compatibility alias
QwenDescriptionEnricher = DeepSeekDescriptionEnricher
get_qwen_description_enricher = get_deepseek_description_enricher
