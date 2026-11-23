"""Ask Claude whether a clip is a moment from the target game worth posting as a Short / Reel."""
from __future__ import annotations

import base64
import json
import logging

import anthropic
import cv2

log = logging.getLogger("clipper.review")

SCHEMA = {
    "type": "object",
    "properties": {
        "is_target_game": {"type": "boolean", "description": "The frames show gameplay of the target game."},
        "game_seen": {"type": "string", "description": "What the frames actually show (game name, or e.g. 'just chatting')."},
        "summary": {"type": "string", "description": "One or two sentences: what happens in the clip."},
        "score": {"type": "integer", "description": "0-100: how likely this is to perform as a Short / Reel."},
        "upload": {"type": "boolean", "description": "True only if this is worth posting as it is."},
        "reason": {"type": "string", "description": "Why it should or should not be posted."},
        "title": {"type": "string", "description": "Short hook title, under 60 characters."},
        "caption": {"type": "string", "description": "One-line caption for the post."},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["is_target_game", "game_seen", "summary", "score", "upload", "reason",
                 "title", "caption", "hashtags"],
    "additionalProperties": False,
}

SYSTEM = """You review short clips cut automatically from live streams for a channel that posts \
only {game} content as YouTube Shorts and Instagram Reels.

About the target game: {game_notes}

Each clip was cut because the live chat suddenly got busier. That is a weak signal: chat also \
spikes for giveaways, spam, polls, donations and greetings. Your job is to decide whether the \
moment itself is worth posting.

You get a few frames from the clip, the speech transcript with timestamps (it may be Hindi, \
Hinglish or English, and speech recognition makes mistakes), and a sample of chat from the spike.

First decide whether the frames show {game}. Use everything available: the look of the world, \
the HUD and map, on-screen text, and what the streamer and chat say. Be strict: an older game in \
the same series, a different game, or the streamer just talking does not count.

A clip is worth posting when a viewer who has never seen the stream would understand and enjoy \
it within the clip's length: a funny exchange, a fail, a chase or crash, a clutch or shocking \
moment, a strong reaction from the streamer. It is not worth posting when nothing happens on \
screen, when it only makes sense with earlier context, when it starts or ends in the middle of \
the important part, or when the game is not {game}.

Score honestly; most automatically cut clips are mediocre and should score below 50. Write the \
title, caption and hashtags in the language and style the stream's own audience uses."""


def _frames_as_images(frames: list) -> list[dict]:
    blocks = []
    for frame in frames:
        h, w = frame.shape[:2]
        small = cv2.resize(frame, (960, int(h * 960 / w)))
        ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            blocks.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": base64.standard_b64encode(buf.tobytes()).decode()}})
    return blocks


def review_clip(frames: list, transcript: dict | None, meta: dict, game: str, game_notes: str,
                model: str = "claude-opus-5-5") -> dict:
    """Return the review as a dict, or {"error": "..."} when no review could be made."""
    lines = []
    if transcript and transcript.get("segments"):
        lines.append(f"Transcript (detected language: {transcript.get('language')}):")
        lines += [f"[{s['start']:.0f}s-{s['end']:.0f}s] {s['text']}" for s in transcript["segments"]]
    else:
        lines.append("Transcript: no speech was detected.")
    lines.append("")
    lines.append(f"Chat spike: {meta.get('messages_in_window')} messages in 10 seconds, "
                 f"{meta.get('score')} times the normal rate.")
    if meta.get("sample_messages"):
        lines.append("Chat around the spike:")
        lines += [f"- {m}" for m in meta["sample_messages"]]
    content = _frames_as_images(frames) + [{"type": "text", "text": "\n".join(lines)}]

    try:
        client = anthropic.Anthropic()
        # If the request is declined by a safety classifier, the server re-runs it on a fallback model.
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SYSTEM.format(game=game, game_notes=game_notes),
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
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
        return {"error": "the model declined to review this clip"}
    if response.stop_reason == "max_tokens":
        return {"error": "the review was cut off before it finished"}
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        return {"error": "the review came back empty"}
    result = json.loads(text)
    result["model"] = response.model
    return result
