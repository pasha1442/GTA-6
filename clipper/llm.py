"""One structured-output call to Claude, shared by the tools that need it."""
from __future__ import annotations

import json
import os


def has_api_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def ask_json(system: str, content: list[dict] | str, schema: dict, model: str = "claude-opus-5-5",
             effort: str = "medium", max_tokens: int = 32000) -> dict:
    """Return Claude's answer parsed as JSON (it follows `schema`), or {"error": "..."}."""
    import anthropic

    try:
        client = anthropic.Anthropic()
        # If the request is declined by a safety classifier, the server re-runs it on a fallback model.
        response = client.beta.messages.create(
            model=model,
            max_tokens=max_tokens,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system,
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.AuthenticationError:
        return {"error": "the Anthropic API key was rejected"}
    except anthropic.RateLimitError:
        return {"error": "rate limited by the Anthropic API"}
    except anthropic.APIStatusError as e:
        return {"error": f"Anthropic API error {e.status_code}: {e.message}"}
    except anthropic.APIConnectionError:
        return {"error": "could not reach the Anthropic API"}
    except anthropic.AnthropicError as e:  # e.g. no credentials configured
        return {"error": str(e).splitlines()[0][:200]}

    if response.stop_reason == "refusal":
        return {"error": "the model declined the request"}
    if response.stop_reason == "max_tokens":
        return {"error": "the answer was cut off before it finished"}
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        return {"error": "the answer came back empty"}
    return json.loads(text)
