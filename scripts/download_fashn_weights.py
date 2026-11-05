"""Скачивает веса FASHN VTON v1.5 и DWPose. Парсер человека качается при первой примерке."""

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Скачать локальные веса FASHN VTON 1.5")
    parser.add_argument("--weights-dir", default="weights/fashn-vton-1.5")
    args = parser.parse_args()

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("Сначала установите зависимости: pip install -r requirements-fashn.txt", file=sys.stderr)
        sys.exit(1)

    weights_dir = os.path.abspath(args.weights_dir)
    os.makedirs(os.path.join(weights_dir, "dwpose"), exist_ok=True)

    print(f"Каталог весов: {weights_dir}")
    hf_hub_download(
        repo_id="fashn-ai/fashn-vton-1.5",
        filename="model.safetensors",
        local_dir=weights_dir,
    )
    for filename in ("yolox_l.onnx", "dw-ll_ucoco_384.onnx"):
        hf_hub_download(
            repo_id="fashn-ai/DWPose",
            filename=filename,
            local_dir=os.path.join(weights_dir, "dwpose"),
        )
    print("Веса модели и DWPose на месте.")
    print("Парсер человека (~244 МБ) скачается сам при первой примерке.")


if __name__ == "__main__":
    main()
