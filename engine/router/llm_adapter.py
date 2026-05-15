#!/usr/bin/env python3
"""
NSOS LLM Adapter — Multi-Provider LLM Integration Layer
Version: 2.0

Routes LLM calls across multiple providers (NVIDIA NIM, OpenAI, Groq, Together AI,
OpenRouter, Ollama, Anthropic) with configurable model registry and automatic fallback chains.

Provides unified interface for multi-tier models optimized for NSOS workflows.
Supports OpenAI-compatible endpoints and Anthropic SDK.
"""

import os
import sys
import json
from typing import Optional, Dict, Any, List
from pathlib import Path
from openai import OpenAI

# Configuration
NSOS_DIR = Path(__file__).parent
CONFIG_FILE = NSOS_DIR / "models.json"
PROMPTS_DIR = NSOS_DIR / "prompts"
SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system_default.txt"

# Operator + company identity (parameterized — defaults to generic strings)
OPERATOR_NAME = os.environ.get("OPERATOR_NAME", "Operator")
COMPANY_NAME = os.environ.get("COMPANY_NAME", "the firm")


def _load_system_prompt() -> str:
    """Load system prompt template from prompts/system_default.txt and substitute identity tokens."""
    if SYSTEM_PROMPT_FILE.exists():
        try:
            template = SYSTEM_PROMPT_FILE.read_text()
            return template.replace("{OPERATOR_NAME}", OPERATOR_NAME).replace("{COMPANY_NAME}", COMPANY_NAME)
        except Exception as e:
            print(f"Warning: Failed to load system prompt {SYSTEM_PROMPT_FILE}: {e}", file=sys.stderr)
    # Minimal fallback if prompt file is missing
    return (
        f"You are Claude, senior technical consultant for {COMPANY_NAME} — "
        f"{OPERATOR_NAME}'s AI-augmented consulting practice.\n"
        "Execute fully, then report. Verify before claiming. Output-driven iteration."
    )


# NSOS system context — loaded from external prompt file with identity substitution
NSOS_SYSTEM = _load_system_prompt()


# Default configuration (used if models.json doesn't exist)
DEFAULT_CONFIG = {
    "providers": {
        "nim": {
            "base_url": "https://integrate.api.nvidia.com/v1",
            "api_key_env": "NIM_API_KEY",
            "type": "openai_compatible"
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "api_key_env": "OPENAI_API_KEY",
            "type": "openai_compatible"
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
            "type": "openai_compatible"
        },
        "together": {
            "base_url": "https://api.together.xyz/v1",
            "api_key_env": "TOGETHER_API_KEY",
            "type": "openai_compatible"
        },
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API_KEY",
            "type": "openai_compatible"
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "api_key_env": None,
            "type": "openai_compatible"
        },
        "anthropic": {
            "api_key_env": "ANTHROPIC_API_KEY",
            "type": "anthropic"
        }
    },
    "tiers": {
        "primary": {"provider": "nim", "model": "nvidia/deepseek-v3.2"},
        "reasoning": {"provider": "nim", "model": "nvidia/deepseek-r1"},
        "fast": {"provider": "nim", "model": "nvidia/kimi-k2.5"},
        "fallback": {"provider": "nim", "model": "nvidia/llama-3.3-70b-instruct"},
        "local": {"provider": "ollama", "model": "llama3.2:latest"}
    },
    "fallback_chain": ["primary", "fast", "fallback", "local"]
}


def _load_env_file(env_path: Path) -> Dict[str, str]:
    """Load environment variables from .env file."""
    env_vars = {}
    if env_path.exists():
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip().strip('"').strip("'")
        except Exception:
            pass
    return env_vars


def _load_config() -> Dict[str, Any]:
    """Load configuration from models.json or create default."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Failed to load {CONFIG_FILE}: {e}. Using defaults.", file=sys.stderr)

    # Create default config file
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not write default config to {CONFIG_FILE}: {e}", file=sys.stderr)

    return DEFAULT_CONFIG


def _get_api_key(env_var_name: Optional[str]) -> Optional[str]:
    """Retrieve API key from environment, .env files, or defaults."""
    if not env_var_name:
        return None

    # Try environment variable
    key = os.environ.get(env_var_name)
    if key:
        return key

    # Try NSOS_DIR/.env
    nsos_env = NSOS_DIR / ".env"
    env_vars = _load_env_file(nsos_env)
    if env_var_name in env_vars:
        return env_vars[env_var_name]

    # Try ~/.env
    home_env = Path.home() / ".env"
    env_vars = _load_env_file(home_env)
    if env_var_name in env_vars:
        return env_vars[env_var_name]

    return None


# Load config globally
CONFIG = _load_config()

# Module-level key exports so downstream modules can check availability with
# `from llm_adapter import NIM_API_KEY` and short-circuit on absence.
NIM_API_KEY = _get_api_key("NIM_API_KEY")
GROQ_API_KEY = _get_api_key("GROQ_API_KEY")
ANTHROPIC_API_KEY = _get_api_key("ANTHROPIC_API_KEY")
OPENAI_API_KEY = _get_api_key("OPENAI_API_KEY")


def list_available_providers() -> Dict[str, bool]:
    """
    Check which providers have valid API keys configured.

    Returns:
        Dict mapping provider name to availability (True/False)
    """
    available = {}
    for provider_name, provider_config in CONFIG.get("providers", {}).items():
        if provider_config.get("type") == "anthropic":
            # Check for anthropic library and API key
            try:
                import anthropic
                api_key = _get_api_key(provider_config.get("api_key_env"))
                available[provider_name] = bool(api_key)
            except ImportError:
                available[provider_name] = False
        else:
            # OpenAI-compatible providers
            api_key_env = provider_config.get("api_key_env")
            if api_key_env:
                api_key = _get_api_key(api_key_env)
                available[provider_name] = bool(api_key)
            else:
                # Ollama doesn't need API key
                available[provider_name] = True

    return available


def test_provider(provider: str) -> Dict[str, Any]:
    """
    Send a quick test message to verify provider connectivity.

    Args:
        provider: Provider name to test

    Returns:
        Dict with success status and details
    """
    providers_config = CONFIG.get("providers", {})
    if provider not in providers_config:
        return {"success": False, "error": f"Unknown provider: {provider}"}

    provider_config = providers_config[provider]
    provider_type = provider_config.get("type")

    try:
        if provider_type == "anthropic":
            try:
                import anthropic
            except ImportError:
                return {
                    "success": False,
                    "error": "anthropic package not installed. Run: pip install anthropic"
                }

            api_key = _get_api_key(provider_config.get("api_key_env"))
            if not api_key:
                return {
                    "success": False,
                    "error": f"API key not found. Set env var {provider_config.get('api_key_env')}"
                }

            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=50,
                messages=[{"role": "user", "content": "Say hello in one word."}]
            )
            return {
                "success": True,
                "provider": provider,
                "response": response.content[0].text
            }

        else:  # OpenAI-compatible
            api_key_env = provider_config.get("api_key_env")
            api_key = _get_api_key(api_key_env) if api_key_env else None

            if api_key_env and not api_key:
                return {
                    "success": False,
                    "error": f"API key not found. Set env var {api_key_env}"
                }

            base_url = provider_config.get("base_url")
            client = OpenAI(base_url=base_url, api_key=api_key or "dummy")

            # Pick a real model for this provider from tiers config
            test_model = None
            for tier_info in CONFIG.get("tiers", {}).values():
                if tier_info.get("provider") == provider:
                    test_model = tier_info.get("model")
                    break
            if not test_model:
                test_model = "gpt-3.5-turbo"  # last resort fallback

            response = client.chat.completions.create(
                model=test_model,
                messages=[{"role": "user", "content": "Say hello in one word."}],
                max_tokens=50,
                timeout=10.0
            )
            return {
                "success": True,
                "provider": provider,
                "response": response.choices[0].message.content
            }

    except Exception as e:
        return {
            "success": False,
            "provider": provider,
            "error": str(e)
        }


def _get_client_for_provider(provider: str) -> tuple:
    """
    Get a client (OpenAI or Anthropic) for the given provider.

    Returns:
        Tuple of (client, provider_type) where client is OpenAI or anthropic.Anthropic
    """
    providers_config = CONFIG.get("providers", {})
    if provider not in providers_config:
        raise ValueError(f"Unknown provider: {provider}")

    provider_config = providers_config[provider]
    provider_type = provider_config.get("type")

    if provider_type == "anthropic":
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        api_key = _get_api_key(provider_config.get("api_key_env"))
        if not api_key:
            raise ValueError(
                f"Anthropic API key not found. Set env var {provider_config.get('api_key_env')}"
            )
        return anthropic.Anthropic(api_key=api_key), "anthropic"

    else:  # OpenAI-compatible
        api_key_env = provider_config.get("api_key_env")
        api_key = _get_api_key(api_key_env) if api_key_env else None

        if api_key_env and not api_key:
            raise ValueError(
                f"API key not found. Set env var {api_key_env}"
            )

        base_url = provider_config.get("base_url")
        return OpenAI(base_url=base_url, api_key=api_key or "dummy"), "openai_compatible"


def _try_provider_tier(
    provider: str,
    model: str,
    messages: List[Dict[str, str]],
    system: str,
    temperature: float,
    max_tokens: int
) -> Optional[str]:
    """
    Try calling a specific provider with a specific model.

    Returns:
        Response text if successful, None if failed
    """
    try:
        client, client_type = _get_client_for_provider(provider)

        if client_type == "anthropic":
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                temperature=temperature
            )
            return response.content[0].text
        else:
            # OpenAI-compatible: system prompt goes as first message
            full_messages = [{"role": "system", "content": system}] + messages
            response = client.chat.completions.create(
                model=model,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=60.0
            )
            return response.choices[0].message.content
    except Exception as e:
        print(f"  [debug] {provider}/{model} failed: {e}", file=sys.stderr)
        return None


def call_llm(
    prompt: str = None,
    system: Optional[str] = None,
    tier: str = "primary",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    messages: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Route LLM call with automatic provider fallback chain.

    Args:
        prompt: User message (if messages not provided)
        system: System prompt (defaults to NSOS_SYSTEM)
        tier: Model tier: "primary" | "reasoning" | "fast" | "fallback" | "local"
        provider: Override provider for this call (e.g., "groq", "anthropic")
        model: Override specific model for this call
        temperature: Sampling temperature (0.0-1.0)
        max_tokens: Max output tokens
        messages: Pre-formatted message list (overrides prompt)

    Returns:
        Response text from LLM

    Raises:
        ValueError: If no valid provider/model can be found
        Exception: If all fallback attempts fail
    """
    system = system or NSOS_SYSTEM

    # Build message list
    if messages is None:
        if not prompt:
            raise ValueError("Either prompt or messages must be provided")
        messages = [{"role": "user", "content": prompt}]

    tiers = CONFIG.get("tiers", {})
    fallback_chain = CONFIG.get("fallback_chain", ["primary", "fallback"])

    # Determine which tiers to try
    if provider and model:
        # Explicit provider/model override
        tiers_to_try = [(provider, model)]
    elif provider:
        # Find tier(s) for this provider
        tiers_to_try = [
            (tier_name_key, tier_cfg.get("model"))
            for tier_name_key, tier_cfg in tiers.items()
            if tier_cfg.get("provider") == provider
        ]
        if not tiers_to_try:
            raise ValueError(f"No tiers configured for provider: {provider}")
    else:
        # Use configured tier + fallback chain
        if tier in tiers:
            tier_cfg = tiers[tier]
            tiers_to_try = [(tier_cfg.get("provider"), tier_cfg.get("model"))]

            # Add fallback chain
            for fallback_tier in fallback_chain:
                if fallback_tier != tier and fallback_tier in tiers:
                    fallback_cfg = tiers[fallback_tier]
                    tiers_to_try.append((fallback_cfg.get("provider"), fallback_cfg.get("model")))
        else:
            raise ValueError(f"Unknown tier: {tier}")

    # Try each provider/model combination
    last_error = None
    for prov, mdl in tiers_to_try:
        if not prov or not mdl:
            continue

        result = _try_provider_tier(prov, mdl, messages, system, temperature, max_tokens)
        if result is not None:
            return result
        last_error = f"Failed with {prov}/{mdl}"

    raise Exception(f"All LLM models failed. Last error: {last_error}")


def analyze_correction(correction_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    NSOS-specific: Analyze operator correction to extract pattern.

    Args:
        correction_data: {pattern_name, context, what_model_did, what_operator_wanted, ...}

    Returns:
        Pattern analysis with confidence, domain, category
    """
    prompt = f"""Analyze this correction from the operator and extract the underlying pattern.

Correction:
{json.dumps(correction_data, indent=2)}

Extract:
1. The root principle being violated
2. When this pattern applies (domain, task types)
3. Confidence (0-1) that this generalizes
4. Category (decision-making, output-format, process, execution-order)

Return JSON with keys: principle, domain, category, confidence, applies_to_tasks"""

    response = call_llm(prompt, tier="reasoning", max_tokens=500)
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {"error": "Failed to parse analysis", "raw": response}


def analyze_prediction_delta(
    prediction: str,
    actual_outcome: str,
    context: str
) -> Dict[str, Any]:
    """
    NSOS-specific: Compare prediction vs actual to measure model drift.

    Args:
        prediction: What model predicted would happen
        actual_outcome: What actually happened
        context: Situation that generated the prediction

    Returns:
        Delta analysis with confidence adjustment
    """
    prompt = f"""Analyze this prediction vs actual outcome.

Context: {context}
Prediction: {prediction}
Actual: {actual_outcome}

Assess:
1. Was prediction correct? (true/false)
2. Confidence delta: how confident was prediction vs how it should have been (-1.0 to +1.0)
3. Why the mismatch (if any): missing context, wrong assumption, model limitation
4. Correction needed: how should model reason differently next time

Return JSON with keys: correct, confidence_delta, mismatch_reason, correction"""

    response = call_llm(prompt, tier="reasoning", max_tokens=500)
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {"error": "Failed to parse delta analysis", "raw": response}


def score_gap_question(question: str, context: str) -> float:
    """
    NSOS-specific: Score how important a question is for closing a gap.

    Args:
        question: Question that could fill a gap
        context: Current context and gap description

    Returns:
        Score 0.0-1.0 (higher = more important)
    """
    prompt = f"""Score how important this question is for closing a knowledge gap.

Gap Context: {context}
Question: {question}

Scoring criteria:
- 0.0: Not relevant or won't help
- 0.3: Marginally relevant, nice-to-have
- 0.6: Relevant, would help
- 0.8: Critical, directly addresses gap
- 1.0: Essential, must answer before proceeding

Return ONLY a float between 0.0 and 1.0"""

    response = call_llm(prompt, tier="fast", max_tokens=10, temperature=0.0)
    try:
        return float(response.strip())
    except ValueError:
        return 0.5


def synthesize_learning_session(
    corrections: List[Dict[str, Any]],
    predictions: List[Dict[str, Any]],
    gaps: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    NSOS-specific: Synthesize learning from a full session.

    Args:
        corrections: List of corrections from the operator
        predictions: List of model predictions vs outcomes
        gaps: List of identified knowledge gaps

    Returns:
        Synthesis with promoted patterns, updated gaps, confidence changes
    """
    prompt = f"""Synthesize learning from this session.

Corrections Applied:
{json.dumps(corrections[:5], indent=2)}

Prediction Outcomes:
{json.dumps(predictions[:5], indent=2)}

Knowledge Gaps:
{json.dumps(gaps[:5], indent=2)}

Provide:
1. Patterns to promote (high confidence, high impact)
2. Patterns to demote (low confidence or wrong)
3. Gaps that closed vs gaps that opened
4. Overall confidence adjustment for model (0.0-1.0)
5. Top 3 learnings from this session

Return JSON with keys: patterns_to_promote, patterns_to_demote, gaps_closed, gaps_opened, confidence_delta, top_learnings"""

    response = call_llm(prompt, tier="reasoning", max_tokens=1000)
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {"error": "Failed to parse synthesis", "raw": response}


def classify_operator_message(message: str) -> Dict[str, Any]:
    """
    NSOS-specific: Classify the operator's message type for correction detection.

    Args:
        message: Operator's message text

    Returns:
        Classification with type, confidence, implied_correction (if any)
    """
    prompt = f"""Classify this message from the operator.

Message: {message}

Classify as one of:
- NEW_INSTRUCTION: Operator is giving a new task
- CONFIRMATION: Operator is confirming something (e.g., "yes", "go ahead")
- CORRECTION: Operator is correcting something the model did wrong
- FRUSTRATION: Operator is expressing frustration (all caps, terse, sarcasm)
- CLARIFICATION: Operator is clarifying or refining a previous instruction
- QUESTION: Operator is asking a question, not instructing

If CORRECTION or FRUSTRATION, also identify:
- What was wrong (the issue)
- What should have happened instead (the correction)
- Severity (low, medium, high)

Return JSON with keys: type, confidence, issue (if correction), correction (if correction), severity (if correction)"""

    response = call_llm(prompt, tier="fast", max_tokens=400, temperature=0.0)
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {"error": "Failed to parse classification", "raw": response}


# Legacy aliases for compatibility
def call_reasoning_tier(prompt: str) -> str:
    """Alias for reasoning tier calls."""
    return call_llm(prompt, tier="reasoning", max_tokens=2000)


def call_primary_tier(prompt: str) -> str:
    """Alias for primary tier calls."""
    return call_llm(prompt, tier="primary", max_tokens=2000)


def call_fast_tier(prompt: str) -> str:
    """Alias for fast tier calls."""
    return call_llm(prompt, tier="fast", max_tokens=1000, temperature=0.1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="NSOS LLM Adapter CLI")
    parser.add_argument("--providers", action="store_true", help="List available providers")
    parser.add_argument("--test", nargs="?", const="all", help="Test provider(s)")
    args = parser.parse_args()

    if args.providers:
        available = list_available_providers()
        print("Available Providers:")
        for provider, is_available in available.items():
            status = "Available" if is_available else "Not configured"
            print(f"  {provider}: {status}")
        sys.exit(0)

    if args.test:
        if args.test == "all":
            available = list_available_providers()
            for provider in available:
                result = test_provider(provider)
                status = "PASS" if result.get("success") else "FAIL"
                print(f"[{status}] {provider}")
                if result.get("success"):
                    print(f"      Response: {result.get('response', '')[:50]}")
                else:
                    print(f"      Error: {result.get('error', '')}")
        else:
            result = test_provider(args.test)
            print(f"Provider: {args.test}")
            print(f"Status: {'PASS' if result.get('success') else 'FAIL'}")
            if result.get("success"):
                print(f"Response: {result.get('response')}")
            else:
                print(f"Error: {result.get('error')}")
        sys.exit(0)

    # Default: quick test with primary tier
    try:
        response = call_llm(
            prompt="What is the NSOS framework?",
            tier="fast",
            max_tokens=500
        )
        print("LLM Response:")
        print(response)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
