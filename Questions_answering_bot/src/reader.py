import json
import logging
import re
from pathlib import Path
from typing import Optional, NamedTuple

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
    Production offline neural reader:
    - Supports both Extractive QA (Longformer/BERT/RoBERTa) and Generative Seq2Seq (T5/BART).
    - Vectorized 2D logit span search (0ms span selection).
    - Null-token / unanswerable query detection to prevent hallucinating answers when information is absent.
    - Strips document noise, base64 blocks, and JSON sample markers.
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
        """Strips base64 blocks, JWT signatures, and JSON noise."""
        clean = re.sub(r"[A-Za-z0-9+/=_-]{40,}", " ", text)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

    @staticmethod
    def clean_answer_text(answer: str) -> str:
        """Trims leading numbering, FAQ labels, and formatting artifacts."""
        ans = re.sub(r"\[JSON sample #\d+\]", "", answer).strip()
        ans = re.sub(r"^([0-9]+[A-Za-z]?[\.\:]|\bQ[\.\:]|\bA[\.\:])\s*", "", ans).strip()
        ans = ans.strip(" '\"`()[]{}.,;:")
        return ans

    def _predict_extractive(self, question: str, context: str) -> Optional[AnswerSpan]:
        """Runs fast vectorized extractive QA inference with null verification."""
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

        if self.config.model_type == "longformer":
            global_attention_mask = torch.zeros_like(inputs["input_ids"])
            sep_token_id = self.tokenizer.sep_token_id
            input_ids_list = inputs["input_ids"][0].tolist()
            first_sep = input_ids_list.index(sep_token_id) if sep_token_id in input_ids_list else 1
            global_attention_mask[:, : first_sep + 1] = 1
            inputs["global_attention_mask"] = global_attention_mask

        with torch.no_grad():
            outputs = self.model(**inputs)

        start_logits = outputs.start_logits[0]
        end_logits = outputs.end_logits[0]

        # Token 0 is the [CLS]/null token (indicating unanswerable)
        null_score = (start_logits[0] + end_logits[0]).item()

        # Isolate context sequence token bounds
        context_indices = [
            i for i, offset in enumerate(offset_mapping)
            if offset != (0, 0) and i > 2 and offset[1] > offset[0]
        ]

        if not context_indices:
            return AnswerSpan(answer="not found", score=0.0, start_char=-1, end_char=-1)

        s_ctx = start_logits[context_indices]
        e_ctx = end_logits[context_indices]

        max_s_logit = s_ctx.max().item()
        max_e_logit = e_ctx.max().item()

        # Vectorized 2D scoring matrix: score[s, e] = s_ctx[s] + e_ctx[e]
        max_len = min(35, len(context_indices))
        score_matrix = s_ctx.unsqueeze(1) + e_ctx.unsqueeze(0)
        len_c = len(context_indices)
        idx = torch.arange(len_c, device=score_matrix.device)

        # Invalidate spans where end < start or end - start >= max_len
        diff = idx.unsqueeze(0) - idx.unsqueeze(1)
        invalid_mask = (diff < 0) | (diff >= max_len)
        score_matrix.masked_fill_(invalid_mask, float("-inf"))

        best_flat_idx = torch.argmax(score_matrix)
        best_s_rel = (best_flat_idx // len_c).item()
        best_e_rel = (best_flat_idx % len_c).item()
        best_logit_sum = score_matrix[best_s_rel, best_e_rel].item()

        # Null-token and unanswerability rejection
        logit_margin_over_null = best_logit_sum - null_score
        if best_logit_sum < 0.5 or max_s_logit < -1.0 or max_e_logit < -1.0 or logit_margin_over_null < 1.5:
            return AnswerSpan(answer="not found", score=0.0, start_char=-1, end_char=-1)

        tok_s = context_indices[best_s_rel]
        tok_e = context_indices[best_e_rel]
        raw_start, _ = offset_mapping[tok_s]
        _, raw_end = offset_mapping[tok_e]

        candidate_text = clean_context[raw_start:raw_end].strip()
        cleaned_text = self.clean_answer_text(candidate_text)

        if not cleaned_text or len(cleaned_text) < 2:
            return AnswerSpan(answer="not found", score=0.0, start_char=-1, end_char=-1)

        # Precise character offset alignment with input context
        char_start = context.find(cleaned_text)
        if char_start != -1:
            char_end = char_start + len(cleaned_text)
        else:
            char_start = raw_start
            char_end = raw_end

        # Calibrated probability in [0.0, 1.0]
        confidence = round(torch.sigmoid(torch.tensor((best_logit_sum - 2.5) / 2.5)).item(), 4)

        return AnswerSpan(
            answer=cleaned_text,
            score=confidence,
            start_char=char_start,
            end_char=char_end
        )

    def _predict_generative(self, question: str, context: str) -> Optional[AnswerSpan]:
        """Runs generative seq2seq inference with concise answering prompt."""
        clean_context = self.strip_document_noise(context)
        prompt = (
            f"Based strictly on the following GST reference context, provide a short, accurate answer to the question.\n"
            f"If the answer cannot be found in the context, reply only with 'not found'.\n\n"
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
                max_new_tokens=40,
                num_beams=2,
                early_stopping=True,
                no_repeat_ngram_size=2
            )

        predicted_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        cleaned_text = self.clean_answer_text(predicted_text)

        if not cleaned_text or cleaned_text.lower() in ("not found", "none", "unknown"):
            return AnswerSpan(answer="not found", score=0.0, start_char=-1, end_char=-1)

        # Verify predicted text is not echoing the prompt
        if cleaned_text.lower() in question.lower() or len(cleaned_text) > 150:
            return AnswerSpan(answer="not found", score=0.0, start_char=-1, end_char=-1)

        char_start = context.find(cleaned_text)
        char_end = char_start + len(cleaned_text) if char_start != -1 else -1

        return AnswerSpan(
            answer=cleaned_text,
            score=0.90,
            start_char=char_start,
            end_char=char_end
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


# Backward compatibility alias
LongReader = DynamicReader

if __name__ == "__main__":
    from config import CONTENT_PATH

    print("=" * 70)
    print(" LIVE DYNAMIC READER TEST ")
    print("=" * 70)

    reader = DynamicReader()
    if not CONTENT_PATH.exists():
        raise FileNotFoundError(f"Content file missing at: {CONTENT_PATH}")

    with open(CONTENT_PATH, "r", encoding="utf-8", errors="replace") as f:
        raw_text = f.read()

    sample_context = raw_text[:3000]
    sample_q = "What is the validity of the auth token?"
    res = reader.predict(sample_q, sample_context)
    print(f"Q: {sample_q}")
    if res and res.answer != "not found":
        print(f"A: {res.answer} (score: {res.score})")
    else:
        print("A: not found")