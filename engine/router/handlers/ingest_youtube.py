"""
ingest-youtube — poll the 'Work (YT)' YouTube playlist, transcribe, extract.

    nsos ingest-youtube           # one polling pass
    nsos ingest-youtube status    # show pipeline state

Transcript extraction order (fastest → slowest):
  1. youtube-transcript-api — reads auto-generated or manual captions.
     Covers ~80% of videos, instant, no auth needed.
  2. yt-dlp + openai-whisper (base model, CPU) — for videos without
     captions. Slow (1-2h per 30-min video on CPU) but acceptable for
     background batch on Dell. These entries are flagged "slow-transcribe".

Long-form transcripts are chunked into ~3000-token segments before NIM
extraction, then a final consolidation pass merges per-chunk insights.
This prevents the same truncated-JSON class of bug that hit the
Instagram pipeline (fixed in commit 19c83b5).

Config via .env:
  YOUTUBE_API_KEY      - Google Cloud API key with YouTube Data API v3 enabled
  YOUTUBE_PLAYLIST_ID  - playlist ID for 'Work (YT)' (e.g. PLxxxxxxxxx)

API key vs OAuth: a plain API key works for reading PUBLIC or UNLISTED
playlists. Private playlists require OAuth2. If your 'Work (YT)' is
unlisted (recommended), an API key suffices — no browser consent flow.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

NSOS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NSOS_DIR))

KNOWLEDGE_DIR = NSOS_DIR / "knowledge" / "youtube"
TRANSCRIPTS_DIR = KNOWLEDGE_DIR / "transcripts"
INSIGHTS_DIR = KNOWLEDGE_DIR / "insights"
INDEX_PATH = KNOWLEDGE_DIR / "index.jsonl"
STATE_PATH = KNOWLEDGE_DIR / "pipeline-state.json"

AUDIO_CACHE_DIR = NSOS_DIR / "knowledge" / "youtube" / "raw_audio"

# NIM extraction chunk size (rough tokens; 1 token ~4 chars for English).
CHUNK_CHAR_SIZE = 12000  # ~3000 tokens
CHUNK_OVERLAP_CHARS = 400

EXTRACT_SYSTEM = """You are analyzing a chunk of a YouTube video transcript for business intelligence.

Return ONLY a JSON object, no markdown fences, no prose:

{
  "summary": "2-3 sentences capturing the core ideas in this chunk",
  "key_ideas": ["list of distinct actionable ideas or principles"],
  "tone": "motivational | tactical | educational | contrarian | storytelling | analytical",
  "quotable_lines": ["exact phrases worth remembering"],
  "tags": ["topic tags for searchability"]
}

This is one chunk of a longer video. Don't repeat content from other chunks — just summarize what's in THIS chunk."""

CONSOLIDATE_SYSTEM = """You are consolidating per-chunk insights from a YouTube video into a single structured summary.

Given multiple per-chunk JSON objects, produce ONE final JSON object:

{
  "summary": "2-3 sentence summary of the WHOLE video's core message",
  "key_ideas": ["deduplicated actionable ideas across all chunks"],
  "tone": "dominant tone across chunks",
  "conviction_level": "low | medium | high",
  "speaker_style": "one-sentence description",
  "business_relevance": {"sales": 0-10, "marketing": 0-10, "operations": 0-10, "product": 0-10, "mindset": 0-10},
  "quotable_lines": ["best phrases worth remembering"],
  "tags": ["merged topic tags"]
}

Return ONLY valid JSON, no markdown fences."""


# ── state helpers ──────────────────────────────────────────────────────────


def _load_env() -> Dict[str, str]:
    env = dict(os.environ)
    envfile = NSOS_DIR / ".env"
    if envfile.exists():
        for line in envfile.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env.setdefault(k.strip(), v.strip())
    return env


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"processed": [], "last_seen_video_id": None, "last_run": None, "stats": {}}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"processed": [], "last_seen_video_id": None, "last_run": None, "stats": {}}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))


def _append_index(rec: Dict[str, Any]) -> None:
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_PATH, "a") as f:
        f.write(json.dumps(rec, default=str) + "\n")


# ── playlist polling ────────────────────────────────────────────────────────


def _fetch_playlist_items(api_key: str, playlist_id: str) -> List[Dict[str, Any]]:
    """Return every video currently in the playlist (newest first).
    Uses the YouTube Data API v3 playlistItems.list endpoint."""
    try:
        import requests
    except ImportError:
        raise RuntimeError("requests not installed")

    base = "https://www.googleapis.com/youtube/v3/playlistItems"
    items = []
    page_token = ""
    while True:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(base, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        for it in data.get("items", []):
            vid = it.get("contentDetails", {}).get("videoId")
            snip = it.get("snippet", {})
            if not vid:
                continue
            items.append({
                "video_id": vid,
                "title": snip.get("title", ""),
                "channel": snip.get("videoOwnerChannelTitle") or snip.get("channelTitle", ""),
                "description": snip.get("description", ""),
                "published_at": snip.get("publishedAt", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break
    return items


# ── transcript extraction ──────────────────────────────────────────────────


def _fetch_captions(video_id: str) -> Optional[str]:
    """Try youtube-transcript-api first (fast path). Returns plain text or None.

    Supports both the v0.x classmethod API (get_transcript) and the v1.x
    instance API (ytt.fetch(...)) so we don't break on upgrades.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None

    # v1.x: instance.fetch(video_id) → FetchedTranscript (iterable of snippets)
    if hasattr(YouTubeTranscriptApi, "fetch") and callable(getattr(YouTubeTranscriptApi, "fetch", None)):
        try:
            ytt = YouTubeTranscriptApi()
            fetched = ytt.fetch(video_id)
        except Exception:
            fetched = None
        if fetched is not None:
            lines = []
            try:
                for seg in fetched:
                    t = getattr(seg, "text", None)
                    if t is None and isinstance(seg, dict):
                        t = seg.get("text")
                    if t:
                        lines.append(str(t).strip())
            except Exception:
                pass
            if lines:
                return "\n".join(lines)

    # v0.x legacy: classmethod get_transcript
    legacy = getattr(YouTubeTranscriptApi, "get_transcript", None)
    if callable(legacy):
        try:
            segments = legacy(video_id)
        except Exception:
            return None
        return "\n".join(s.get("text", "").strip() for s in segments if s.get("text"))

    return None


def _whisper_transcribe(video_id: str, url: str) -> Optional[Tuple[str, str]]:
    """Download audio with yt-dlp, transcribe with Whisper base on CPU.
    Returns (text, status) where status is 'slow-transcribe' or 'whisper-failed'."""
    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    mp3_path = AUDIO_CACHE_DIR / f"{video_id}.mp3"
    try:
        subprocess.run(
            ["yt-dlp", "--extract-audio", "--audio-format", "mp3",
             "-o", str(AUDIO_CACHE_DIR / f"{video_id}.%(ext)s"),
             url],
            check=True, capture_output=True, timeout=600,
        )
    except Exception as e:
        return (f"(yt-dlp failed: {e})", "whisper-failed")
    if not mp3_path.exists():
        return (f"(no mp3 produced)", "whisper-failed")

    try:
        import whisper
    except ImportError:
        return ("(whisper not installed)", "whisper-failed")
    try:
        model = whisper.load_model("base")
        result = model.transcribe(str(mp3_path), fp16=False)
        return (result.get("text", "").strip(), "slow-transcribe")
    except Exception as e:
        return (f"(whisper transcribe failed: {e})", "whisper-failed")


def _get_transcript(video: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """Returns (transcript_text, source) where source ∈ {'captions','slow-transcribe','unavailable'}."""
    vid = video["video_id"]
    cached = TRANSCRIPTS_DIR / f"{vid}.txt"
    if cached.exists():
        return cached.read_text(), "cached"
    text = _fetch_captions(vid)
    if text:
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_text(text)
        return text, "captions"
    # Fallback to Whisper
    wr = _whisper_transcribe(vid, video["url"])
    if wr is None or not wr[0] or wr[1] == "whisper-failed":
        return None, "unavailable"
    text, status = wr
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(text)
    return text, status


# ── chunking + NIM extraction ───────────────────────────────────────────────


def _chunk(text: str, size: int = CHUNK_CHAR_SIZE, overlap: int = CHUNK_OVERLAP_CHARS) -> List[str]:
    """Chunk transcript into overlapping ~3000-token segments."""
    if len(text) <= size:
        return [text]
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i + size])
        i += size - overlap
    return chunks


def _parse_llm_json(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    t = raw.strip()
    t = re.sub(r"^```json?\s*|\s*```$", "", t, flags=re.MULTILINE).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", t)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def _extract_chunk(chunk_text: str, call_llm) -> Optional[Dict[str, Any]]:
    try:
        raw = call_llm(
            prompt=chunk_text,
            system=EXTRACT_SYSTEM,
            tier="primary",
            temperature=0.3,
            max_tokens=2500,
        )
    except Exception:
        return None
    return _parse_llm_json(raw)


def _consolidate_chunks(per_chunk: List[Dict[str, Any]], call_llm) -> Optional[Dict[str, Any]]:
    if not per_chunk:
        return None
    if len(per_chunk) == 1:
        return per_chunk[0]
    payload = json.dumps(per_chunk, default=str)[:12000]
    try:
        raw = call_llm(
            prompt=payload,
            system=CONSOLIDATE_SYSTEM,
            tier="primary",
            temperature=0.2,
            max_tokens=2000,
        )
    except Exception:
        return None
    return _parse_llm_json(raw)


# ── end-to-end video processing ────────────────────────────────────────────


def _process_video(video: Dict[str, Any], call_llm) -> Dict[str, Any]:
    vid = video["video_id"]
    transcript, source = _get_transcript(video)
    if not transcript:
        return {**video, "transcript_source": source, "insights": None}

    chunks = _chunk(transcript)
    per_chunk = []
    for ch in chunks:
        result = _extract_chunk(ch, call_llm)
        if result:
            per_chunk.append(result)
    consolidated = _consolidate_chunks(per_chunk, call_llm)

    if consolidated:
        INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
        (INSIGHTS_DIR / f"{vid}.json").write_text(json.dumps(consolidated, indent=2, default=str))

    return {
        **video,
        "transcript_chars": len(transcript),
        "transcript_source": source,
        "chunks": len(chunks),
        "chunks_extracted": len(per_chunk),
        "insights": consolidated,
    }


# ── public API + handler ───────────────────────────────────────────────────


def run_ingest(limit: int = 5) -> Dict[str, Any]:
    """Poll playlist, process new videos up to `limit` per invocation."""
    env = _load_env()
    api_key = env.get("YOUTUBE_API_KEY")
    playlist_id = env.get("YOUTUBE_PLAYLIST_ID")
    if not api_key:
        return {"error": "YOUTUBE_API_KEY not set in .env"}
    if not playlist_id:
        return {"error": "YOUTUBE_PLAYLIST_ID not set in .env"}

    try:
        from llm_adapter import call_llm
    except Exception as e:
        return {"error": f"llm_adapter import failed: {e}"}

    try:
        items = _fetch_playlist_items(api_key, playlist_id)
    except Exception as e:
        return {"error": f"playlist fetch failed: {e}"}

    state = _load_state()
    processed = set(state.get("processed", []))
    new_items = [it for it in items if it["video_id"] not in processed][:limit]

    # First run: don't replay the entire playlist — just snapshot current state.
    if state.get("last_run") is None and items:
        for it in items:
            processed.add(it["video_id"])
        state["processed"] = list(processed)
        state["last_seen_video_id"] = items[0]["video_id"] if items else None
        _save_state(state)
        return {
            "initialized": True,
            "snapshot_size": len(items),
            "note": "first-run snapshot; future polls will process only new additions",
        }

    outcomes = []
    for video in new_items:
        result = _process_video(video, call_llm)
        outcomes.append(result)
        rec = {
            "video_id": result["video_id"],
            "title": result.get("title"),
            "channel": result.get("channel"),
            "url": result.get("url"),
            "transcript_source": result.get("transcript_source"),
            "transcript_chars": result.get("transcript_chars", 0),
            "has_insights": result.get("insights") is not None,
            "summary": (result.get("insights") or {}).get("summary", ""),
            "tags": (result.get("insights") or {}).get("tags", []),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        _append_index(rec)
        processed.add(result["video_id"])
        state["processed"] = list(processed)
        _save_state(state)

    return {
        "polled": len(items),
        "new_processed": len(outcomes),
        "outcomes": [
            {
                "video_id": o["video_id"],
                "title": o.get("title", "")[:80],
                "source": o.get("transcript_source"),
                "chunks": o.get("chunks"),
                "has_insights": o.get("insights") is not None,
            }
            for o in outcomes
        ],
    }


def _status() -> Dict[str, Any]:
    state = _load_state()
    try:
        index_count = sum(1 for _ in open(INDEX_PATH)) if INDEX_PATH.exists() else 0
    except Exception:
        index_count = 0
    return {
        "processed_count": len(state.get("processed", [])),
        "indexed_count": index_count,
        "last_run": state.get("last_run"),
        "last_seen_video_id": state.get("last_seen_video_id"),
    }


def handle(envelope: Dict[str, Any]) -> str:
    parts = (envelope.get("text") or "").split(None, 1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""
    if arg == "status":
        return json.dumps(_status(), indent=2, default=str)
    result = run_ingest(limit=5)
    return json.dumps(result, indent=2, default=str)[:MAX_RESPONSE_CHARS]


MAX_RESPONSE_CHARS = 4000
