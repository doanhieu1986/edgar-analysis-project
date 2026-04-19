"""
Trade War relevance classifier — score 0-1
==========================================
Labels:  1 = Trade War relevant  (from label_data/)
         0 = Not relevant        (sampled from cleaned_data, no TW keywords)

Output:  outputs/labeled_dataset.parquet   — labeled training set
         outputs/predictions.parquet       — full cleaned_data with score column
"""

import re
import sys
import argparse
import numpy as np
import pandas as pd
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import StratifiedKFold, cross_validate
from sklearn.metrics import (
    classification_report, roc_auc_score,
    precision_recall_curve, average_precision_score,
)

OUTPUTS_DIR   = Path(__file__).parent.parent / "outputs"
LABEL_DIR     = Path(__file__).parent.parent / "label_data"
CLEANED_FILE  = OUTPUTS_DIR / "cleaned_data.parquet"
LABELED_FILE  = OUTPUTS_DIR / "labeled_dataset.parquet"
PRED_FILE     = OUTPUTS_DIR / "predictions.parquet"

# Keywords used to exclude obvious negatives (avoid leaking TW signal into neg class)
TW_KEYWORD_PATTERN = re.compile(
    r"tariff|trade.{0,5}war|trade.{0,5}barrier|trade.{0,5}tension|"
    r"retaliator|protectionism|trade.{0,5}sanction|trade.{0,5}dispute|"
    r"import.{0,5}dut|export.{0,5}control|trade.{0,5}conflict",
    re.IGNORECASE,
)

NEGATIVE_RATIO = 3   # negatives per positive
RANDOM_STATE   = 42


# ---------------------------------------------------------------------------
# Step 1: Build labeled dataset
# ---------------------------------------------------------------------------

def load_label_files() -> pd.DataFrame:
    df1 = pd.read_csv(LABEL_DIR / "label2018.csv")
    df2 = pd.read_csv(LABEL_DIR / "label_pre2018.csv")
    combined = pd.concat([df1, df2], ignore_index=True).dropna(subset=["cik"])
    combined["cik_int"] = combined["cik"].astype(int)
    combined["year_int"] = combined["year"].astype(int)
    return combined


def build_labeled_dataset(df_clean: pd.DataFrame, labels: pd.DataFrame,
                           neg_ratio: int = NEGATIVE_RATIO) -> pd.DataFrame:
    df_clean = df_clean.copy()
    df_clean["cik_int"] = df_clean["cik"].str.lstrip("0").astype(int)
    df_clean["year_int"] = df_clean["year"].astype(int)

    # Positives: join label keys onto cleaned data
    positives = labels.merge(
        df_clean, on=["year_int", "cik_int"], how="inner"
    )[["year_int", "cik_int", "filename", "item_1a_clean", "label"]]

    print(f"  Positives matched: {len(positives)}")

    # Negatives: rows with NO trade war keywords, not already in positives pool
    pos_keys = set(zip(positives["year_int"], positives["cik_int"]))
    mask_not_pos = ~df_clean.apply(
        lambda r: (r["year_int"], r["cik_int"]) in pos_keys, axis=1
    )
    mask_no_kw = ~df_clean["item_1a_clean"].str.contains(TW_KEYWORD_PATTERN)
    negatives_pool = df_clean[mask_not_pos & mask_no_kw]

    n_neg = len(positives) * neg_ratio
    negatives = negatives_pool.sample(
        min(n_neg, len(negatives_pool)), random_state=RANDOM_STATE
    )[["year_int", "cik_int", "filename", "item_1a_clean"]].copy()
    negatives["label"] = 0

    print(f"  Negatives sampled: {len(negatives)} (ratio 1:{neg_ratio})")

    dataset = pd.concat([positives, negatives], ignore_index=True).sample(
        frac=1, random_state=RANDOM_STATE
    ).reset_index(drop=True)

    return dataset


# ---------------------------------------------------------------------------
# Step 2: Train & evaluate
# ---------------------------------------------------------------------------

def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=20_000,
            sublinear_tf=True,
            min_df=2,
        )),
        ("clf", LogisticRegression(
            C=1.0,
            class_weight="balanced",
            max_iter=1000,
            random_state=RANDOM_STATE,
        )),
    ])


def evaluate(dataset: pd.DataFrame) -> Pipeline:
    X = dataset["item_1a_clean"].values
    y = dataset["label"].values

    print(f"\n  Dataset: {len(dataset)} rows | Pos: {y.sum()} | Neg: {(y==0).sum()}")

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    pipeline = build_pipeline()

    scores = cross_validate(
        pipeline, X, y, cv=cv, scoring=["roc_auc", "average_precision"],
        return_train_score=False,
    )

    print(f"\n  === 5-fold Cross-Validation ===")
    print(f"  ROC-AUC:  {scores['test_roc_auc'].mean():.3f}  ±{scores['test_roc_auc'].std():.3f}")
    print(f"  PR-AUC:   {scores['test_average_precision'].mean():.3f}  ±{scores['test_average_precision'].std():.3f}")

    # Final fit on full dataset for inspection
    pipeline.fit(X, y)

    # Detailed report on training set (indicative)
    y_pred = pipeline.predict(X)
    y_score = pipeline.predict_proba(X)[:, 1]
    print(f"\n  === Classification Report (train set — indicative) ===")
    print(classification_report(y, y_pred, target_names=["Not TW", "Trade War"]))
    print(f"  ROC-AUC (train): {roc_auc_score(y, y_score):.3f}")

    # Top features
    feat_names = pipeline.named_steps["tfidf"].get_feature_names_out()
    coef = pipeline.named_steps["clf"].coef_[0]
    top_pos = np.argsort(coef)[-15:][::-1]
    top_neg = np.argsort(coef)[:15]
    print(f"\n  Top TW-relevant features:")
    for i in top_pos:
        print(f"    +{coef[i]:.2f}  {feat_names[i]}")
    print(f"\n  Top NOT-TW features:")
    for i in top_neg:
        print(f"    {coef[i]:.2f}  {feat_names[i]}")

    return pipeline


# ---------------------------------------------------------------------------
# Step 3: Score full cleaned_data
# ---------------------------------------------------------------------------

def score_full_dataset(pipeline: Pipeline, df_clean: pd.DataFrame) -> pd.DataFrame:
    scores = pipeline.predict_proba(df_clean["item_1a_clean"].values)[:, 1]
    df_out = df_clean[["year", "quarter", "filename", "cik", "filed_date",
                        "form_type", "conformed_period", "item_1a_clean"]].copy()
    df_out["tw_score"] = scores
    df_out = df_out.sort_values("tw_score", ascending=False).reset_index(drop=True)
    return df_out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Train Trade War relevance classifier.")
    parser.add_argument("--neg-ratio", type=int, default=NEGATIVE_RATIO,
                        help=f"Negatives per positive (default: {NEGATIVE_RATIO})")
    parser.add_argument("--no-predict", action="store_true",
                        help="Skip scoring full dataset")
    args = parser.parse_args()

    print("=== Step 1: Build labeled dataset ===")
    df_clean = pd.read_parquet(CLEANED_FILE)
    labels   = load_label_files()
    dataset  = build_labeled_dataset(df_clean, labels, neg_ratio=args.neg_ratio)
    dataset.to_parquet(LABELED_FILE, index=False)
    print(f"  Saved → {LABELED_FILE}")

    print("\n=== Step 2: Train & evaluate ===")
    pipeline = evaluate(dataset)

    if not args.no_predict:
        print("\n=== Step 3: Score full cleaned_data ===")
        df_pred = score_full_dataset(pipeline, df_clean)
        df_pred.to_parquet(PRED_FILE, index=False)
        size_mb = PRED_FILE.stat().st_size / 1024 / 1024
        print(f"  Saved → {PRED_FILE}  ({size_mb:.1f} MB)")

        print(f"\n  Score distribution:")
        print(df_pred["tw_score"].describe().apply(lambda x: f"{x:.4f}"))

        print(f"\n  Top 15 highest-scoring docs:")
        cols = ["year", "filename", "tw_score"]
        print(df_pred[cols].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
