"""Проверка настоящей FASHN через API приложения, без подмены результата."""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--steps", type=int, default=20)
    args = parser.parse_args()
    os.chdir(ROOT)
    # Временные задания не смешиваются с пользовательскими данными.
    os.environ["DATA_DIR"] = str(ROOT / ".verification" / "data")
    os.environ["API_KEYS"] = "verification-only-local-key"
    os.environ["DEFAULT_MODEL"] = "fashn-vton-1.5"
    os.environ["ENABLE_CATVTON_FLUX"] = "false"
    from fastapi.testclient import TestClient
    from PIL import Image
    import torch
    from app.config import get_settings
    from app.main import create_app
    from app.providers.device import pick_device

    get_settings.cache_clear()
    refs = ROOT / "app" / "static" / "references"
    evidence = ROOT / "docs" / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    key = {"X-API-Key": "verification-only-local-key"}
    started = time.perf_counter()
    with TestClient(create_app()) as client:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpx2").setLevel(logging.WARNING)
        health = client.get("/health").json()
        card = next(m for m in health["models"] if m["id"] == "fashn-vton-1.5")
        if not card["available"]:
            raise SystemExit(card["detail"])
        response = client.post(
            "/v1/try-on", headers=key,
            data={"model": "fashn-vton-1.5", "category": "tops",
                  "garment_photo_type": "flat-lay", "num_timesteps": str(args.steps),
                  "seed": "42", "segmentation_free": "true", "wait_seconds": "0"},
            files={"person_image": ("person.jpg", (refs / "person.jpg").read_bytes(), "image/jpeg"),
                   "garment_image": ("garment.jpg", (refs / "garment.jpg").read_bytes(), "image/jpeg")},
        )
        response.raise_for_status()
        job = response.json()
        print("Real FASHN job submitted", flush=True)
        last_step = None
        while job["status"] in {"queued", "running"}:
            if time.perf_counter() - started > args.timeout:
                raise SystemExit("Real inference exceeded the verification time limit")
            time.sleep(1)
            state = client.get(f"/v1/try-on/{job['id']}", headers=key)
            state.raise_for_status()
            job = state.json()
            marker = (job["status"], job.get("step"))
            if marker != last_step:
                print("Progress", *marker, flush=True)
                last_step = marker
        if job["status"] != "succeeded" or job["model"] != "fashn-vton-1.5" or job.get("warning"):
            raise SystemExit("Real inference failed: " + str(job.get("error")))
        result = client.get(job["result_url"], headers=key)
        result.raise_for_status()
        content = result.content
        image = Image.open(io.BytesIO(content))
        image.load()
        image_path = evidence / "real-tryon.png"
        image_path.write_bytes(content)
        report = {
            "verified_at_utc": datetime.now(timezone.utc).isoformat(),
            "model": job["model"], "status": job["status"], "device": pick_device(),
            "device_name": torch.xpu.get_device_name(0) if torch.xpu.is_available() else
                           torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
            "torch": torch.__version__, "steps": args.steps, "seed": 42,
            "cold_end_to_end_seconds": round(time.perf_counter() - started, 2),
            "width": image.width, "height": image.height,
            "result_sha256": hashlib.sha256(content).hexdigest(),
            "person_sha256": hashlib.sha256((refs / "person.jpg").read_bytes()).hexdigest(),
            "garment_sha256": hashlib.sha256((refs / "garment.jpg").read_bytes()).hexdigest(),
            "note": "One cold real inference through local API. Not a quality benchmark or a 5-second SLA.",
        }
        (evidence / "real-tryon.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
