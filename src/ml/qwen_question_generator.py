"""
Module: src/ml/qwen_question_generator.py
Description: Dynamic Clarification Question Generator wrapper for backward compatibility.
"""

from src.ml.dynamic_question_generator import (
    DynamicQuestionGenerator,
    get_dynamic_question_generator,
    SCHEMA_VERSION
)

__all__ = [
    "DynamicQuestionGenerator",
    "get_dynamic_question_generator",
    "SCHEMA_VERSION"
]
