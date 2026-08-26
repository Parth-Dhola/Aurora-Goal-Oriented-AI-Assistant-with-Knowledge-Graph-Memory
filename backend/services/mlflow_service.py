"""
mlflow_service.py — Centralised MLflow experiment tracking.

Tracks per-run:
  params  : model, prompt_version, strategy, prompt_hash
  metrics : latency_ms, input_tokens, output_tokens,
            kg_nodes_used, context_relevant
"""

import os
import hashlib

try:
    import mlflow
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "mlruns"))
    mlflow.set_experiment("aurora-crag-agent")
    MLFLOW_ENABLED = True
except Exception:
    MLFLOW_ENABLED = False

# Bump this string when you change the prompt structure — enables A/B comparison
PROMPT_VERSION = "crag-kg-v1"


def log_agent_run(
    query: str,
    answer: str,
    strategy: str,
    latency_ms: float,
    kg_nodes_used: int,
    context_relevant: bool,
    model: str = "gemini-3.1-flash-lite",
) -> None:
    """
    Log a single CRAG agent run to MLflow.

    strategy values:
      'direct'       — no KG data yet, answered from base prompt
      'graph_hit'    — KG context was relevant and grounded the answer
      'web_fallback' — KG context was insufficient, web search used
    """
    if not MLFLOW_ENABLED:
        return

    prompt_hash   = hashlib.md5(query.encode()).hexdigest()[:8]
    input_tokens  = len(query.split())
    output_tokens = len(answer.split())

    try:
        with mlflow.start_run(run_name=f"{strategy}-{prompt_hash}"):
            mlflow.log_params({
                "model":          model,
                "prompt_version": PROMPT_VERSION,
                "strategy":       strategy,
                "prompt_hash":    prompt_hash,
            })
            mlflow.log_metrics({
                "latency_ms":       latency_ms,
                "input_tokens":     input_tokens,
                "output_tokens":    output_tokens,
                "kg_nodes_used":    float(kg_nodes_used),
                "context_relevant": 1.0 if context_relevant else 0.0,
            })
    except Exception as e:
        print(f"[MLflow] non-critical error: {e}")

