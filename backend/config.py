import json
import os


def load_config(config_path: str = None) -> dict:
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "api_config.json")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    model_cfg = raw.get("model", {}).get("qa_agent", {})
    return {
        "model_name": model_cfg.get("model_name", ""),
        "api_key": model_cfg.get("api_key", ""),
        "base_url": model_cfg.get("base_url", ""),
    }
