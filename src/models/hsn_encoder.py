"""
Contrastive MLP Architecture: src/models/hsn_encoder.py
PyTorch module executing purely on CPU.
Maps 32,768-dimensional token distributions to 128-dimensional unit hypersphere representations:
Input (32,768-D) -> Linear -> Hidden (512-D) -> ReLU -> Linear -> Embedding (128-D) -> L2 Normalize -> z
Dot-products on the unit hypersphere directly yield cosine similarity.
"""

from typing import Optional, Union
import torch
import torch.nn as nn
import torch.nn.functional as F


class HSNContrastiveMLP(nn.Module):
    """Contrastive Two-Layer MLP Projector for HSN Semantic Retrieval."""

    def __init__(
        self,
        input_dim: int = 32768,
        hidden_dim: int = 512,
        output_dim: int = 128,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim

        self.fc1 = nn.Linear(input_dim, hidden_dim, bias=True)
        self.relu = nn.ReLU()
        self.fc2 = nn.Linear(hidden_dim, output_dim, bias=False)

        # Initialize weights
        nn.init.kaiming_normal_(self.fc1.weight, nonlinearity="relu")
        nn.init.zeros_(self.fc1.bias)
        nn.init.xavier_normal_(self.fc2.weight)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass projecting sparse/dense feature distributions onto unit hypersphere.

        Args:
            x: Input tensor of shape (32768,) or (batch_size, 32768).

        Returns:
            L2-normalized embedding tensor z of shape (128,) or (batch_size, 128)
            satisfying ||z||_2 = 1.
        """
        is_1d = (x.dim() == 1)
        if is_1d:
            x = x.unsqueeze(0)

        # Handle sparse input if passed
        if x.is_sparse:
            x = x.to_dense()

        h = self.relu(self.fc1(x))
        out = self.fc2(h)

        # Project onto unit hypersphere
        z = F.normalize(out, p=2, dim=-1)

        if is_1d:
            return z.squeeze(0)
        return z

    @torch.no_grad()
    def encode(self, x: torch.Tensor) -> torch.Tensor:
        """Inference wrapper guaranteeing no gradient overhead."""
        self.eval()
        return self.forward(x)
