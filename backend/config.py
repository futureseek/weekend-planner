import json
import os


MODEL_DEFAULTS = {
    "model_name": "",
    "api_key": "",
    "base_url": "",
    "temperature": 0.2,
    "timeout": 45,
    "max_retries": 1,
    "reasoning_effort": "low",
    "extra_body": {},
}


def _model_config(raw_cfg: dict | None, fallback: dict | None = None) -> dict:
    base = {**MODEL_DEFAULTS, **(fallback or {})}
    if raw_cfg:
        base.update({key: value for key, value in raw_cfg.items() if value is not None})
    return base


def load_config(config_path: str = None) -> dict:
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "api_config.json")

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    model_root = raw.get("model", {}) or {}
    qa_cfg = _model_config(model_root.get("qa_agent", {}))
    fast_cfg = _model_config(model_root.get("fast_agent"), qa_cfg)
    parser_cfg = _model_config(model_root.get("parser_agent"), fast_cfg)
    chat_cfg = _model_config(model_root.get("chat_agent"), fast_cfg)
    explain_cfg = _model_config(model_root.get("explain_agent"), qa_cfg)
    guide_cfg = _model_config(model_root.get("guide_agent"), fast_cfg)

    return {
        **qa_cfg,
        "agents": {
            "qa": qa_cfg,
            "fast": fast_cfg,
            "parser": parser_cfg,
            "chat": chat_cfg,
            "explain": explain_cfg,
            "guide": guide_cfg,
        },
    }
