import logging

import httpx

from .config import settings

log = logging.getLogger("safesound.llm")
PROVIDER = settings.resolved_llm_provider()

_anthropic_client = None
if PROVIDER == "anthropic":
    import anthropic

    _anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def complete(system: str, user: str, max_tokens: int = 300) -> str | None:
    try:
        if PROVIDER == "anthropic":
            msg = _anthropic_client.messages.create(
                model=settings.anthropic_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return msg.content[0].text.strip()

        if PROVIDER == "ollama":
            r = httpx.post(
                f"{settings.ollama_url}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=30,
            )
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
    except Exception as e:
        log.warning("LLM call failed (%s); falling back to rules.", e)
    return None
