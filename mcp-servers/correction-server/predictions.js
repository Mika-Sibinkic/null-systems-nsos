/**
 * Predictions Engine — Tracks predictions, outcomes, and residuals for the Learning Loop.
 *
 * This is the data layer for the Adaptive Learning Loop skill.
 * It tracks what the model predicted, what actually happened,
 * and computes residuals per category to determine learning phase.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { join } from 'path';

// ── Configuration ──────────────────────────────────────────────────────────

const CORRECTIONS_DIR = process.env.CORRECTIONS_DIR
  || join(process.env.HOME, 'Desktop', 'Null Systems', 'business-framework', '.claude', 'corrections');

const PREDICTIONS_FILE = join(CORRECTIONS_DIR, 'predictions.json');
const RESIDUALS_FILE = join(CORRECTIONS_DIR, 'residuals.json');

// ── Phase Thresholds ───────────────────────────────────────────────────────

// Phase thresholds are intentionally HIGH — the model must EARN the right to stop asking.
// Mika's instruction: "the model shouldn't be shy with questions"
const PHASE_THRESHOLDS = {
  ACTIVE: { minPredictions: 0, minAccuracy: 0 },
  GUIDED: { minPredictions: 20, minAccuracy: 0.6 },
  AUTONOMOUS: { minPredictions: 50, minAccuracy: 0.8 },
};
// Confidence decay: how much confidence drops per session of inactivity
const CONFIDENCE_DECAY_PER_SESSION = 0.04; // 20% over 5 sessions
const MAX_STALE_SESSIONS = 20;

// Residual change rates (asymmetric by design)
const RESIDUAL_CHANGES = {
  explicit_confirm: -1.0,    // strong shrink
  no_correction: -0.1,       // very slow shrink (silence ≠ approval)
  correction: 2.0,           // fast grow
  redirect: 3.0,             // very fast grow
  frustration: 4.0,          // maximum grow
};

// ── Data Access ────────────────────────────────────────────────────────────

function ensureDir() {
  if (!existsSync(CORRECTIONS_DIR)) {
    mkdirSync(CORRECTIONS_DIR, { recursive: true });
  }
}

function loadPredictions() {
  ensureDir();
  if (!existsSync(PREDICTIONS_FILE)) return [];
  try { return JSON.parse(readFileSync(PREDICTIONS_FILE, 'utf-8')); }
  catch { return []; }
}

function savePredictions(predictions) {
  ensureDir();  writeFileSync(PREDICTIONS_FILE, JSON.stringify(predictions, null, 2));
}

function loadResiduals() {
  ensureDir();
  if (!existsSync(RESIDUALS_FILE)) return {};
  try { return JSON.parse(readFileSync(RESIDUALS_FILE, 'utf-8')); }
  catch { return {}; }
}

function saveResiduals(residuals) {
  ensureDir();
  writeFileSync(RESIDUALS_FILE, JSON.stringify(residuals, null, 2));
}

// ── Core Operations ────────────────────────────────────────────────────────

/**
 * Log a prediction before acting or presenting options.
 */
export function logPrediction({
  category,
  situation,
  prediction,
  confidence,
  evidence_source,
  alternatives = [],
  session_id = 'unknown'
}) {
  const predictions = loadPredictions();
  const id = `pred_${new Date().toISOString().split('T')[0]}_${String(predictions.length + 1).padStart(3, '0')}`;

  // Cap confidence for unsourced predictions
  let adjustedConfidence = confidence || 0.5;
  if (!evidence_source || evidence_source === '' || evidence_source === 'intuition') {
    adjustedConfidence = Math.min(adjustedConfidence, 0.5);
  }

  const pred = {
    id,
    timestamp: new Date().toISOString(),
    category: category || 'uncategorized',
    situation,
    prediction,
    confidence: adjustedConfidence,
    evidence_source: evidence_source || 'none',
    alternatives,
    session_id,
    outcome: null,
    residual: null,
  };

  predictions.push(pred);
  savePredictions(predictions);

  return {
    prediction_id: id,
    confidence: adjustedConfidence,
    confidence_capped: adjustedConfidence < (confidence || 0.5),    phase: getPhaseForCategory(category),
  };
}

/**
 * Log the outcome after Mika responds to a prediction.
 */
export function logOutcome({
  prediction_id,
  actual,
  outcome_type,
  mika_words = '',
}) {
  const predictions = loadPredictions();
  const residuals = loadResiduals();

  const pred = predictions.find(p => p.id === prediction_id);
  if (!pred) {
    return { error: `Prediction ${prediction_id} not found` };
  }

  // Determine if prediction was correct
  const predictionCorrect = actual.toLowerCase().includes(pred.prediction.toLowerCase())
    || pred.prediction.toLowerCase().includes(actual.toLowerCase());

  // Calculate residual change
  const residualChange = RESIDUAL_CHANGES[outcome_type] || 0;
  const computedResidual = predictionCorrect ? 0 : Math.abs(residualChange);

  // Update prediction record
  pred.outcome = actual;  pred.outcome_type = outcome_type;
  pred.mika_words = mika_words;
  pred.residual = computedResidual;
  pred.prediction_correct = predictionCorrect;
  savePredictions(predictions);

  // Update category residuals
  const cat = pred.category;
  if (!residuals[cat]) {
    residuals[cat] = {
      cumulative_residual: 0,
      total_predictions: 0,
      correct_predictions: 0,
      last_updated: null,
      last_tested_session: pred.session_id,
      sessions_since_test: 0,
      phase_history: [],
    };
  }

  const catData = residuals[cat];
  catData.cumulative_residual += residualChange;
  catData.cumulative_residual = Math.max(0, catData.cumulative_residual); // floor at 0
  catData.total_predictions++;
  if (predictionCorrect) catData.correct_predictions++;
  catData.last_updated = new Date().toISOString();
  catData.last_tested_session = pred.session_id;
  catData.sessions_since_test = 0;

  // Check for phase transition  const oldPhase = getCurrentPhase(catData);
  const accuracy = catData.correct_predictions / catData.total_predictions;
  const newPhase = computePhase(catData.total_predictions, accuracy);

  if (newPhase !== oldPhase) {
    catData.phase_history.push({
      from: oldPhase,
      to: newPhase,
      timestamp: new Date().toISOString(),
      reason: newPhase < oldPhase
        ? 'regression — accuracy dropped or consecutive failures'
        : 'progression — accuracy improved with sufficient predictions',
    });
  }

  saveResiduals(residuals);

  return {
    prediction_id,
    prediction_correct: predictionCorrect,
    outcome_type,
    residual_change: residualChange,
    category: cat,
    category_accuracy: (accuracy * 100).toFixed(1) + '%',
    category_phase: phaseNumberToName(newPhase),
    phase_changed: newPhase !== oldPhase,
    phase_direction: newPhase !== oldPhase ? (newPhase > oldPhase ? 'progressed' : 'REGRESSED') : 'stable',
  };
}

/** * Get current residuals and phases for all categories.
 */
export function getResiduals() {
  const residuals = loadResiduals();
  const predictions = loadPredictions();

  const result = {};
  for (const [cat, data] of Object.entries(residuals)) {
    const accuracy = data.total_predictions > 0
      ? data.correct_predictions / data.total_predictions
      : 0;

    // Apply confidence decay for stale categories
    const decayedAccuracy = applyDecay(accuracy, data.sessions_since_test);

    result[cat] = {
      total_predictions: data.total_predictions,
      correct_predictions: data.correct_predictions,
      raw_accuracy: (accuracy * 100).toFixed(1) + '%',
      decayed_accuracy: (decayedAccuracy * 100).toFixed(1) + '%',
      cumulative_residual: data.cumulative_residual.toFixed(2),
      phase: phaseNumberToName(computePhase(data.total_predictions, decayedAccuracy)),
      sessions_since_test: data.sessions_since_test,
      stale: data.sessions_since_test >= 5,
      last_updated: data.last_updated,
    };
  }

  // Check for convergence-to-self
  const recentPredictions = predictions.slice(-50);  const sourceCounts = {};
  for (const p of recentPredictions) {
    const src = p.evidence_source || 'none';
    sourceCounts[src] = (sourceCounts[src] || 0) + 1;
  }
  const totalRecent = recentPredictions.length;
  const topSource = Object.entries(sourceCounts).sort((a, b) => b[1] - a[1])[0];
  const convergenceRisk = topSource && totalRecent > 0
    ? topSource[1] / totalRecent > 0.8
    : false;

  return {
    categories: result,
    convergence_risk: convergenceRisk,
    convergence_detail: convergenceRisk
      ? `WARNING: ${(topSource[1] / totalRecent * 100).toFixed(0)}% of recent predictions cite "${topSource[0]}". Evidence base may be too narrow.`
      : 'OK — evidence sources are diverse',
    reality_check_due: shouldTriggerRealityCheck(predictions),
  };
}

/**
 * Get the current learning phase for a specific category.
 */
export function getLearningPhase(category) {
  const residuals = loadResiduals();
  const catData = residuals[category || 'uncategorized'];

  if (!catData) {
    return {      category: category || 'uncategorized',
      phase: 'ACTIVE',
      reason: 'No predictions logged for this category yet',
      total_predictions: 0,
      accuracy: '0%',
    };
  }

  const accuracy = catData.total_predictions > 0
    ? catData.correct_predictions / catData.total_predictions
    : 0;
  const decayedAccuracy = applyDecay(accuracy, catData.sessions_since_test);
  const phase = computePhase(catData.total_predictions, decayedAccuracy);

  return {
    category,
    phase: phaseNumberToName(phase),
    total_predictions: catData.total_predictions,
    raw_accuracy: (accuracy * 100).toFixed(1) + '%',
    decayed_accuracy: (decayedAccuracy * 100).toFixed(1) + '%',
    sessions_since_test: catData.sessions_since_test,
    stale: catData.sessions_since_test >= 5,
    phase_history: catData.phase_history || [],
  };
}

/**
 * Trigger a reality check — returns the top assumptions that need Mika's validation.
 */
export function triggerRealityCheck() {  const predictions = loadPredictions();
  const residuals = loadResiduals();

  // Find most-used predictions (highest confidence + most repeated pattern)
  const patternCounts = {};
  for (const pred of predictions) {
    const key = `${pred.category}:${pred.prediction}`;
    if (!patternCounts[key]) {
      patternCounts[key] = {
        category: pred.category,
        prediction: pred.prediction,
        confidence: pred.confidence,
        evidence_source: pred.evidence_source,
        count: 0,
        last_tested: null,
        ever_confirmed: false,
      };
    }
    patternCounts[key].count++;
    if (pred.outcome_type === 'explicit_confirm') {
      patternCounts[key].ever_confirmed = true;
      patternCounts[key].last_tested = pred.timestamp;
    }
  }

  // Sort by risk: high-count + never-confirmed + stale = highest risk
  const assumptions = Object.values(patternCounts)
    .map(p => ({
      ...p,      risk_score: p.count * (p.ever_confirmed ? 0.5 : 2.0) * (p.last_tested ? 0.5 : 2.0),
    }))
    .sort((a, b) => b.risk_score - a.risk_score)
    .slice(0, 5);

  return {
    trigger_reason: 'Periodic reality check — validating assumptions against Mika',
    top_assumptions: assumptions.map((a, i) => ({
      rank: i + 1,
      assumption: `For ${a.category} decisions: "${a.prediction}"`,
      based_on: a.evidence_source,
      times_used: a.count,
      ever_explicitly_confirmed: a.ever_confirmed,
      risk_level: a.risk_score > 5 ? 'HIGH' : a.risk_score > 2 ? 'MEDIUM' : 'LOW',
    })),
    instructions: 'Present these to Mika and ask for explicit confirmation or correction. Log outcomes for each.',
  };
}

/**
 * Increment sessions_since_test for all categories (call at session start).
 */
export function incrementSessionCounters() {
  const residuals = loadResiduals();
  for (const cat of Object.values(residuals)) {
    cat.sessions_since_test = (cat.sessions_since_test || 0) + 1;
  }
  saveResiduals(residuals);
}
// ── Helper Functions ───────────────────────────────────────────────────────

function computePhase(totalPredictions, accuracy) {
  if (totalPredictions >= PHASE_THRESHOLDS.AUTONOMOUS.minPredictions
      && accuracy >= PHASE_THRESHOLDS.AUTONOMOUS.minAccuracy) return 3;
  if (totalPredictions >= PHASE_THRESHOLDS.GUIDED.minPredictions
      && accuracy >= PHASE_THRESHOLDS.GUIDED.minAccuracy) return 2;
  return 1;
}

function getCurrentPhase(catData) {
  const accuracy = catData.total_predictions > 0
    ? catData.correct_predictions / catData.total_predictions
    : 0;
  return computePhase(catData.total_predictions, accuracy);
}

function getPhaseForCategory(category) {
  const residuals = loadResiduals();
  const catData = residuals[category || 'uncategorized'];
  if (!catData) return 'ACTIVE';
  return phaseNumberToName(getCurrentPhase(catData));
}

function phaseNumberToName(n) {
  return { 1: 'ACTIVE', 2: 'GUIDED', 3: 'AUTONOMOUS' }[n] || 'ACTIVE';
}

function applyDecay(accuracy, sessionsSinceTest) {  if (!sessionsSinceTest || sessionsSinceTest <= 0) return accuracy;
  const decay = Math.min(sessionsSinceTest, MAX_STALE_SESSIONS) * CONFIDENCE_DECAY_PER_SESSION;
  return Math.max(0.3, accuracy - decay); // Floor at 30%
}

function shouldTriggerRealityCheck(predictions) {
  // Check if we've gone 5+ sessions without a correction
  const recent = predictions.slice(-100);
  const corrections = recent.filter(p => p.outcome_type === 'correction' || p.outcome_type === 'redirect');

  if (recent.length >= 20 && corrections.length === 0) {
    return true;
  }

  return false;
}

export default {
  logPrediction,
  logOutcome,
  getResiduals,
  getLearningPhase,
  triggerRealityCheck,
  incrementSessionCounters,
};