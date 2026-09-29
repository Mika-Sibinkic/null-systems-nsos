/**
 * Corrections Store — Storage and retrieval engine for Null Systems corrections.
 *
 * Uses a simple JSON file + inverted keyword index. No vector DB needed.
 * Designed for <10,000 corrections (covers years of daily usage).
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { join } from 'path';

// ── Configuration ──────────────────────────────────────────────────────────

const CORRECTIONS_DIR = process.env.CORRECTIONS_DIR
  || join(process.env.HOME, '.nsos', 'corrections');

const CORRECTIONS_FILE = join(CORRECTIONS_DIR, 'corrections.json');
const INDEX_FILE = join(CORRECTIONS_DIR, 'index.json');
const STATS_FILE = join(CORRECTIONS_DIR, 'stats.json');

// ── Stop Words (excluded from keyword indexing) ────────────────────────────

const STOP_WORDS = new Set([
  'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
  'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
  'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
  'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
  'into', 'through', 'during', 'before', 'after', 'above', 'below',
  'and', 'but', 'or', 'nor', 'not', 'so', 'yet', 'both', 'either',  'neither', 'each', 'every', 'all', 'any', 'few', 'more', 'most',
  'other', 'some', 'such', 'no', 'only', 'same', 'than', 'too', 'very',
  'just', 'because', 'if', 'when', 'where', 'how', 'what', 'which',
  'who', 'whom', 'this', 'that', 'these', 'those', 'i', 'me', 'my',
  'we', 'our', 'you', 'your', 'he', 'him', 'his', 'she', 'her', 'it',
  'its', 'they', 'them', 'their', 'about', 'up', 'out', 'then', 'also'
]);

// ── Initialization ─────────────────────────────────────────────────────────

function ensureDir() {
  if (!existsSync(CORRECTIONS_DIR)) {
    mkdirSync(CORRECTIONS_DIR, { recursive: true });
  }
}

function loadCorrections() {
  ensureDir();
  if (!existsSync(CORRECTIONS_FILE)) return [];
  try {
    return JSON.parse(readFileSync(CORRECTIONS_FILE, 'utf-8'));
  } catch { return []; }
}

function saveCorrections(corrections) {
  ensureDir();
  writeFileSync(CORRECTIONS_FILE, JSON.stringify(corrections, null, 2));
}

function loadIndex() {
  ensureDir();  if (!existsSync(INDEX_FILE)) return {};
  try {
    return JSON.parse(readFileSync(INDEX_FILE, 'utf-8'));
  } catch { return {}; }
}

function saveIndex(index) {
  ensureDir();
  writeFileSync(INDEX_FILE, JSON.stringify(index));
}

function loadStats() {
  ensureDir();
  if (!existsSync(STATS_FILE)) return { patterns: {}, total: 0, lastUpdated: null };
  try {
    return JSON.parse(readFileSync(STATS_FILE, 'utf-8'));
  } catch { return { patterns: {}, total: 0, lastUpdated: null }; }
}

function saveStats(stats) {
  ensureDir();
  writeFileSync(STATS_FILE, JSON.stringify(stats, null, 2));
}

// ── Tokenization ───────────────────────────────────────────────────────────

function tokenize(text) {
  if (!text) return [];
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, ' ')    .split(/\s+/)
    .filter(w => w.length > 2 && !STOP_WORDS.has(w));
}

// ── Core Operations ────────────────────────────────────────────────────────

/**
 * Add a correction to the store and update the index.
 */
export function logCorrection(correction) {
  const corrections = loadCorrections();
  const index = loadIndex();
  const stats = loadStats();

  // Generate ID if not provided
  if (!correction.id) {
    const date = new Date().toISOString().split('T')[0];
    const count = corrections.filter(c => c.id?.startsWith(`corr_${date}`)).length + 1;
    correction.id = `corr_${date}_${String(count).padStart(3, '0')}`;
  }

  // Add timestamp if not provided
  if (!correction.timestamp) {
    correction.timestamp = new Date().toISOString();
  }

  // Generate keywords from all text fields
  const textFields = [
    correction.context,
    correction.what_model_did,    correction.what_operator_wanted,
    correction.operator_exact_words,
    correction.detection_rule,
    correction.pattern_name
  ].filter(Boolean);

  const keywords = [...new Set(textFields.flatMap(tokenize))];
  correction.keywords = keywords;

  // Add to corrections list
  corrections.push(correction);
  saveCorrections(corrections);

  // Update inverted index
  for (const keyword of keywords) {
    if (!index[keyword]) index[keyword] = [];
    index[keyword].push({
      id: correction.id,
      score: 1.0,
      timestamp: correction.timestamp
    });
  }
  saveIndex(index);

  // Update stats
  const patternName = correction.pattern_name || 'unknown';
  if (!stats.patterns[patternName]) {
    stats.patterns[patternName] = { count: 0, sessions: [], lastSeen: null };
  }
  stats.patterns[patternName].count++;  stats.patterns[patternName].lastSeen = correction.timestamp;
  if (correction.session_id && !stats.patterns[patternName].sessions.includes(correction.session_id)) {
    stats.patterns[patternName].sessions.push(correction.session_id);
  }
  stats.total = corrections.length;
  stats.lastUpdated = new Date().toISOString();
  saveStats(stats);

  return {
    id: correction.id,
    total_corrections: corrections.length,
    pattern_count: stats.patterns[patternName].count,
    pattern_sessions: stats.patterns[patternName].sessions.length
  };
}

/**
 * Get the N most recent corrections.
 */
export function getRecentCorrections(limit = 20) {
  const corrections = loadCorrections();
  return corrections
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .slice(0, limit)
    .map(formatCorrection);
}

/**
 * Search corrections by query string. Returns ranked results.
 */export function getRelevantCorrections(query, limit = 10) {
  const corrections = loadCorrections();
  const index = loadIndex();
  const queryTokens = tokenize(query);

  if (queryTokens.length === 0) {
    return getRecentCorrections(limit);
  }

  // Score each correction by keyword overlap + recency
  const scores = {};
  for (const token of queryTokens) {
    const entries = index[token] || [];
    for (const entry of entries) {
      if (!scores[entry.id]) scores[entry.id] = { relevance: 0, recency: 0 };
      scores[entry.id].relevance += 1;
    }
  }

  // Add recency bonus (corrections from last 7 days get a boost)
  const now = Date.now();
  const weekMs = 7 * 24 * 60 * 60 * 1000;
  for (const corr of corrections) {
    if (scores[corr.id]) {
      const age = now - new Date(corr.timestamp).getTime();
      scores[corr.id].recency = age < weekMs ? 0.5 : 0;
    }
  }

  // Rank by combined score
  const ranked = Object.entries(scores)    .map(([id, s]) => ({
      id,
      score: (s.relevance / queryTokens.length) + s.recency
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);

  // Fetch full corrections
  const corrMap = Object.fromEntries(corrections.map(c => [c.id, c]));
  return ranked
    .map(r => {
      const corr = corrMap[r.id];
      if (!corr) return null;
      return { ...formatCorrection(corr), relevance_score: r.score.toFixed(2) };
    })
    .filter(Boolean);
}

/**
 * Get pattern frequency statistics.
 */
export function getPatternStats() {
  const stats = loadStats();
  const corrections = loadCorrections();

  // Enrich with promotion status
  const enriched = {};
  for (const [name, data] of Object.entries(stats.patterns)) {
    enriched[name] = {
      ...data,      promoted: data.count >= 3 && data.sessions.length >= 2,
      promotion_status: data.count >= 3 && data.sessions.length >= 2
        ? 'HARD RULE — promoted to operator-instinct.md'
        : data.count >= 2
          ? `${3 - data.count} more occurrence(s) needed for promotion`
          : 'monitoring'
    };
  }

  return {
    total_corrections: stats.total || corrections.length,
    last_updated: stats.lastUpdated,
    patterns: enriched
  };
}

/**
 * Format a correction for display (strips internal fields).
 */
function formatCorrection(corr) {
  return {
    id: corr.id,
    timestamp: corr.timestamp,
    pattern_id: corr.pattern_id,
    pattern_name: corr.pattern_name,
    context: corr.context,
    what_model_did: corr.what_model_did,
    what_operator_wanted: corr.what_operator_wanted,
    operator_exact_words: corr.operator_exact_words,
    detection_rule: corr.detection_rule,    severity: corr.severity
  };
}

/**
 * Seed corrections from a JSON file (for initial setup).
 */
export async function seedFromFile(filePath) {
  const data = JSON.parse(readFileSync(filePath, 'utf-8'));
  let count = 0;
  for (const corr of data) {
    logCorrection(corr);
    count++;
  }
  console.log(`Seeded ${count} corrections.`);
  return count;
}

export default {
  logCorrection,
  getRecentCorrections,
  getRelevantCorrections,
  getPatternStats,
  seedFromFile
};