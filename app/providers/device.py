"""Выбор устройства: NVIDIA CUDA, Intel XPU, иначе CPU."""


def pick_device(preferred: str = "") -> str:
    choice = preferred.strip().lower()
    if choice:
        return choice
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    xpu = getattr(torch, "xpu", None)
    if xpu is not None and xpu.is_available():
        return "xpu"
    return "cpu"
