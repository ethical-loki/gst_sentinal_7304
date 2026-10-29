import json
import logging
import re
from pathlib import Path
from typing import Optional, NamedTuple, Tuple

import torch
from transformers import (
    AutoConfig,
    AutoTokenizer,
    AutoModelForQuestionAnswering,
    AutoModelForSeq2SeqLM,
)

from config import MODEL_PATH

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
)
logger = logging.getLogger("gst_sentinel.reader")


class AnswerSpan(NamedTuple):
    answer: str
    score: float
    start_char: int
    end_char: int


class DynamicReader:
    """
    Dynamic offline reader:
    - Automatically discovers local model architecture from config.json.
    - Dynamically supports both Generative Seq2Seq (T5/BART) and Extractive QA (Longformer/BERT/RoBERTa).
    - Automatically allocates CPU or CUDA.
    - Filters high-entropy base64 ciphertext noise from technical documents on the fly.
    """

    def __init__(self, model_dir: Optional[str] = None):
        self.model_path = Path(model_dir) if model_dir else MODEL_PATH
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model directory not found at {self.model_path.resolve()}. "
                "Ensure local model files are stored in the configured path."
            )

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Target device dynamically set to: {self.device}")

        # 1. Inspect config to dynamically determine architecture
        self.config = AutoConfig.from_pretrained(str(self.model_path), local_files_only=True)
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_path), local_files_only=True)

        self.is_generative = bool(
            self.config.is_encoder_decoder
            or any("seq2seq" in arch.lower() or "forconditionalgeneration" in arch.lower()
                   for arch in getattr(self.config, "architectures", []))
        )

        if self.is_generative:
            logger.info(f"Detected Generative architecture: {self.config.model_type}")
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                str(self.model_path),
                local_files_only=True,
                config=self.config
            ).to(self.device)
        else:
            logger.info(f"Detected Extractive QA architecture: {self.config.model_type}")
            self.model = AutoModelForQuestionAnswering.from_pretrained(
                str(self.model_path),
                local_files_only=True,
                config=self.config
            ).to(self.device)

        self.model.eval()

        # Dynamically determine maximum input context limit
        self.max_tokens = getattr(
            self.config,
            "max_position_embeddings",
            getattr(self.tokenizer, "model_max_length", 2048)
        )
        if self.max_tokens is None or self.max_tokens > 4096 or self.max_tokens <= 0:
            self.max_tokens = 2048

        logger.info(f"Dynamic input sequence length set to: {self.max_tokens} tokens")

    @staticmethod
    def strip_document_noise(text: str) -> str:
        """
        Dynamically strips base64 blocks, token signatures, and excessive
        JSON noise that disrupts both tokenizers and language models.
        """
        # Remove long uninterrupted base64-like words (> 40 chars)
        clean = re.sub(r"[A-Za-z0-9+/=_-]{40,}", " ", text)
        # Collapse multiple spaces and newlines
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    def _predict_extractive(self, question: str, context: str) -> Optional[AnswerSpan]:
        """Runs dynamic extractive QA inference with char-span alignment."""
        clean_context = self.strip_document_noise(context)
        inputs = self.tokenizer(
            question,
            clean_context,
            return_tensors="pt",
            max_length=self.max_tokens,
            truncation="only_second",
            return_offsets_mapping=True,
            padding=True,
        )

        offset_mapping = inputs.pop("offset_mapping")[0].cpu().tolist()
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Dynamically attach global attention if Longformer
        if self.config.model_type == "longformer":
            global_attention_mask = torch.zeros_like(inputs["input_ids"])
            # Apply global attention to question tokens + CLS token
            sep_token_id = self.tokenizer.sep_token_id
            input_ids_list = inputs["input_ids"][0].tolist()
            first_sep = input_ids_list.index(sep_token_id) if sep_token_id in input_ids_list else 1
            global_attention_mask[:, : first_sep + 1] = 1
            inputs["global_attention_mask"] = global_attention_mask

        with torch.no_grad():
            outputs = self.model(**inputs)

        start_logits = outputs.start_logits[0]
        end_logits = outputs.end_logits[0]

        # Isolate context sequence index bounds
        try:
            sequence_ids = inputs.get("token_type_ids")
            if sequence_ids is not None:
                context_indices = [
                    i for i, seq_id in enumerate(sequence_ids[0].cpu().tolist()) if seq_id == 1
                ]
            else:
                # Dynamic fallback using offset mappings (first non-zero start offset after question)
                context_indices = [
                    i for i, offset in enumerate(offset_mapping)
                    if offset != (0, 0) and i > 2
                ]
        except Exception:
            context_indices = list(range(1, len(offset_mapping) - 1))

        if not context_indices:
            return None

        # Mask non-context tokens
        mask = torch.full_like(start_logits, float("-inf"))
        mask[context_indices] = 0.0
        masked_start = start_logits + mask
        masked_end = end_logits + mask

        start_probs = torch.softmax(masked_start, dim=-1)
        end_probs = torch.softmax(masked_end, dim=-1)

        best_score = -1.0
        best_span = (0, 0)
        max_answer_len = min(60, len(context_indices))

        for s_idx in context_indices:
            e_limit = min(s_idx + max_answer_len, context_indices[-1] + 1)
            for e_idx in range(s_idx, e_limit):
                score = (start_probs[s_idx] * end_probs[e_idx]).item()
                if score > best_score:
                    best_score = score
                    best_span = (s_idx, e_idx)

        s_tok, e_tok = best_span
        start_char, _ = offset_mapping[s_tok]
        _, end_char = offset_mapping[e_tok]

        extracted_text = clean_context[start_char:end_char].strip()
        if not extracted_text:
            return None

        return AnswerSpan(
            answer=extracted_text,
            score=round(best_score, 4),
            start_char=start_char,
            end_char=end_char
        )

    def _predict_generative(self, question: str, context: str) -> Optional[AnswerSpan]:
        """Runs dynamic generative seq2seq inference."""
        clean_context = self.strip_document_noise(context)
        prompt = (
            f"Given the context information below, answer the question accurately.\n"
            f"If the information is not present, reply with 'not found'.\n\n"
            f"Context: {clean_context}\n\n"
            f"Question: {question}\n\n"
            f"Answer:"
        )

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            max_length=self.max_tokens,
            truncation=True
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=80,
                num_beams=2,
                early_stopping=True,
                no_repeat_ngram_size=2
            )

        predicted_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        if not predicted_text or predicted_text.lower() == "not found":
            return AnswerSpan(answer="not found", score=0.0, start_char=-1, end_char=-1)

        return AnswerSpan(
            answer=predicted_text,
            score=1.0,
            start_char=-1,
            end_char=-1
        )

    def predict(self, question: str, context: str) -> Optional[AnswerSpan]:
        """Single dynamic interface for both Generative and Extractive models."""
        q_clean = question.strip()
        c_clean = context.strip()

        if not q_clean or not c_clean:
            return None

        if self.is_generative:
            return self._predict_generative(q_clean, c_clean)
        return self._predict_extractive(q_clean, c_clean)


# Alias for backward compatibility with previous scripts
LongReader = DynamicReader
if __name__ == "__main__":
    from config import CONTENT_PATH

    print("=" * 70)
    print(" LIVE DYNAMIC READER TEST ")
    print("=" * 70)

    try:
        reader = DynamicReader()

        # Dynamically load live context from data/content.txt
        if not CONTENT_PATH.exists():
            raise FileNotFoundError(f"Content file missing at: {CONTENT_PATH}")

        with open(CONTENT_PATH, "r", encoding="utf-8", errors="replace") as f:
            raw_text = f.read()

        # Dynamically pull the first ~1200 words of real content as the live context window
        words = raw_text.split()
        dynamic_context = " ".join(words[:1200])

        print(f"\n[+] Loaded dynamic context from: {CONTENT_PATH} ({len(words)} total words available)")
        print("-" * 70)

        # Interactive loop to test live questions dynamically
        while True:
            try:
                user_q = input("\nEnter a question to test reader (or 'exit' to quit): ").strip()
                if user_q.lower() in ("exit", "quit"):
                    print("Exiting dynamic reader test.")
                    break
                if not user_q:
                    print("Please enter a non-empty question.")
                    continue

                result = reader.predict(question=user_q, context=dynamic_context)

                print("\n" + "-" * 50)
                if result and result.answer != "not found":
                    print(f" Extracted/Generated Answer: {result.answer}")
                    print(f" Confidence Score:           {result.score}")
                    if result.start_char != -1:
                        print(f" Character Span:             [{result.start_char}:{result.end_char}]")
                else:
                    print(" Result: not found (confidence below threshold or no match)")
                print("-" * 50)

            except (KeyboardInterrupt, EOFError):
                print("\nInterrupted. Exiting.")
                break

    except Exception as err:
        logger.critical(f"Execution failed: {err}")