"""download_data.py — Download datasets for scam ML model.

Tries Kaggle CLI first, then prints manual steps.
HuggingFace dataset downloaded automatically.
"""

import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

KAGGLE_FILE = RAW_DIR / "fake_job_postings.csv"
HF_FILE = RAW_DIR / "hinglish_scam.json"


def download_kaggle():
    """Try to download Kaggle dataset."""
    if KAGGLE_FILE.exists():
        print(f"[kaggle] Already exists: {KAGGLE_FILE}")
        return True
    try:
        import subprocess
        result = subprocess.run(
            [
                "kaggle", "datasets", "download",
                "-d", "shivamb/real-or-fake-fake-jobposting-prediction",
                "--unzip", "-p", str(RAW_DIR),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("[kaggle] Download successful.")
            return True
        else:
            print(f"[kaggle] Download failed: {result.stderr}")
    except FileNotFoundError:
        print("[kaggle] Kaggle CLI not found.")
    except Exception as e:
        print(f"[kaggle] Error: {e}")

    print("\n=== MANUAL STEPS to get fake_job_postings.csv ===")
    print("1. Go to: https://www.kaggle.com/datasets/shivamb/real-or-fake-fake-jobposting-prediction")
    print("2. Click 'Download' (requires Kaggle login)")
    print("3. Unzip and place 'fake_job_postings.csv' at:")
    print(f"   {KAGGLE_FILE}")
    print("Or install kaggle CLI: pip install kaggle")
    print("Set credentials in ~/.kaggle/kaggle.json")
    print("Then re-run: python -m scripts.download_data")
    return False


def download_huggingface():
    """Download HuggingFace hinglish scam dataset."""
    if HF_FILE.exists():
        print(f"[hf] Already exists: {HF_FILE}")
        return True
    try:
        from huggingface_hub import HfApi, hf_hub_download

        api = HfApi()
        files = list(api.list_repo_files(
            "bolewara/hinglish-scam-text-dataset",
            repo_type="dataset",
        ))
        json_files = [f for f in files if f.endswith(".json")]
        if not json_files:
            print("[hf] No JSON file found in repository.")
            return False

        target = json_files[0]
        print(f"[hf] Downloading {target} ...")
        local_path = hf_hub_download(
            repo_id="bolewara/hinglish-scam-text-dataset",
            filename=target,
            repo_type="dataset",
        )

        # Normalize to list of {"text": ..., "label": ...}
        with open(local_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        rows = []
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict) and "rows" in raw:
            items = raw["rows"]
        else:
            items = list(raw.values())[0] if raw else []

        for item in items:
            if isinstance(item, dict) and "row" in item:
                item = item["row"]
            if "text" in item and "label" in item:
                rows.append({"text": item["text"], "label": int(item["label"])})

        with open(HF_FILE, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)

        print(f"[hf] Saved {len(rows)} rows to {HF_FILE}")
        return True

    except Exception as e:
        print(f"[hf] Failed to download HuggingFace dataset: {e}")
        return False


if __name__ == "__main__":
    print("=== Downloading datasets ===\n")
    hf_ok = download_huggingface()
    kaggle_ok = download_kaggle()
    print("\n=== Summary ===")
    print(f"HuggingFace (hinglish_scam.json): {'✓' if hf_ok else '✗'}")
    print(f"Kaggle (fake_job_postings.csv):   {'✓' if kaggle_ok else '✗'}")
    if hf_ok or kaggle_ok:
        print("\nRun training: python -m scripts.train")
    else:
        print("\nNo datasets available — app will run in rules-only mode.")
