#!/usr/bin/env python3
"""
NSOS Prompt Evolution Engine

Manages prompt variants, A/B tests them against eval harness, and promotes winners.
Zero API cost (NVIDIA NIM) — every system prompt evolves through data.

Version: 1.0.0
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List, Any
import re
import hashlib

# Add NSOS to path for llm_adapter imports
NSOS_DIR = Path(__file__).parent
sys.path.insert(0, str(NSOS_DIR))

try:
    from llm_adapter import call_llm
except ImportError:
    # Fallback for testing/development
    def call_llm(*args, **kwargs):
        raise ImportError("llm_adapter not found. Ensure it exists in NSOS_DIR.")


@dataclass
class PromptVariant:
    """Represents a single prompt variant experiment."""
    variant_id: str
    module_name: str
    prompt_name: str
    text: str
    strategy: str
    created_at: str
    test_results: Optional[Dict[str, Any]] = None
    promoted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PromptRegistry:
    """Tracks all registered system prompts."""
    module_name: str
    prompt_name: str
    current_text: str
    purpose: str
    registered_at: str
    last_tested: Optional[str] = None
    best_variant_id: Optional[str] = None
    test_count: int = 0
    avg_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PromptEvolver:
    """Manages prompt optimization lifecycle."""

    def __init__(self):
        self.prompts_dir = NSOS_DIR / "prompts"
        self.prompts_dir.mkdir(exist_ok=True)
        self.registry_path = self.prompts_dir / "registry.json"
        self.experiments_path = self.prompts_dir / "experiments.jsonl"

    # ── CORE OPERATIONS ──

    def register_prompt(
        self,
        module_name: str,
        prompt_name: str,
        current_text: str,
        purpose: str,
    ) -> bool:
        """Register a prompt for evolution tracking."""
        registry = self._load_registry()
        key = f"{module_name}:{prompt_name}"

        if key in registry:
            print(f"[INFO] Prompt already registered: {key}")
            return False

        entry = PromptRegistry(
            module_name=module_name,
            prompt_name=prompt_name,
            current_text=current_text,
            purpose=purpose,
            registered_at=datetime.now().isoformat(),
        )

        registry[key] = entry.to_dict()
        self._save_registry(registry)
        print(f"[REGISTERED] {key}: {purpose[:50]}...")
        return True

    def generate_variant(
        self,
        module_name: str,
        prompt_name: str,
        strategy: str = "refine",
    ) -> Optional[PromptVariant]:
        """Generate an improved variant using LLM."""
        key = f"{module_name}:{prompt_name}"
        registry = self._load_registry()

        if key not in registry:
            print(f"[ERROR] Prompt not registered: {key}")
            return None

        current_entry = registry[key]
        current_text = current_entry["current_text"]

        # Build strategy-specific prompt
        strategy_prompts = {
            "refine": (
                "Make small, targeted improvements to this system prompt. "
                "Keep overall structure and philosophy. Focus on clarity, specificity, and edge cases."
            ),
            "restructure": (
                "Rewrite this system prompt from scratch with better organization. "
                "Preserve the core purpose but improve hierarchy, flow, and logical grouping."
            ),
            "simplify": (
                "Reduce token count of this prompt by 20-30% without losing critical information. "
                "Remove redundancy, combine similar ideas, use shorter phrasing."
            ),
            "specialize": (
                "Enhance this prompt for <OPERATOR>'s specific consulting workflows. "
                "Add operator-specific reasoning patterns, decision logic, and operational constraints."
            ),
        }

        strategy_desc = strategy_prompts.get(strategy, strategy_prompts["refine"])

        generation_prompt = f"""You are a prompt engineering expert optimizing system prompts for an AI agent.

Current prompt (module: {module_name}, name: {prompt_name}):
---
{current_text}
---

Task: {strategy_desc}

Return ONLY the improved prompt text, without explanation or markdown. Start immediately with the first word of the prompt."""

        try:
            variant_text = call_llm(
                model="reasoning",
                messages=[
                    {"role": "user", "content": generation_prompt}
                ],
                temperature=0.7,
            )

            variant_id = self._generate_variant_id(variant_text)
            variant = PromptVariant(
                variant_id=variant_id,
                module_name=module_name,
                prompt_name=prompt_name,
                text=variant_text,
                strategy=strategy,
                created_at=datetime.now().isoformat(),
            )

            self._save_experiment(variant)
            print(f"[VARIANT] {key}@{strategy}: {variant_id}")
            return variant

        except Exception as e:
            print(f"[ERROR] Failed to generate variant: {e}")
            return None

    def test_variant(
        self,
        module_name: str,
        prompt_name: str,
        variant_text: str,
        test_tasks: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Run A/B comparison: current prompt vs variant."""
        key = f"{module_name}:{prompt_name}"
        registry = self._load_registry()

        if key not in registry:
            print(f"[ERROR] Prompt not registered: {key}")
            return {}

        current_text = registry[key]["current_text"]

        # Default test tasks (can be extended)
        if not test_tasks:
            test_tasks = self._get_default_test_tasks(module_name, prompt_name)

        if not test_tasks:
            print(f"[WARN] No test tasks for {key}")
            return {"error": "no_test_tasks"}

        results = {
            "module": module_name,
            "prompt": prompt_name,
            "test_date": datetime.now().isoformat(),
            "test_count": len(test_tasks),
            "current_score": 0.0,
            "variant_score": 0.0,
            "winner": None,
            "confidence": 0.0,
            "details": [],
        }

        # Run tests for both prompts
        current_results = []
        variant_results = []

        for i, task in enumerate(test_tasks):
            task_input = task.get("input", "")
            expected_output = task.get("expected", "")

            # Current prompt test
            try:
                current_output = call_llm(
                    model="reasoning",
                    system=current_text,
                    messages=[{"role": "user", "content": task_input}],
                    temperature=0.5,
                )
                current_score = self._judge_output(
                    current_output, expected_output, task_input
                )
                current_results.append(current_score)
            except Exception as e:
                print(f"[WARN] Current test {i} failed: {e}")
                current_results.append(0.0)

            # Variant test
            try:
                variant_output = call_llm(
                    model="reasoning",
                    system=variant_text,
                    messages=[{"role": "user", "content": task_input}],
                    temperature=0.5,
                )
                variant_score = self._judge_output(
                    variant_output, expected_output, task_input
                )
                variant_results.append(variant_score)
            except Exception as e:
                print(f"[WARN] Variant test {i} failed: {e}")
                variant_results.append(0.0)

            results["details"].append({
                "task_idx": i,
                "current": current_results[-1],
                "variant": variant_results[-1],
            })

        # Calculate averages
        current_avg = sum(current_results) / len(current_results) if current_results else 0.0
        variant_avg = sum(variant_results) / len(variant_results) if variant_results else 0.0

        results["current_score"] = round(current_avg, 3)
        results["variant_score"] = round(variant_avg, 3)

        # Determine winner with confidence
        score_diff = abs(variant_avg - current_avg)
        results["confidence"] = min(score_diff / 0.3, 1.0)  # Cap at 1.0

        if variant_avg > current_avg:
            results["winner"] = "variant"
        elif current_avg > variant_avg:
            results["winner"] = "current"
        else:
            results["winner"] = "tie"

        print(
            f"[TEST] {key}: current={results['current_score']}, "
            f"variant={results['variant_score']}, winner={results['winner']}"
        )

        return results

    def promote_variant(
        self,
        module_name: str,
        prompt_name: str,
        variant_id: str,
    ) -> bool:
        """Promote variant to current if test winner."""
        key = f"{module_name}:{prompt_name}"
        registry = self._load_registry()

        if key not in registry:
            print(f"[ERROR] Prompt not registered: {key}")
            return False

        # Find variant
        variant = self._find_variant(variant_id)
        if not variant:
            print(f"[ERROR] Variant not found: {variant_id}")
            return False

        # Update registry
        old_text = registry[key]["current_text"]
        registry[key]["current_text"] = variant["text"]
        registry[key]["best_variant_id"] = variant_id
        registry[key]["last_tested"] = datetime.now().isoformat()
        registry[key]["test_count"] += 1

        self._save_registry(registry)

        # Mark variant as promoted
        variant["promoted"] = True
        self._update_experiment(variant)

        print(f"[PROMOTED] {key}@{variant_id}")
        print(f"  Strategy: {variant['strategy']}")
        print(f"  Old length: {len(old_text)}, New length: {len(variant['text'])}")

        return True

    def scan_modules(self) -> List[str]:
        """Scan all .py files, find PROMPT constants, register them."""
        prompts_found = []
        py_files = list(NSOS_DIR.glob("*.py"))

        for py_file in py_files:
            if py_file.name == "prompt_evolver.py":
                continue

            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    content = f.read()

                # Find PROMPT = "..." or PROMPT = """...""" patterns
                pattern = r'((?:SYSTEM_)?PROMPT|SYSTEM_INSTRUCTION)\s*=\s*["\']+"\'\'\'(?:.*?)[\'\']+"\'\'\'|(?:PROMPT|SYSTEM_INSTRUCTION)\s*=\s*["\'](?:[^"\']*)["\']'
                matches = re.finditer(
                    r'((?:SYSTEM_)?PROMPT|SYSTEM_INSTRUCTION)\s*=\s*("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"[^"]*"|\'[^\']*\')',
                    content,
                    re.MULTILINE,
                )

                for match in matches:
                    var_name = match.group(1)
                    var_value = match.group(2)

                    # Extract actual text
                    if var_value.startswith('"""') or var_value.startswith("'''"):
                        prompt_text = var_value[3:-3].strip()
                    else:
                        prompt_text = var_value[1:-1].strip()

                    # Only register if substantial
                    if len(prompt_text) > 50:
                        module_name = py_file.stem
                        prompt_name = var_name
                        purpose = prompt_text[:100] + "..."

                        self.register_prompt(
                            module_name=module_name,
                            prompt_name=prompt_name,
                            current_text=prompt_text,
                            purpose=purpose,
                        )

                        prompts_found.append(f"{module_name}:{prompt_name}")

            except Exception as e:
                print(f"[WARN] Failed to scan {py_file}: {e}")

        print(f"\n[SCAN] Found {len(prompts_found)} prompts")
        return prompts_found

    def evolve_cycle(self, max_experiments: int = 3) -> Dict[str, Any]:
        """Automated evolution: generate, test, promote."""
        registry = self._load_registry()

        if not registry:
            print("[WARN] No prompts registered. Run --scan first.")
            return {}

        # Find underperforming prompts
        candidates = []
        for key, entry in registry.items():
            module_name = entry["module_name"]
            prompt_name = entry["prompt_name"]

            # Priority: never tested, or low score, or stale
            test_age = (
                (datetime.now() - datetime.fromisoformat(entry["last_tested"])).days
                if entry["last_tested"]
                else 999
            )

            priority = 999 + test_age - (entry.get("avg_score") or 0.0) * 100
            candidates.append((priority, module_name, prompt_name, key))

        candidates.sort(reverse=True)
        candidates = candidates[:max_experiments]

        results = {
            "cycle_date": datetime.now().isoformat(),
            "experiments": [],
        }

        for _, module_name, prompt_name, key in candidates:
            print(f"\n[EVOLVE] {key}")

            # Generate 2 variants per prompt
            for strategy in ["refine", "simplify"]:
                variant = self.generate_variant(module_name, prompt_name, strategy)
                if not variant:
                    continue

                # Test
                test_result = self.test_variant(
                    module_name,
                    prompt_name,
                    variant.text,
                )

                if test_result.get("winner") == "variant":
                    self.promote_variant(module_name, prompt_name, variant.variant_id)
                    results["experiments"].append({
                        "key": key,
                        "strategy": strategy,
                        "variant_id": variant.variant_id,
                        "promoted": True,
                        "score": test_result.get("variant_score"),
                    })
                else:
                    results["experiments"].append({
                        "key": key,
                        "strategy": strategy,
                        "variant_id": variant.variant_id,
                        "promoted": False,
                        "score": test_result.get("variant_score"),
                    })

        return results

    def get_prompt_health(self) -> Dict[str, Any]:
        """Show which prompts have been tested, which haven't, which are underperforming."""
        registry = self._load_registry()

        if not registry:
            print("[INFO] No prompts registered.")
            return {}

        health = {
            "total": len(registry),
            "never_tested": [],
            "stale": [],
            "underperforming": [],
            "healthy": [],
        }

        now = datetime.now()

        for key, entry in registry.items():
            last_tested = entry.get("last_tested")
            avg_score = entry.get("avg_score")

            if not last_tested:
                health["never_tested"].append({
                    "key": key,
                    "purpose": entry["purpose"][:60],
                })
            else:
                test_age = (now - datetime.fromisoformat(last_tested)).days
                if test_age > 7:
                    health["stale"].append({
                        "key": key,
                        "last_tested_days_ago": test_age,
                        "score": avg_score,
                    })
                elif avg_score and avg_score < 0.6:
                    health["underperforming"].append({
                        "key": key,
                        "score": avg_score,
                    })
                else:
                    health["healthy"].append({
                        "key": key,
                        "score": avg_score,
                        "test_count": entry.get("test_count", 0),
                    })

        return health

    # ── PRIVATE HELPERS ──

    def _load_registry(self) -> Dict[str, Dict]:
        """Load registry from disk."""
        if not self.registry_path.exists():
            return {}
        try:
            with open(self.registry_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_registry(self, registry: Dict[str, Dict]) -> None:
        """Save registry to disk."""
        with open(self.registry_path, "w") as f:
            json.dump(registry, f, indent=2)

    def _save_experiment(self, variant: PromptVariant) -> None:
        """Append experiment to JSONL log."""
        with open(self.experiments_path, "a") as f:
            f.write(json.dumps(variant.to_dict()) + "\n")

    def _update_experiment(self, variant: Dict[str, Any]) -> None:
        """Update variant in experiments log."""
        experiments = []
        if self.experiments_path.exists():
            with open(self.experiments_path, "r") as f:
                experiments = [json.loads(line) for line in f if line.strip()]

        # Update matching variant
        for i, exp in enumerate(experiments):
            if exp.get("variant_id") == variant.get("variant_id"):
                experiments[i] = variant
                break

        with open(self.experiments_path, "w") as f:
            for exp in experiments:
                f.write(json.dumps(exp) + "\n")

    def _find_variant(self, variant_id: str) -> Optional[Dict[str, Any]]:
        """Find variant by ID in experiments log."""
        if not self.experiments_path.exists():
            return None
        try:
            with open(self.experiments_path, "r") as f:
                for line in f:
                    exp = json.loads(line)
                    if exp.get("variant_id") == variant_id:
                        return exp
        except Exception:
            pass
        return None

    def _generate_variant_id(self, text: str) -> str:
        """Generate deterministic variant ID from content hash."""
        hash_obj = hashlib.sha256(text.encode())
        return f"var_{hash_obj.hexdigest()[:12]}"

    def _get_default_test_tasks(self, module_name: str, prompt_name: str) -> List[Dict[str, str]]:
        """Load default test tasks (can be extended per module)."""
        # Placeholder: each module can define test_tasks.json
        test_file = NSOS_DIR / module_name / "test_tasks.json"
        if test_file.exists():
            try:
                with open(test_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _judge_output(self, output: str, expected: str, input_text: str) -> float:
        """Score output quality (0.0-1.0) using simple heuristics."""
        if not output:
            return 0.0

        score = 0.5  # Base score

        # Check for expected keywords
        if expected and any(word in output.lower() for word in expected.lower().split()):
            score += 0.2

        # Check length reasonableness (not too short, not too long)
        expected_len = len(expected) if expected else len(input_text)
        output_len = len(output)
        len_ratio = output_len / max(expected_len, 1)

        if 0.5 < len_ratio < 2.0:
            score += 0.2

        # Check coherence (rough heuristic: has periods, lowercase variety)
        if output.count(".") > 0 and not output.isupper() and not output.islower():
            score += 0.1

        return min(score, 1.0)


def main():
    parser = argparse.ArgumentParser(
        description="NSOS Prompt Evolution Engine"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")

    subparsers.add_parser("scan", help="Scan modules and register prompts")
    subparsers.add_parser("evolve", help="Run automated evolution cycle")
    subparsers.add_parser("health", help="Show prompt health status")

    test_parser = subparsers.add_parser("test", help="Test a specific prompt variant")
    test_parser.add_argument("module", help="Module name")
    test_parser.add_argument("prompt", help="Prompt name")

    history_parser = subparsers.add_parser("history", help="Show evolution history")
    history_parser.add_argument("module", help="Module name")

    args = parser.parse_args()
    evolver = PromptEvolver()

    if args.command == "scan":
        evolver.scan_modules()

    elif args.command == "evolve":
        result = evolver.evolve_cycle(max_experiments=3)
        print(json.dumps(result, indent=2))

    elif args.command == "health":
        health = evolver.get_prompt_health()
        print(json.dumps(health, indent=2))

    elif args.command == "test":
        result = evolver.test_variant(args.module, args.prompt, "")
        print(json.dumps(result, indent=2))

    elif args.command == "history":
        registry = evolver._load_registry()
        key = f"{args.module}:*"
        matching = {k: v for k, v in registry.items() if k.startswith(args.module + ":")}
        print(json.dumps(matching, indent=2, default=str))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
