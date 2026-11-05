"""Два дополнительных референса: брюки и платье."""

import shutil
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(r"C:\Users\User\.cursor\projects\c-projects-ai-learning-1-txt\assets")
OUT = ROOT / "app" / "static" / "references"
API = "http://127.0.0.1:8080"
KEY = {"X-API-Key": "local-dev-key"}

SETS = (
    ("person-2.jpg", "garment-2.jpg", "tryon-2.png", "bottoms", "43"),
    ("person-3.jpg", "garment-3.jpg", "tryon-3.png", "one-pieces", "44"),
)


def wait_result(client: httpx.Client, job_id: str) -> bytes:
    for _ in range(100):
        body = client.get(f"{API}/v1/try-on/{job_id}", headers=KEY).json()
        print(job_id, body.get("status"), body.get("step"), body.get("steps"), flush=True)
        if body["status"] == "failed":
            raise SystemExit(body.get("error") or "failed")
        if body["status"] == "succeeded":
            result_url = body["result_url"]
            if result_url.startswith("/"):
                result_url = API + result_url
            image = client.get(result_url, headers=KEY)
            image.raise_for_status()
            return image.content
        time.sleep(3)
    raise SystemExit(f"timeout {job_id}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60) as client:
        health = client.get(f"{API}/health")
        health.raise_for_status()
        for person_name, garment_name, out_name, category, seed in SETS:
            person = ASSETS / person_name
            garment = ASSETS / garment_name
            shutil.copyfile(person, OUT / person_name)
            shutil.copyfile(garment, OUT / garment_name)
            response = client.post(
                f"{API}/v1/try-on",
                headers=KEY,
                data={
                    "category": category,
                    "garment_photo_type": "flat-lay",
                    "model": "fashn-vton-1.5",
                    "segmentation_free": "false",
                    "num_timesteps": "30",
                    "seed": seed,
                },
                files={
                    "person_image": (person_name, person.read_bytes(), "image/jpeg"),
                    "garment_image": (garment_name, garment.read_bytes(), "image/jpeg"),
                },
            )
            response.raise_for_status()
            job = response.json()
            print("job", job["id"], category, job["status"], flush=True)
            if job["status"] == "succeeded" and job.get("result_url"):
                result_url = job["result_url"]
                if result_url.startswith("/"):
                    result_url = API + result_url
                image = client.get(result_url, headers=KEY)
                image.raise_for_status()
                content = image.content
            else:
                content = wait_result(client, job["id"])
            (OUT / out_name).write_bytes(content)
            print("saved", out_name, len(content), flush=True)


if __name__ == "__main__":
    main()
