"""
reader.py — Dynamic neural reader utilizing Google Flan-T5 Seq2Seq generation.

Maintains backward-compatibility for AnswerSpan and DynamicReader interfaces
while upgrading the core generative inference to instruction-tuned Flan-T5.
"""

import logging
import re
from pathlib import Path
from typing import Optional, NamedTuple

from config import MODEL_PATH, FALLBACK_RESPONSE
from model import FlanT5Generator

logger = logging.getLogger("gst_sentinel.reader")


class AnswerSpan(NamedTuple):
    answer: str
    score: float
    start_char: int
    end_char: int


class DynamicReader:
    """
    Unified neural reader powered by instruction-tuned Flan-T5.
    """

    def __init__(self, model_dir: Optional[str] = None):
        model_str = str(model_dir) if model_dir else str(MODEL_PATH)
        logger.info(f"Initializing DynamicReader with Flan-T5 model: {model_str}")
        self.generator = FlanT5Generator(model_name_or_path=model_str)

    def predict(self, question: str, context: str) -> Optional[AnswerSpan]:
        """Runs instruction-tuned Flan-T5 inference over the provided context chunk."""
        q_clean = question.strip() if question else ""
        c_clean = context.strip() if context else ""

        if not q_clean or not c_clean:
            return None

        answer = self.generator.generate(question=q_clean, context=c_clean)

        if answer == FALLBACK_RESPONSE or not answer:
            return AnswerSpan(answer="not found", score=0.0, start_char=-1, end_char=-1)

        char_start = context.find(answer)
        char_end = char_start + len(answer) if char_start != -1 else -1

        return AnswerSpan(
            answer=answer,
            score=0.95,
            start_char=char_start,
            end_char=char_end
        )


# Backward compatibility aliases
LongReader = DynamicReader
