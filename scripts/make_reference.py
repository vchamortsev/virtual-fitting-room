"""Снимает референс примерки для страницы заказчика и кладёт кадры в static."""

import shutil
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(r"C:\Users\User\.cursor\projects\c-projects-ai-learning-1-txt\assets")
OUT = ROOT / "app" / "static" / "references"
API = "http://127.0.0.1:8080"
KEY = {"X-API-Key": "local-dev-key"}


def main() -> None:
    person = ASSETS / "reference-person.jpg"
    garment = ASSETS / "reference-garment.jpg"
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(person, OUT / "person.jpg")
    shutil.copyfile(garment, OUT / "garment.jpg")
    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{API}/v1/try-on",
            headers=KEY,
            data={
                "category": "tops",
                "garment_photo_type": "flat-lay",
                "model": "fashn-vton-1.5",
                "segmentation_free": "false",
                "num_timesteps": "30",
                "seed": "42",
            },
            files={
                "person_image": ("person.jpg", person.read_bytes(), "image/jpeg"),
                "garment_image": ("garment.jpg", garment.read_bytes(), "image/jpeg"),
            },
        )
        response.raise_for_status()
        job = response.json()
        print("job", job["id"], job["status"], flush=True)
        for _ in range(80):
            current = client.get(f"{API}/v1/try-on/{job['id']}", headers=KEY)
            body = current.json()
            print(body["status"], flush=True)
            if body["status"] == "failed":
                raise SystemExit(body.get("error") or "failed")
            if body["status"] == "succeeded":
                result_url = body["result_url"]
                if result_url.startswith("/"):
                    result_url = API + result_url
                image = client.get(result_url, headers=KEY)
                image.raise_for_status()
                (OUT / "tryon.png").write_bytes(image.content)
                print("saved", len(image.content), flush=True)
                return
            time.sleep(3)
    raise SystemExit("timeout")


if __name__ == "__main__":
    main()
