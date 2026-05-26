"""Framework configuration: loads YAML file then applies env-var overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from automation.core.exceptions import ConfigError

_DEFAULTS: dict[str, Any] = {
    "or_path": "or/epic_or.yaml",
    "assets_dir": "assets/images",
    "screenshots_dir": "assets/screenshots",
    "log_level": "INFO",
    "citrix_window_title": "Citrix Viewer",
    "default_confidence": 0.85,
    "default_timeout": 30.0,
    "default_poll_interval": 0.5,
    "ocr_lang": "eng",
    "ocr_min_confidence": 0.65,
    "max_retry_attempts": 3,
    "retry_backoff": 1.5,
    "screen_stable_frames": 3,
    "screen_stable_interval": 0.5,
}

# Env-var prefix: AUTOMATION_<KEY_UPPER>  e.g. AUTOMATION_LOG_LEVEL=DEBUG
_ENV_PREFIX = "AUTOMATION_"


class Config:
    """Flat key-value store for framework settings."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get(self, key: str, default: Any = None) -> Any:
        """Return config value; fall back to *default* when key is absent."""
        return self._data.get(key, default)

    def require(self, key: str) -> Any:
        """Return config value or raise ConfigError when key is absent."""
        if key not in self._data:
            raise ConfigError(f"Required config key {key!r} is missing", logical_name=key)
        return self._data[key]

    def __getitem__(self, key: str) -> Any:
        """Dict-style access."""
        return self.require(key)

    def __repr__(self) -> str:
        return f"Config({list(self._data.keys())})"


def _apply_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Overlay matching AUTOMATION_* environment variables onto *data*."""
    for env_key, env_val in os.environ.items():
        if not env_key.startswith(_ENV_PREFIX):
            continue
        config_key = env_key[len(_ENV_PREFIX):].lower()
        # Best-effort type coercion: preserve the original type when possible.
        original = data.get(config_key)
        if isinstance(original, bool):
            data[config_key] = env_val.lower() in ("1", "true", "yes")
        elif isinstance(original, float):
            try:
                data[config_key] = float(env_val)
            except ValueError:
                data[config_key] = env_val
        elif isinstance(original, int):
            try:
                data[config_key] = int(env_val)
            except ValueError:
                data[config_key] = env_val
        else:
            data[config_key] = env_val
    return data


def load_config(path: Path | str | None = None) -> Config:
    """Load YAML config from *path*, apply env overrides, and return Config."""
    data: dict[str, Any] = dict(_DEFAULTS)

    if path is not None:
        config_path = Path(path)
        if not config_path.exists():
            raise ConfigError(
                f"Config file not found: {config_path}",
                logical_name=str(config_path),
            )
        try:
            with config_path.open() as fh:
                file_data = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(
                f"YAML parse error in {config_path}: {exc}",
                logical_name=str(config_path),
            ) from exc
        data.update(file_data)

    data = _apply_env_overrides(data)
    return Config(data)


# Module-level singleton; replaced by load_config() at test / runtime startup.
_config: Config | None = None


def get_config() -> Config:
    """Return the active Config singleton; auto-initialise with defaults."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(cfg: Config) -> None:
    """Replace the active Config singleton (used by conftest.py)."""
    global _config
    _config = cfg
