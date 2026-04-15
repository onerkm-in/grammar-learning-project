from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import torch

from tiny_lm.model import ModelConfig, TinyTransformerLM


@dataclass
class TrainConfig:
    batch_size: int = 32
    block_size: int = 128
    n_embed: int = 128
    n_head: int = 4
    n_layer: int = 4
    dropout: float = 0.1
    learning_rate: float = 3e-4
    weight_decay: float = 0.01
    max_steps: int = 3000
    eval_interval: int = 200
    eval_batches: int = 25
    device: str = "cpu"
    seed: int = 1337


def load_text(data_dir: Path) -> tuple[str, str]:
    train_text = (data_dir / "train.txt").read_text(encoding="utf-8")
    val_text = (data_dir / "val.txt").read_text(encoding="utf-8")
    if len(train_text) < 2 or len(val_text) < 2:
        raise ValueError("Training and validation text must both contain at least 2 characters.")
    return train_text, val_text


def build_vocab(train_text: str, val_text: str) -> tuple[dict[str, int], dict[int, str]]:
    chars = sorted(set(train_text + val_text))
    stoi = {char: index for index, char in enumerate(chars)}
    itos = {index: char for char, index in stoi.items()}
    return stoi, itos


def encode(text: str, stoi: dict[str, int]) -> torch.Tensor:
    return torch.tensor([stoi[c] for c in text], dtype=torch.long)


def get_batch(
    data: torch.Tensor, batch_size: int, block_size: int, device: str
) -> tuple[torch.Tensor, torch.Tensor]:
    """Sample random next-token training windows from a flat token tensor."""
    max_start = len(data) - block_size - 1
    if max_start <= 0:
        raise ValueError("Dataset is too small for the selected block size.")

    indices = torch.randint(0, max_start, (batch_size,))
    x = torch.stack([data[i : i + block_size] for i in indices])
    y = torch.stack([data[i + 1 : i + block_size + 1] for i in indices])
    return x.to(device), y.to(device)


@torch.no_grad()
def estimate_loss(
    model: TinyTransformerLM,
    train_data: torch.Tensor,
    val_data: torch.Tensor,
    batch_size: int,
    block_size: int,
    eval_batches: int,
    device: str,
) -> dict[str, float]:
    """Run a small validation sweep so checkpoints can track generalization."""
    model.eval()
    losses: dict[str, float] = {}
    for split_name, split_data in (("train", train_data), ("val", val_data)):
        split_losses = torch.zeros(eval_batches)
        for i in range(eval_batches):
            xb, yb = get_batch(split_data, batch_size, block_size, device)
            _, loss = model(xb, yb)
            split_losses[i] = loss.item()
        losses[split_name] = split_losses.mean().item()
    model.train()
    return losses


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a tiny character-level LM.")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--block-size", type=int, default=128)
    parser.add_argument("--n-embed", type=int, default=128)
    parser.add_argument("--n-head", type=int, default=4)
    parser.add_argument("--n-layer", type=int, default=4)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--max-steps", type=int, default=3000)
    parser.add_argument("--eval-interval", type=int, default=200)
    parser.add_argument("--eval-batches", type=int, default=25)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--seed", type=int, default=1337)
    args = parser.parse_args()

    config = TrainConfig(
        batch_size=args.batch_size,
        block_size=args.block_size,
        n_embed=args.n_embed,
        n_head=args.n_head,
        n_layer=args.n_layer,
        dropout=args.dropout,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        max_steps=args.max_steps,
        eval_interval=args.eval_interval,
        eval_batches=args.eval_batches,
        device=args.device,
        seed=args.seed,
    )

    torch.manual_seed(config.seed)
    if config.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available.")

    train_text, val_text = load_text(args.data_dir)
    stoi, itos = build_vocab(train_text, val_text)
    train_data = encode(train_text, stoi)
    val_data = encode(val_text, stoi)

    model_config = ModelConfig(
        vocab_size=len(stoi),
        block_size=config.block_size,
        n_embed=config.n_embed,
        n_head=config.n_head,
        n_layer=config.n_layer,
        dropout=config.dropout,
    )
    model = TinyTransformerLM(model_config).to(config.device)

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)

    best_val = math.inf
    start_time = time.time()

    for step in range(config.max_steps + 1):
        if step % config.eval_interval == 0 or step == config.max_steps:
            # Periodic evaluation keeps the saved checkpoint aligned with the best val loss.
            losses = estimate_loss(
                model,
                train_data,
                val_data,
                config.batch_size,
                config.block_size,
                config.eval_batches,
                config.device,
            )
            elapsed = time.time() - start_time
            print(
                f"step {step:5d} | train loss {losses['train']:.4f} | "
                f"val loss {losses['val']:.4f} | elapsed {elapsed:.1f}s"
            )

            if losses["val"] < best_val:
                best_val = losses["val"]
                checkpoint = {
                    "model_state": model.state_dict(),
                    "model_config": model_config.to_dict(),
                    "train_config": asdict(config),
                    "stoi": stoi,
                    "itos": {str(k): v for k, v in itos.items()},
                    "best_val_loss": best_val,
                }
                torch.save(checkpoint, args.out_dir / "model.pt")

        if step == config.max_steps:
            break

        xb, yb = get_batch(train_data, config.batch_size, config.block_size, config.device)
        _, loss = model(xb, yb)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()

    summary = {
        "best_val_loss": best_val,
        "vocab_size": len(stoi),
        "train_characters": len(train_text),
        "val_characters": len(val_text),
        "model_config": model_config.to_dict(),
        "train_config": asdict(config),
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Saved best checkpoint to {(args.out_dir / 'model.pt').resolve()}")


if __name__ == "__main__":
    main()
