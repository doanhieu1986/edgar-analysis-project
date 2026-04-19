"""
Trade War relevance scorer — Qwen2.5-7B via Ollama
===================================================
Đo mức độ text 10-K *đề cập / mô tả* rủi ro Trade War (Option A).

Score 0.0–1.0:
  0.0  Không đề cập gì đến trade war / thương mại quốc tế
  0.3  Đề cập gián tiếp (vd: "trade policy uncertainty")
  0.6  Đề cập rõ tariff / trade war như một risk factor
  1.0  Mô tả chi tiết, cụ thể tác động trade war lên công ty

Usage:
  python scripts/score_with_llm.py               # score toàn bộ
  python scripts/score_with_llm.py --limit 100   # test 100 docs
  python scripts/score_with_llm.py --workers 6   # tăng concurrency
  python scripts/score_with_llm.py --resume      # tiếp tục nếu bị gián đoạn

Output:
  outputs/predictions.parquet   — full dataset + cột tw_score
"""

import json
import asyncio
import argparse
import re
import sys
from pathlib import Path

import httpx
import pandas as pd
from tqdm.asyncio import tqdm as atqdm

OUTPUTS_DIR    = Path(__file__).parent.parent / "outputs"
CLEANED_FILE   = OUTPUTS_DIR / "cleaned_data.parquet"
PRED_FILE      = OUTPUTS_DIR / "predictions.parquet"
CHECKPOINT_FILE = OUTPUTS_DIR / "scoring_checkpoint.parquet"

OLLAMA_URL  = "http://localhost:11434/api/generate"
MODEL       = "qwen2.5:7b"
TIMEOUT     = 60        # seconds per request
MAX_RETRIES = 3
CHECKPOINT_EVERY = 200  # save checkpoint every N docs
DEFAULT_WORKERS  = 4    # concurrent requests

PROMPT_TEMPLATE = """\
Score how explicitly this SEC 10-K text MENTIONS trade war risks (tariffs, US-China trade tensions, retaliatory measures, trade barriers, trade sanctions).

0.0 = no mention at all
0.2 = vague "trade policy" mention
0.5 = mentions tariffs or trade uncertainty as a risk
0.8 = clear mention of trade war / US-China tensions
1.0 = detailed: specific tariff rates, products, financial impact

Score ONLY what is written. Short/boilerplate text = 0.0.
Reply with a single number between 0.0 and 1.0, nothing else.

Text: {text}

Score:"""


def build_prompt(text: str, max_chars: int = 2000) -> str:
    # Truncate very long texts to control token usage
    truncated = text[:max_chars] if len(text) > max_chars else text
    return PROMPT_TEMPLATE.format(text=truncated)


def parse_score(response_text: str) -> float | None:
    """Extract score from LLM response — handles plain number, JSON, and markdown."""
    text = response_text.strip()

    # Strip markdown code blocks
    text = re.sub(r"```[a-z]*\n?", "", text).strip()

    # Try plain float first (e.g. "0.8" or "0.0")
    try:
        score = float(text.split()[0])
        if 0.0 <= score <= 1.0:
            return round(score, 3)
    except (ValueError, IndexError):
        pass

    # Try JSON {"score": X.X}
    try:
        data = json.loads(text)
        score = float(data.get("score", -1))
        if 0.0 <= score <= 1.0:
            return round(score, 3)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Regex: first float in 0–1 range anywhere in text
    matches = re.findall(r'\b([0-1](?:\.\d+)?)\b', text)
    for m in matches:
        try:
            score = float(m)
            if 0.0 <= score <= 1.0:
                return round(score, 3)
        except ValueError:
            continue

    return None


async def score_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    idx: int,
    text: str,
) -> tuple[int, float]:
    prompt = build_prompt(text)
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.0,   # deterministic
            "top_p": 1.0,
            "num_predict": 20,    # only need {"score": X.X}
        },
    }

    async with semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.post(OLLAMA_URL, json=payload, timeout=TIMEOUT)
                resp.raise_for_status()
                raw = resp.json().get("response", "")
                score = parse_score(raw)
                if score is not None:
                    return idx, score
                # Unparseable response → retry
            except (httpx.TimeoutException, httpx.HTTPStatusError):
                if attempt == MAX_RETRIES - 1:
                    break
                await asyncio.sleep(1)

    return idx, -1.0   # sentinel: failed


async def score_all(
    texts: list[str],
    workers: int = DEFAULT_WORKERS,
    start_idx: int = 0,
) -> list[float]:
    semaphore = asyncio.Semaphore(workers)
    scores = [-1.0] * len(texts)

    async with httpx.AsyncClient() as client:
        tasks = [
            score_one(client, semaphore, i, text)
            for i, text in enumerate(texts)
        ]

        pbar = atqdm(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="Scoring",
            unit="doc",
            initial=start_idx,
        )

        completed = 0
        for coro in pbar:
            idx, score = await coro
            scores[idx] = score
            completed += 1
            pbar.set_postfix({"failed": sum(1 for s in scores if s < 0)})

    return scores


def load_checkpoint() -> set[int]:
    """Return set of already-scored row indices."""
    if CHECKPOINT_FILE.exists():
        cp = pd.read_parquet(CHECKPOINT_FILE)
        done = set(cp[cp["tw_score"] >= 0].index.tolist())
        print(f"Resuming: {len(done):,} docs already scored.")
        return done
    return set()


def save_checkpoint(df: pd.DataFrame) -> None:
    df.to_parquet(CHECKPOINT_FILE, index=True)


async def main_async(args):
    # Load data
    print(f"Loading {CLEANED_FILE} ...")
    df = pd.read_parquet(CLEANED_FILE)

    if args.limit:
        df = df.head(args.limit)
        print(f"Limited to {len(df):,} docs (--limit {args.limit})")
    else:
        print(f"Total docs to score: {len(df):,}")

    # Resume support
    df["tw_score"] = -1.0
    if args.resume and CHECKPOINT_FILE.exists():
        cp = pd.read_parquet(CHECKPOINT_FILE)
        scored_mask = cp["tw_score"] >= 0
        df.loc[scored_mask.index[scored_mask], "tw_score"] = cp.loc[scored_mask, "tw_score"]
        already_done = scored_mask.sum()
        print(f"Resuming from checkpoint: {already_done:,} already done.")
    else:
        already_done = 0

    # Identify docs needing scoring
    todo_mask = df["tw_score"] < 0
    todo_df = df[todo_mask]
    print(f"Docs to score this run: {len(todo_df):,}")

    if len(todo_df) == 0:
        print("All docs already scored.")
    else:
        # Score in batches with periodic checkpointing
        batch_size = CHECKPOINT_EVERY * args.workers
        todo_indices = todo_df.index.tolist()

        for batch_start in range(0, len(todo_indices), batch_size):
            batch_idx = todo_indices[batch_start: batch_start + batch_size]
            batch_texts = df.loc[batch_idx, "item_1a_clean"].tolist()

            print(f"\nBatch {batch_start // batch_size + 1} — "
                  f"docs {batch_start + 1}–{min(batch_start + len(batch_idx), len(todo_indices))} "
                  f"of {len(todo_indices)}")

            batch_scores = await score_all(batch_texts, workers=args.workers,
                                           start_idx=already_done + batch_start)

            df.loc[batch_idx, "tw_score"] = batch_scores
            save_checkpoint(df[["tw_score"]])

    # Report failures
    failed = (df["tw_score"] < 0).sum()
    if failed:
        print(f"\nWarning: {failed:,} docs failed to score — setting to -1")

    # Save final output
    out = df.drop(columns=["tw_score"]).copy()
    out["tw_score"] = df["tw_score"].clip(lower=0)   # -1 failures → 0
    out = out.sort_values("tw_score", ascending=False).reset_index(drop=True)
    out.to_parquet(PRED_FILE, index=False)
    size_mb = PRED_FILE.stat().st_size / 1024 / 1024
    print(f"\nSaved → {PRED_FILE}  ({size_mb:.1f} MB)")

    # Summary stats
    valid = out[out["tw_score"] > 0]
    print(f"\n=== Score distribution ===")
    print(out["tw_score"].describe().apply(lambda x: f"{x:.4f}"))
    print(f"\nDocs by score bucket:")
    bins = [0, 0.2, 0.4, 0.6, 0.8, 1.01]
    labels = ["0.0–0.2", "0.2–0.4", "0.4–0.6", "0.6–0.8", "0.8–1.0"]
    out["bucket"] = pd.cut(out["tw_score"], bins=bins, labels=labels, right=False)
    print(out["bucket"].value_counts().sort_index().to_string())

    print(f"\nTop 15 highest Trade War scores:")
    cols = ["year", "cik", "tw_score", "filename"]
    print(out[cols].head(15).to_string(index=False))

    # Cleanup checkpoint on success
    if not failed and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("\nCheckpoint file removed.")


def main():
    parser = argparse.ArgumentParser(description="Score 10-K docs for Trade War relevance.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Score only first N docs (for testing)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Concurrent Ollama requests (default: {DEFAULT_WORKERS})")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from checkpoint if interrupted")
    parser.add_argument("--model", type=str, default=MODEL,
                        help=f"Ollama model name (default: {MODEL})")
    args = parser.parse_args()

    # Verify Ollama is running
    try:
        import httpx as _h
        r = _h.get("http://localhost:11434", timeout=3)
    except Exception:
        print("ERROR: Ollama không chạy. Mở Ollama app trước.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
