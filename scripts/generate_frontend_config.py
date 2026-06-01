#!/usr/bin/env python3
"""Generate frontend/config.js from environment variables.

Reads the same env vars documented in config/omnifeed.env.example.
Used locally and in GitHub Actions deploy-frontend workflow.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "frontend" / "config.js"


def _load_env_files() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for path in (ROOT / "config" / "omnifeed.env", ROOT / ".env"):
        if path.exists():
            load_dotenv(path)


def build_config() -> dict[str, str]:
    return {
        "apiBase": os.getenv("OMNIFEED_API_BASE") or "/api",
        "feedsBase": os.getenv("OMNIFEED_FEEDS_BASE") or "",
        "turnstileSiteKey": os.getenv("TURNSTILE_SITE_KEY") or "",
    }


def render_config_js(config: dict[str, str]) -> str:
    payload = json.dumps(config, ensure_ascii=False, indent=4)
    return f"""/**
 * OmniFeed frontend runtime config (auto-generated — do not edit manually)
 * Source: config/omnifeed.env.example
 * Regenerate: python scripts/generate_frontend_config.py
 */
window.OMNIFEED_CONFIG = {payload};
"""


def main() -> int:
    _load_env_files()
    config = build_config()
    OUTPUT.write_text(render_config_js(config), encoding="utf-8")
    print(f"Generated {OUTPUT.relative_to(ROOT)}")
    print(f"  apiBase: {config['apiBase'] or '(empty)'}")
    print(f"  feedsBase: {config['feedsBase'] or '(empty)'}")
    print(f"  turnstileSiteKey: {'set' if config['turnstileSiteKey'] else 'not set'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
