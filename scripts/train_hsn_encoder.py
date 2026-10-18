"""
Contrastive Training Pipeline: scripts/train_hsn_encoder.py
Trains the HSNContrastiveMLP with InfoNCE Loss (temperature tau = 0.07) on CPU.
Synthesizes positive pairs and hard negatives from statutory tariff master,
chapter overlaps (e.g., Chapter 73 steel fittings vs. Chapter 84 valves),
and historical invoice training records.
Saves trained weights to models/hsn_contrastive_mlp.pt.
"""

import os
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

import sys
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

TARIFF_PARQUET = ROOT_DIR / "data" / "tariff_master.parquet"
TRAIN_PARQUET = ROOT_DIR / "data" / "train.parquet"
VAL_PARQUET = ROOT_DIR / "data" / "val.parquet"
OUTPUT_MODEL_DIR = ROOT_DIR / "models"
OUTPUT_MODEL_PATH = OUTPUT_MODEL_DIR / "hsn_contrastive_mlp.pt"

from src.models.tokenizer import FeatureHashingTokenizer
from src.models.hsn_encoder import HSNContrastiveMLP

# Temperature hyperparameter as per specification
TAU = 0.07

# Chapter confusion / overlap mapping for hard negative mining
CHAPTER_OVERLAPS = {
    "73": ["84", "72", "76", "83"],  # Iron/steel articles vs machinery/valves
    "84": ["73", "85", "90"],        # Machinery/valves vs steel articles/electrical
    "85": ["84", "90", "85"],        # Electrical vs mechanical/instruments
    "39": ["40", "48", "38"],        # Plastics vs rubber
    "40": ["39", "87"],              # Rubber vs plastics
    "28": ["29", "38"],              # Inorganic vs organic/misc chemicals
    "29": ["28", "38", "30"],        # Organic chemicals vs pharmaceuticals
    "01": ["02", "03", "04"],        # Live animals vs meat/dairy
    "02": ["01", "03", "16"],        # Meat vs animals/meat preps
    "61": ["62", "63", "52"],        # Knitted apparel vs woven apparel
    "62": ["61", "63", "54"],        # Woven apparel vs knitted apparel
    "87": ["84", "85", "86"],        # Vehicles vs parts/machinery
}

COMMON_TRADE_EXPANSIONS = {
    "ss": "stainless steel",
    "ms": "mild steel",
    "ci": "cast iron",
    "gi": "galvanized iron",
    "pvc": "polyvinyl chloride",
    "cs": "carbon steel",
    "al": "aluminium",
    "cu": "copper",
    "assy": "assembly",
    "mfg": "manufacturing",
    "flg": "flange",
    "vlv": "valve",
    "pmp": "pump",
    "ht": "high tensile",
}


def synthesize_noisy_invoice_text(clean_desc: str, hsn_code: str) -> str:
    """Generates synthetic noisy invoice variations (trade slang, abbreviations, specs)."""
    words = clean_desc.split()
    if not words:
        return clean_desc

    tokens = []
    for w in words:
        w_lower = w.lower()
        if w_lower in COMMON_TRADE_EXPANSIONS and random.random() < 0.5:
            tokens.append(COMMON_TRADE_EXPANSIONS[w_lower])
        else:
            tokens.append(w)

    # Invert some expansions into trade abbreviations
    rev_exp = {v: k for k, v in COMMON_TRADE_EXPANSIONS.items()}
    text = " ".join(tokens)
    for phrase, abbr in rev_exp.items():
        if phrase in text.lower() and random.random() < 0.6:
            text = re_sub_case_insensitive(phrase, abbr.upper(), text)

    # Inject random specs or part numbers with 40% probability
    if random.random() < 0.4:
        specs = random.choice([
            "25MM", "50MM", "100MM", "CLASS 150", "PN16", "SCH 40", "GRADE A",
            "TYPE 304", "TYPE 316", "DIA 2 INCH", "10 BAR", "OEM SPEC", "HEAVY DUTY"
        ])
        text = f"{text} {specs}"

    return text


def re_sub_case_insensitive(pattern: str, replacement: str, text: str) -> str:
    import re
    return re.sub(re.escape(pattern), replacement, text, flags=re.IGNORECASE)


class ContrastiveTripletDataset(Dataset):
    """Dataset producing (anchor_vec, positive_vec, hard_negative_vec) tensors."""

    def __init__(
        self,
        anchors: torch.Tensor,
        positives: torch.Tensor,
        hard_negatives: torch.Tensor,
    ):
        self.anchors = anchors
        self.positives = positives
        self.hard_negatives = hard_negatives

    def __len__(self) -> int:
        return self.anchors.size(0)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        return self.anchors[idx], self.positives[idx], self.hard_negatives[idx]


def build_training_pairs(
    tariff_df: pd.DataFrame,
    train_df: Optional[pd.DataFrame] = None,
) -> Tuple[List[str], List[str], List[str]]:
    """Synthesizes high-fidelity (anchor, positive, hard_negative) text triplets."""
    print("[*] Mining and synthesizing contrastive training triplets...")
    anchors: List[str] = []
    positives: List[str] = []
    hard_negatives: List[str] = []

    # Map chapter to descriptions for mining chapter overlaps
    chapter_to_descs: Dict[str, List[str]] = {}
    hsn_to_desc: Dict[str, str] = {}

    for _, row in tariff_df.iterrows():
        ch = str(row["chapter"]).zfill(2)
        code = str(row["hsn_code"]).zfill(4)
        desc = str(row["description"])
        hsn_to_desc[code] = desc
        if ch not in chapter_to_descs:
            chapter_to_descs[ch] = []
        chapter_to_descs[ch].append(desc)

    all_descs = list(tariff_df["description"].dropna().unique())

    # 1. From Tariff Master: Statutory descriptions and synthetic noisy variations
    for _, row in tariff_df.iterrows():
        code = str(row["hsn_code"]).zfill(4)
        ch = str(row["chapter"]).zfill(2)
        statutory_desc = str(row["description"])
        if not statutory_desc or len(statutory_desc) < 4:
            continue

        # Generate 2-3 noisy variants
        for _ in range(2):
            noisy_anchor = synthesize_noisy_invoice_text(statutory_desc, code)
            positives.append(statutory_desc)
            anchors.append(noisy_anchor)

            # Hard negative mining: Pick from overlapping chapters if available
            neg_candidates = []
            if ch in CHAPTER_OVERLAPS:
                for conf_ch in CHAPTER_OVERLAPS[ch]:
                    if conf_ch in chapter_to_descs and chapter_to_descs[conf_ch]:
                        neg_candidates.extend(chapter_to_descs[conf_ch])

            if neg_candidates:
                hard_neg = random.choice(neg_candidates)
            else:
                hard_neg = random.choice(all_descs)
            hard_negatives.append(hard_neg)

    # 2. From train.parquet if available (Real-world invoice line items)
    if train_df is not None and not train_df.empty:
        print(f"[*] Incorporating {len(train_df)} historical training invoice records...")
        for _, row in train_df.iterrows():
            prod_desc = str(row.get("product_description", ""))
            stat_desc = str(row.get("official_statutory_description", ""))
            true_hsn = str(row.get("true_hsn", "")).zfill(4)
            ch = true_hsn[:2]

            if not prod_desc or not stat_desc or stat_desc == "nan":
                continue

            anchors.append(prod_desc)
            positives.append(stat_desc)

            # Hard negative
            neg_candidates = []
            if ch in CHAPTER_OVERLAPS:
                for conf_ch in CHAPTER_OVERLAPS[ch]:
                    if conf_ch in chapter_to_descs and chapter_to_descs[conf_ch]:
                        neg_candidates.extend(chapter_to_descs[conf_ch])
            if neg_candidates:
                hard_neg = random.choice(neg_candidates)
            else:
                hard_neg = random.choice(all_descs)
            hard_negatives.append(hard_neg)

    print(f"[OK] Total synthesized triplets: {len(anchors)}")
    return anchors, positives, hard_negatives


class InfoNCELoss(nn.Module):
    """InfoNCE Loss with temperature tau and in-batch + hard negatives.

    L = -log( exp(z_a . z_p / tau) / ( exp(z_a . z_p / tau) + sum_k exp(z_a . z_neg_k / tau) ) )
    """

    def __init__(self, tau: float = TAU):
        super().__init__()
        self.tau = tau

    def forward(
        self,
        z_anchor: torch.Tensor,
        z_positive: torch.Tensor,
        z_hard_neg: torch.Tensor,
    ) -> torch.Tensor:
        """Computes InfoNCE loss.

        Args:
            z_anchor: (B, 128) unit vectors
            z_positive: (B, 128) unit vectors
            z_hard_neg: (B, 128) unit vectors
        """
        b_size = z_anchor.size(0)

        # Cosine similarity matrix between anchors and positives: (B, B)
        sim_matrix = torch.matmul(z_anchor, z_positive.T) / self.tau

        # Hard negative similarity: (B, 1)
        sim_hard_neg = torch.sum(z_anchor * z_hard_neg, dim=1, keepdim=True) / self.tau

        # Full logits: (B, B + 1)
        # sim_matrix[:, i] is positive for anchor i, all j != i are in-batch negatives.
        # sim_hard_neg is explicit hard negative.
        logits = torch.cat([sim_matrix, sim_hard_neg], dim=1)

        # Ground truth positive targets are the diagonal indices 0, 1, ..., B-1
        targets = torch.arange(b_size, dtype=torch.long, device=z_anchor.device)

        loss = F.cross_entropy(logits, targets)
        return loss


def train_encoder(
    epochs: int = 18,
    batch_size: int = 64,
    learning_rate: float = 1e-3,
    weight_decay: float = 1e-4,
) -> HSNContrastiveMLP:
    """Trains the HSN Contrastive MLP on CPU and saves model weights."""
    print("=" * 65)
    print("      TRAINING IN-HOUSE CONTRASTIVE SEMANTIC HSN ENCODER      ")
    print(f"      PyTorch CPU-Only | Temperature tau = {TAU} | Epochs = {epochs}")
    print("=" * 65)

    OUTPUT_MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load Data
    tariff_df = pd.read_parquet(TARIFF_PARQUET)
    train_df = pd.read_parquet(TRAIN_PARQUET) if TRAIN_PARQUET.exists() else None

    anchors_text, positives_text, hard_negs_text = build_training_pairs(tariff_df, train_df)

    # 2. Tokenize into 32,768-D feature space
    print("[*] Vectorizing text pairs into fixed 32,768-D hashed representations...")
    t0_tok = time.perf_counter()
    tokenizer = FeatureHashingTokenizer(dim=32768)

    anchors_tensor = tokenizer.batch_tokenize(anchors_text)
    positives_tensor = tokenizer.batch_tokenize(positives_text)
    hard_negs_tensor = tokenizer.batch_tokenize(hard_negs_text)
    print(f"[OK] Vectorization complete in {time.perf_counter() - t0_tok:.2f}s. Tensor shape: {anchors_tensor.shape}")

    dataset = ContrastiveTripletDataset(anchors_tensor, positives_tensor, hard_negs_tensor)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=True)

    # 3. Initialize Model and Optimizer
    model = HSNContrastiveMLP(input_dim=32768, hidden_dim=512, output_dim=128)
    model.train()

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-5)
    criterion = InfoNCELoss(tau=TAU)

    # 4. Training Loop
    total_steps = len(dataloader)
    print(f"[*] Starting training: {epochs} epochs, {total_steps} steps/epoch...")

    for epoch in range(1, epochs + 1):
        epoch_loss = 0.0
        t0 = time.perf_counter()

        for step, (a_batch, p_batch, neg_batch) in enumerate(dataloader):
            optimizer.zero_grad()

            z_a = model(a_batch)
            z_p = model(p_batch)
            z_neg = model(neg_batch)

            loss = criterion(z_a, z_p, z_neg)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()

        scheduler.step()
        avg_loss = epoch_loss / total_steps
        elapsed = time.perf_counter() - t0
        print(f"  Epoch [{epoch:02d}/{epochs:02d}] | InfoNCE Loss: {avg_loss:.4f} | LR: {scheduler.get_last_lr()[0]:.6f} | Elapsed: {elapsed:.2f}s")

    # 5. Save weights
    print(f"[*] Saving trained weights to {OUTPUT_MODEL_PATH}...")
    torch.save(model.state_dict(), OUTPUT_MODEL_PATH)
    print(f"[OK] Contrastive MLP weights saved successfully. File size: {OUTPUT_MODEL_PATH.stat().st_size / 1024:.1f} KB")

    return model


if __name__ == "__main__":
    train_encoder()
