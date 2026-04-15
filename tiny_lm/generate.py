from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch

from tiny_lm.model import ModelConfig, TinyTransformerLM


def load_checkpoint(checkpoint_path: Path, device: str) -> tuple[TinyTransformerLM, dict[str, int], dict[int, str]]:
    checkpoint = torch.load(checkpoint_path, map_location=device)
    config = ModelConfig(**checkpoint["model_config"])
    model = TinyTransformerLM(config)
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    model.eval()

    stoi = checkpoint["stoi"]
    raw_itos = checkpoint["itos"]
    itos = {int(k): v for k, v in raw_itos.items()}
    return model, stoi, itos


def encode_prompt(prompt: str, stoi: dict[str, int]) -> list[int]:
    unknown = sorted(set(char for char in prompt if char not in stoi))
    if unknown:
        joined = "".join(unknown)
        raise ValueError(
            f"Prompt contains characters not seen during training: {joined!r}. "
            "Try a simpler prompt from the dataset's character set."
        )
    return [stoi[c] for c in prompt]


def decode(tokens: torch.Tensor, itos: dict[int, str]) -> str:
    return "".join(itos[int(token)] for token in tokens.tolist())


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Generate text from a tiny LM checkpoint.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--prompt", type=str, default="English grammar")
    parser.add_argument("--max-new-tokens", type=int, default=300)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--device", type=str, default="cpu")
    args = parser.parse_args()

    if args.device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available.")

    model, stoi, itos = load_checkpoint(args.checkpoint, args.device)
    prompt_ids = encode_prompt(args.prompt, stoi)
    context = torch.tensor([prompt_ids], dtype=torch.long, device=args.device)
    output = model.generate(
        context,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_k=args.top_k,
    )
    print(decode(output[0], itos))


if __name__ == "__main__":
    main()
