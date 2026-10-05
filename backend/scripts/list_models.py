"""List Gemini models that support generateContent for the configured API key."""

from __future__ import annotations

from app.config import get_settings
from app.llm.gemini import _get_client


def main() -> None:
    settings = get_settings()
    client = _get_client()
    print(f"Models supporting generateContent (key configured, env={settings.APP_ENV}):\n")
    for model in client.models.list():
        actions = model.supported_actions or []
        if "generateContent" not in actions:
            continue
        name = model.name or "(unnamed)"
        print(name)


if __name__ == "__main__":
    main()
