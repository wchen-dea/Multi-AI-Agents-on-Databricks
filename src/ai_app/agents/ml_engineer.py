from .base import BaseSpecialistAgent

_SYSTEM = """You are a senior machine learning engineer specializing in model development, training pipelines, and MLOps.

Your responsibilities:
- Design and implement ML models (scikit-learn, PyTorch, TensorFlow/Keras)
- Build training pipelines with experiment tracking (MLflow, Weights & Biases)
- Feature engineering, preprocessing pipelines (pandas, NumPy, scikit-learn Pipelines)
- Hyperparameter optimization (Optuna, Ray Tune)
- Model evaluation, cross-validation, metrics analysis
- Model serialization and versioning (joblib, ONNX, TorchScript)
- Write training scripts, notebooks, and reproducible experiments
- Implement data augmentation, class imbalance handling, regularization

When writing code:
- Use type hints throughout
- Write modular, reusable pipeline components
- Include proper train/val/test splits
- Log metrics and artifacts systematically
- Write reproducible code (set seeds)
- Include model evaluation reports with key metrics (accuracy, F1, AUC, RMSE, etc.)
- Document data assumptions and feature expectations

Always produce working, production-ready ML code."""


class MLEngineerAgent(BaseSpecialistAgent):
    name = "ml_engineer"
    role = "Machine Learning Engineer"
    system_prompt = _SYSTEM
    _MCP_ALLOWED_SOURCE = "databricks_feature_store"
    extra_tools = [
        {
            "name": "scaffold_training_script",
            "description": "Scaffold a PyTorch training script with train/val loop boilerplate.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "model_name": {"type": "string", "description": "Model class name."},
                    "task": {
                        "type": "string",
                        "enum": ["classification", "regression"],
                        "description": "Task type.",
                    },
                    "path": {"type": "string", "description": "Output file path."},
                },
                "required": ["model_name", "task", "path"],
            },
        }
    ]

    def _dispatch_tool(self, name: str, inputs: dict) -> str:
        if name == "mcp_retrieve":
            source = inputs.get("source_type", self._MCP_ALLOWED_SOURCE)
            if source != self._MCP_ALLOWED_SOURCE:
                return (
                    "ERROR: ml_engineer is restricted to Feature Store retrieval only. "
                    "Use source_type='databricks_feature_store'."
                )
            return self._mcp_retrieve(
                source_type=self._MCP_ALLOWED_SOURCE,
                query=inputs["query"],
                top_k=inputs.get("top_k", 5),
            )

        if name == "scaffold_training_script":
            model_name = inputs["model_name"]
            task = inputs["task"]
            path = inputs["path"]
            loss = "nn.CrossEntropyLoss()" if task == "classification" else "nn.MSELoss()"
            metric = "accuracy" if task == "classification" else "rmse"
            code = f'''"""Training script for {model_name} ({task})."""

import random
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from typing import Tuple


def set_seed(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class {model_name}(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, output_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: nn.Module,
    device: torch.device,
) -> float:
    model.train()
    total_loss = 0.0
    for X, y in loader:
        X, y = X.to(device), y.to(device)
        optimizer.zero_grad()
        loss = criterion(model(X), y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * len(X)
    return total_loss / len(loader.dataset)


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> Tuple[float, float]:
    model.eval()
    total_loss, correct = 0.0, 0
    for X, y in loader:
        X, y = X.to(device), y.to(device)
        preds = model(X)
        total_loss += criterion(preds, y).item() * len(X)
        correct += (preds.argmax(1) == y).sum().item()
    n = len(loader.dataset)
    return total_loss / n, correct / n


def main() -> None:
    set_seed(42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # ── Data (replace with real data loading) ────────────────────────────────
    X = torch.randn(1000, 16)
    y = torch.randint(0, 2, (1000,))
    split = 800
    train_ds = TensorDataset(X[:split], y[:split])
    val_ds = TensorDataset(X[split:], y[split:])
    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=64)

    # ── Model ─────────────────────────────────────────────────────────────────
    model = {model_name}(input_dim=16, hidden_dim=64, output_dim=2).to(device)
    criterion = {loss}
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=20)

    best_val_loss = float("inf")
    for epoch in range(1, 21):
        train_loss = train_epoch(model, train_loader, optimizer, criterion, device)
        val_loss, val_{metric} = evaluate(model, val_loader, criterion, device)
        scheduler.step()

        print(f"Epoch {{epoch:3d}} | train_loss={{train_loss:.4f}} | val_loss={{val_loss:.4f}} | val_{metric}={{val_{metric}:.4f}}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), "best_model.pt")
            print("  → Saved best model.")

    print(f"Training complete. Best val loss: {{best_val_loss:.4f}}")


if __name__ == "__main__":
    main()
'''
            self._write_file(path, code)
            return f"Scaffolded {model_name} training script → {path}"
        return super()._dispatch_tool(name, inputs)
