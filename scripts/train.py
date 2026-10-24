"""train.py — Train and save the ML scam classifier.

Usage:
    python -m scripts.train

Requires at least one of:
  - data/raw/fake_job_postings.csv  (Kaggle)
  - data/raw/hinglish_scam.json     (HuggingFace)

If neither is available, prints a message and exits cleanly.
"""

import json
import sys
import re
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
MODELS_DIR = Path(__file__).parent.parent / "models"
KAGGLE_FILE = RAW_DIR / "fake_job_postings.csv"
HF_FILE = RAW_DIR / "hinglish_scam.json"

KAGGLE_REQUIRED_COLS = {
    "job_id", "title", "description", "requirements", "benefits",
    "company_profile", "fraudulent"
}

MODELS_DIR.mkdir(parents=True, exist_ok=True)


def clean_text(text: str) -> str:
    """Lowercase, strip HTML, collapse whitespace, keep digits/currency."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_kaggle_data():
    """Load Kaggle fake_job_postings.csv. Returns (texts, labels) or ([], [])."""
    if not KAGGLE_FILE.exists():
        print(f"[train] Kaggle file not found: {KAGGLE_FILE}")
        return [], []
    try:
        import pandas as pd
        df = pd.read_csv(KAGGLE_FILE)
        missing = KAGGLE_REQUIRED_COLS - set(df.columns)
        if missing:
            print(f"[train] ERROR: Kaggle CSV missing columns: {missing}")
            print(f"[train] Available columns: {list(df.columns)}")
            return [], []
        text_cols = ["title", "description", "requirements", "benefits", "company_profile"]
        df[text_cols] = df[text_cols].fillna("")
        texts = (
            df["title"] + " " + df["description"] + " " +
            df["requirements"] + " " + df["benefits"] + " " +
            df["company_profile"]
        ).apply(clean_text).tolist()
        labels = df["fraudulent"].astype(int).tolist()
        n_scam = sum(labels)
        print(f"[train] Kaggle: {len(texts)} rows, {n_scam} fraudulent ({100*n_scam/len(texts):.1f}%)")
        return texts, labels
    except Exception as e:
        print(f"[train] Failed to load Kaggle data: {e}")
        return [], []


def load_hf_data():
    """Load HuggingFace hinglish scam JSON. Returns (texts, labels, hinglish_mask)."""
    if not HF_FILE.exists():
        print(f"[train] HF file not found: {HF_FILE}")
        return [], [], []
    try:
        with open(HF_FILE, "r", encoding="utf-8") as f:
            rows = json.load(f)

        # Normalize
        texts, labels, hinglish = [], [], []
        hinglish_keywords = re.compile(
            r"\b(aapka|namaste|jaldi|sirf|bhej|dijiye|pehle|hamari|mein|karein|hai)\b",
            re.IGNORECASE,
        )
        for row in rows:
            if isinstance(row, dict) and "row" in row:
                row = row["row"]
            if "text" not in row or "label" not in row:
                continue
            text = clean_text(str(row["text"]))
            label = int(row["label"])
            is_hinglish = bool(hinglish_keywords.search(text))
            texts.append(text)
            labels.append(label)
            hinglish.append(is_hinglish)

        n_scam = sum(labels)
        n_hin = sum(hinglish)
        print(f"[train] HF: {len(texts)} rows, {n_scam} scam, {n_hin} Hinglish rows")

        # Upsample Hinglish rows ×10
        extra_texts, extra_labels = [], []
        for t, l, h in zip(texts, labels, hinglish):
            if h:
                extra_texts.extend([t] * 9)  # +9 copies = ×10 total
                extra_labels.extend([l] * 9)

        texts += extra_texts
        labels += extra_labels
        if extra_texts:
            print(f"[train] After Hinglish ×10 upsample: {len(texts)} rows")

        return texts, labels, hinglish

    except Exception as e:
        print(f"[train] Failed to load HF data: {e}")
        return [], [], []


def print_metrics(name, y_true, y_pred):
    from sklearn.metrics import classification_report
    print(f"\n--- {name} metrics ---")
    print(classification_report(y_true, y_pred, target_names=["benign", "scam"], digits=3))


def train():
    import numpy as np

    kaggle_texts, kaggle_labels = load_kaggle_data()
    hf_texts, hf_labels, hf_hinglish = load_hf_data()

    all_texts = kaggle_texts + hf_texts
    all_labels = kaggle_labels + hf_labels

    if not all_texts:
        print("\n[train] No training data found. App will run in rules-only mode.")
        print("[train] Run: python -m scripts.download_data")
        sys.exit(0)

    print(f"\n[train] Total training samples: {len(all_texts)}")

    from sklearn.model_selection import StratifiedShuffleSplit
    from sklearn.pipeline import Pipeline
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import FeatureUnion
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score
    import joblib

    feature_union = FeatureUnion([
        ("word", TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=2,
            max_features=50_000,
        )),
        ("char", TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            max_features=100_000,
        )),
    ])

    pipeline = Pipeline([
        ("features", feature_union),
        ("clf", LogisticRegression(
            class_weight="balanced",
            max_iter=1000,
            C=1.0,
            random_state=42,
        )),
    ])

    # Stratified 80/20 split
    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    X = np.array(all_texts)
    y = np.array(all_labels)
    train_idx, test_idx = next(sss.split(X, y))

    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    print("[train] Fitting model ...")
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    overall_f1 = f1_score(y_test, y_pred, average="weighted")
    print(f"\n[train] Overall weighted F1: {overall_f1:.3f}")

    # Per-source metrics on test split
    # Kaggle test indices
    if kaggle_texts:
        kaggle_mask = test_idx < len(kaggle_texts)
        if any(kaggle_mask):
            print_metrics("Kaggle", y_test[kaggle_mask], y_pred[kaggle_mask])

    # HF test indices
    hf_start = len(kaggle_texts)
    hf_orig_count = len(hf_texts) - sum(1 for h in hf_hinglish if h) * 9 if hf_hinglish else len(hf_texts)
    hf_mask = (test_idx >= hf_start) & (test_idx < hf_start + hf_orig_count)
    if hf_texts and any(hf_mask):
        # English HF rows (non-Hinglish)
        hf_en_labels_test = y_test[hf_mask]
        hf_en_pred_test = y_pred[hf_mask]
        if len(hf_en_labels_test) > 0:
            print_metrics("HF-English", hf_en_labels_test, hf_en_pred_test)

    # Save model
    model_path = MODELS_DIR / "scam.joblib"
    joblib.dump({"pipeline": pipeline, "f1": float(overall_f1)}, model_path)
    print(f"\n[train] Model saved to {model_path}")
    print("[train] Done!")


if __name__ == "__main__":
    train()
