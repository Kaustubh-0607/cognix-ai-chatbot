# Cognix Evaluation Proof Pack

This folder contains a reproducible intent-classification benchmark for the Cognix chatbot.

## Files
- benchmark_queries.json: Labeled test set used for metrics.
- evaluate.py: Reproducible evaluator for Rule-only, LLM-only, and Hybrid.
- latest_results.json: Most recent computed metrics snapshot.

## How to run
1. Ensure dependencies are installed from requirements.txt.
2. Ensure GEMINI_API_KEY is set in .env at project root.
3. Run:

c:/Users/ASUS/ChatBot/.venv/Scripts/python.exe/evaluation/evaluate.py

The script prints metrics and writes latest_results.json.

## Metric definitions
- Precision/Recall/F1: macro-averaged across intent classes.
- Factual Error (%): percent of queries where predicted intent != gold intent.

## Important note
These metrics are true for the exact benchmark set and runtime conditions used in this folder. They are not a universal guarantee for all future runs, all prompts, or changed configurations.
