# Council Protocol — Recursive-Weight Scoring

> Authoritative spec for how 6 meta-team findings collapse into a single ranked list of opportunities for the executive report.

## Inputs

Each meta-team produces a `Finding` JSON object:

```json
{
  "id": "fin-2026-05-15-0007",
  "team": "financial",
  "headline": "Proposal assembly burns 11h partner-time/wk",
  "evidence": ["..."],
  "impact_usd": 180000,
  "impact_hours": 572,
  "confidence": 0.83,
  "embedding": [0.123, ...]
}
```

Plus from the tenant snapshot:
- `ceo_priorities`: ranked list with weights (e.g., `[{"text": "raise net retention", "weight": 1.0}, ...]`)
- `known_baseline`: list of items the CEO already mentioned as known, with embeddings

## Scoring algorithm

```python
def rank_findings(findings, ceo_priorities, known_baseline):
    """Recursive-weight Borda + multiplicative weighting.

    Per finding, compute:
      - prio:     max cosine sim to a CEO priority, weighted by priority rank
      - novelty:  1 - max sim to known_baseline (higher = newer)
      - corrob:   log2(1 + #distinct teams that surfaced this finding-cluster)
      - impact:   z-normalized blend of $ and hours

    Combine via:
      composite = 0.30*prio + 0.25*novelty + 0.20*corrob + 0.25*impact
      final     = borda_position(f, all) * (1 + composite)
    """
    scored = []
    for f in findings:
        prio    = max((cos(f.emb, p.emb) * p.weight for p in ceo_priorities), default=0)
        novelty = 1.0 - max((cos(f.emb, k.emb) for k in known_baseline), default=0)
        corrob  = math.log2(1 + len({c.team for c in f.cluster}))
        impact  = 0.6 * z_norm(f.impact_usd) + 0.4 * z_norm(f.impact_hours)

        composite = 0.30*prio + 0.25*novelty + 0.20*corrob + 0.25*impact

        # Pairwise LLM-judge tournament gives Borda position
        borda = borda_count(f, findings, judge=ensemble_judge)

        scored.append((f, borda * (1 + composite)))
    return sorted(scored, key=lambda t: -t[1])
```

## Pairwise LLM-judge tournament

Why pairwise: 2025–2026 LLM-judge literature consistently shows pairwise comparisons outperform absolute scalar scoring for ranking tasks (lower variance, less position bias).

Implementation:
- For N findings, sample `O(N log N)` pairs (full round-robin only when N ≤ 20).
- Each pair → judge ensemble of 3 LLMs (NIM R1-distill + DeepSeek V3.2 + Groq Llama 3.3) returns "A wins" / "B wins" / "tie" with rationale.
- Majority vote; ties broken by R1-distill (the "tiebreaker judge").
- Borda position = N - (rank assigned by aggregated wins).

## Hyperparameters

The `0.30 / 0.25 / 0.20 / 0.25` weights are tunable per engagement. Calibration:
1. Run on 2–3 pilot reports.
2. Have Mika (or, eventually, the client engagement lead) manually rank the top 10 findings.
3. Fit weights to minimize Spearman distance from manual rank.
4. Persist tuned weights to `client/snapshots/{tenant_id}/council-weights.json`.

## Council debate (the "debate" part)

The Borda + composite gives a candidate ranking. Then a **debate node** runs:
1. Each meta-team gets to nominate 1 finding for "promote up the ranking" with a 100-token rationale.
2. Each meta-team gets to nominate 1 finding for "demote — too speculative / too small" with a 100-token rationale.
3. Council judge reads all rationales, decides whether to adjust ranks (max 3 swaps per debate round).
4. Repeat for 2 rounds or until no swaps occur.

This catches cases where pure scoring missed cross-cutting context (e.g., a financial finding that the operational team can confirm is already underway).

## Artifacts

- `runs/{run_id}/council/candidates.jsonl` — pre-debate ranked list with all signals broken out
- `runs/{run_id}/council/debate-rounds.jsonl` — every nomination + rationale + decision
- `runs/{run_id}/council/final.jsonl` — post-debate ranked list, fed to the reporter

## Failure modes + recovery

| Failure | Symptom | Recovery |
|---|---|---|
| Judge ensemble disagrees often | high tie rate (>30%) on pairwise comparisons | escalate to Anthropic Claude judge for ties |
| All findings score low | composite < 0.2 for top 3 | snapshot data is too thin — request more sources or interviews from client |
| Debate rounds never converge | swaps continue past round 5 | freeze ranking, log warning, ship with caveat in report |
