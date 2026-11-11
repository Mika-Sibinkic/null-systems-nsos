// node --test. Each run writes to its own temp CORRECTIONS_DIR, never ~/.nsos.
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const dir = mkdtempSync(join(tmpdir(), 'corr-'));
process.env.CORRECTIONS_DIR = dir;
after(() => rmSync(dir, { recursive: true, force: true }));
const { logPrediction, logOutcome } = await import('./predictions.js');

const predict = (category) =>
  logPrediction({ category, situation: 's', prediction: 'a', confidence: 0.9, evidence_source: 'c1' });

test('log_outcome after log_prediction returns a result, not an error', () => {
  const { prediction_id } = predict('smoke');
  const r = logOutcome({ prediction_id, actual: 'a', outcome_type: 'explicit_confirm' });
  assert.equal(r.error, undefined);
  assert.equal(r.prediction_correct, true);
  assert.equal(r.phase_changed, false);
});

test('the 20th correct outcome moves the category from ACTIVE to GUIDED, once', () => {
  const changed = [];
  for (let i = 1; i <= 21; i++) {
    const { prediction_id } = predict('phase');
    const r = logOutcome({ prediction_id, actual: 'a', outcome_type: 'explicit_confirm' });
    if (r.phase_changed) changed.push([i, r.category_phase, r.phase_direction]);
  }
  assert.deepEqual(changed, [[20, 'GUIDED', 'progressed']]);
});
