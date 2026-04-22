import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from thefuzz import fuzz, process

BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = BASE_DIR / "intents.json"
BENCHMARK_PATH = Path(__file__).resolve().parent / "benchmark_queries.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "latest_results.json"


cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
settings = cfg["settings"]
INTENTS = cfg["intents"]
FUZZY_THRESHOLD = settings.get("fuzzy_threshold", 60)
MIN_TOKEN_LEN = settings.get("min_token_length", 3)

AI_ROUTE_PATTERNS = [
    r"\bcompare\b",
    r"\bvs\.?\b",
    r"\bversus\b",
    r"\bdifference\s+between\b",
    r"\bwhich\s+is\s+better\b",
    r"\bwhich\s+one\b",
    r"\bwhich\s+should\b",
    r"\brecommend\b",
    r"\bsuggest\b",
    r"\bbest\s+for\b",
    r"\bshould\s+i\b",
    r"\bpros\s+and\s+cons\b",
    r"\badvise\b",
    r"\bguidance\b",
    r"\bpath\b",
    r"\bcareer\b",
    r"\bbeginner\b",
    r"\bno\s+experience\b",
    r"\bwhat\s+should\b",
    r"\bhelp\s+me\s+choose\b",
    r"\bjoke\b",
    r"\bfunny\b",
    r"\btell\s+me\b",
    r"\bwhat\s+is\b",
    r"\bhow\s+does\b",
    r"\bwhy\s+is\b",
    r"\bexplain\b",
    r"\bwhat\s+are\b",
    r"\bfun\s+fact\b",
    r"\bwho\s+are\s+you\b",
    r"\bwhat\s+can\s+you\s+do\b",
    r"\bthanks?\b",
    r"\bthank\s+you\b",
]


def is_complex_query(msg: str) -> bool:
    lower = msg.lower()
    return any(re.search(p, lower) for p in AI_ROUTE_PATTERNS)


def match_intent(user_msg: str):
    msg = user_msg.lower().strip()

    best_intent = None
    best_score = 0

    for intent_key, intent_data in INTENTS.items():
        keywords = intent_data["keywords"]

        for kw in keywords:
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, msg):
                score = 100 + len(kw)
                if score > best_score:
                    best_score = score
                    best_intent = intent_key

        msg_tokens = {t for t in msg.split() if len(t) >= MIN_TOKEN_LEN}
        for kw in keywords:
            kw_tokens = {t for t in kw.split() if len(t) >= MIN_TOKEN_LEN}
            if not kw_tokens:
                continue
            overlap = msg_tokens & kw_tokens
            if overlap:
                score = int((len(overlap) / len(kw_tokens)) * 90)
                if score > best_score:
                    best_score = score
                    best_intent = intent_key

        _best_kw, fuzzy_score = process.extractOne(msg, keywords, scorer=fuzz.token_sort_ratio)
        if fuzzy_score > best_score and fuzzy_score >= FUZZY_THRESHOLD:
            best_score = fuzzy_score
            best_intent = intent_key

    if len(msg) <= 3 and best_score < 100:
        for intent_key, intent_data in INTENTS.items():
            if msg in intent_data["keywords"]:
                return intent_key
        return None

    return best_intent


def macro_metrics(y_true, y_pred, labels):
    eps = 1e-12
    precisions = []
    recalls = []
    f1s = []

    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)

        prec = tp / (tp + fp + eps)
        rec = tp / (tp + fn + eps)
        f1 = 2 * prec * rec / (prec + rec + eps)

        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)

    factual_err = 100.0 * sum(1 for t, p in zip(y_true, y_pred) if t != p) / len(y_true)

    return {
        "precision": round(sum(precisions) / len(labels) * 100, 2),
        "recall": round(sum(recalls) / len(labels) * 100, 2),
        "f1": round(sum(f1s) / len(labels) * 100, 2),
        "factual_err": round(factual_err, 2),
    }


def llm_classify_all(queries, labels):
    load_dotenv(BASE_DIR / ".env")
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in .env")

    client = genai.Client(api_key=api_key)
    model = cfg.get("ai_settings", {}).get("model_name", "gemini-2.5-flash")

    intent_desc = "\n".join(
        [f"- {k}: {', '.join(INTENTS[k]['keywords'][:5])}" for k in labels]
    )
    qblock = "\n".join([f"{i + 1}. {q}" for i, q in enumerate(queries)])

    prompt = f"""
Classify each query into exactly one intent key from this list.
Return STRICT JSON only in this format:
{{"predictions": [{{"id": 1, "intent": "..."}}, ...]}}

Valid intents:
{intent_desc}

Queries:
{qblock}
"""

    resp = client.models.generate_content(
        model=model,
        config=types.GenerateContentConfig(temperature=0),
        contents=prompt,
    )
    text = (resp.text or "").strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise RuntimeError("LLM did not return parseable JSON")

    obj = json.loads(m.group(0))
    pred_map = {
        int(x["id"]): x["intent"]
        for x in obj.get("predictions", [])
        if "id" in x and "intent" in x
    }
    return [pred_map.get(i + 1, None) for i in range(len(queries))]


def run():
    dataset = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))

    queries = [d["query"] for d in dataset]
    gold = [d["label"] for d in dataset]
    labels = sorted(set(gold))

    llm_pred = llm_classify_all(queries, labels)
    rule_pred = [match_intent(q) or '__fallback__' for q in queries]

    hybrid_pred = []
    for i, q in enumerate(queries):
        if is_complex_query(q):
            hybrid_pred.append(llm_pred[i])
            continue
        p = rule_pred[i]
        hybrid_pred.append(p if p is not None else llm_pred[i])

    results = {
        "n_samples": len(dataset),
        "n_labels": len(labels),
        "rule_only": macro_metrics(gold, rule_pred, labels),
        "llm_only": macro_metrics(gold, llm_pred, labels),
        "hybrid": macro_metrics(gold, hybrid_pred, labels),
    }

    OUTPUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    run()
