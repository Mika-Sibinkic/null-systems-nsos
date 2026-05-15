/**
 * Session Parser — Extracts corrections from Claude Code JSONL session transcripts.
 *
 * Reads JSONL files, identifies user messages that are corrections (not new instructions),
 * and feeds them into the corrections store.
 */

import { readFileSync, readdirSync, existsSync } from 'fs';
import { join, basename } from 'path';
import { logCorrection } from './corrections-store.js';

// ── Correction Detection Heuristics ────────────────────────────────────────

const FRUSTRATION_MARKERS = [
  /\b(obviously|just do it|why are you asking|i already said|i told you)\b/i,
  /^(yes|no|go|fine|ok|sure|yep|yeah|correct|right)\s*[.!]?\s*$/i,
  /[A-Z]{3,}/,  // ALL CAPS words (3+ chars)
];

const PERMISSION_RESPONSES = [
  /^(go ahead|yes|do it|proceed|sure|yep|yeah|go for it)\s*[.!]?\s*$/i,
  /^(yes|yeah|yep),?\s+(go ahead|do it|please|just do it)/i,
];

const MEMORY_PROMPTS = [
  /\b(is the log updated|did you save|update the|checkpoint|memory)\b/i,
  /\b(did you log|have you updated|is .+ current)\b/i,
];

const COMPREHENSION_TESTS = [
  /\bwhat (is|are) left\b/i,  /\bwhat('s| is) the status\b/i,
  /\bwhat('s| is) remaining\b/i,
  /\btell me .+ what\b/i,
];

const PREMATURE_VICTORY_SIGNALS = [
  /\b(is this real|actual production|full (batch|corpus|set))\b/i,
  /\b(all of them|every single|the whole)\b/i,
];

// ── Pattern Classification ─────────────────────────────────────────────────

/**
 * Classify a user message as a correction and identify the pattern.
 * Returns null if the message is not a correction.
 */
function classifyCorrection(userMsg, prevAssistantMsg) {
  const text = typeof userMsg === 'string' ? userMsg : JSON.stringify(userMsg);
  const trimmed = text.trim();

  // Very short response after a long assistant message = likely correction
  const assistantLength = typeof prevAssistantMsg === 'string' ? prevAssistantMsg.length : 0;
  const isShortResponse = trimmed.length < 50 && assistantLength > 500;

  // Check each pattern
  for (const regex of PERMISSION_RESPONSES) {
    if (regex.test(trimmed)) {
      return {
        pattern_id: 1,
        pattern_name: 'permission-seeking',        mika_exact_words: trimmed,
        detection_rule: 'If the action is the obvious next step and tests pass, execute without asking',
        severity: isShortResponse ? 'high' : 'medium'
      };
    }
  }

  for (const regex of MEMORY_PROMPTS) {
    if (regex.test(trimmed)) {
      return {
        pattern_id: 2,
        pattern_name: 'memory-neglect',
        mika_exact_words: trimmed,
        detection_rule: 'Update checkpoint.md after every deploy, test batch, or 30+ min of work',
        severity: 'medium'
      };
    }
  }

  for (const regex of PREMATURE_VICTORY_SIGNALS) {
    if (regex.test(trimmed)) {
      return {
        pattern_id: 4,
        pattern_name: 'premature-victory',
        mika_exact_words: trimmed,
        detection_rule: 'Label partial results as partial. Never claim full success on subset data.',
        severity: 'high'
      };
    }
  }
  for (const regex of COMPREHENSION_TESTS) {
    if (regex.test(trimmed)) {
      return {
        pattern_id: 7,
        pattern_name: 'incomplete-reporting',
        mika_exact_words: trimmed,
        detection_rule: 'Label every result with its status. Never present partial data as final.',
        severity: 'medium'
      };
    }
  }

  // Frustration signals (generic — try to identify which pattern from context)
  for (const regex of FRUSTRATION_MARKERS) {
    if (regex.test(trimmed) && isShortResponse) {
      return {
        pattern_id: 0,
        pattern_name: 'frustration-signal',
        mika_exact_words: trimmed,
        detection_rule: 'Frustration detected — review preceding action for anti-pattern match',
        severity: 'high'
      };
    }
  }

  return null;
}

// ── JSONL Session Parser ───────────────────────────────────────────────────
/**
 * Parse a JSONL session transcript and extract corrections.
 * Returns an array of correction objects ready for the store.
 */
export function parseSession(sessionPath) {
  if (!existsSync(sessionPath)) {
    throw new Error(`Session file not found: ${sessionPath}`);
  }

  const lines = readFileSync(sessionPath, 'utf-8').split('\n').filter(Boolean);
  const corrections = [];
  let prevAssistantContent = '';
  let prevAssistantContext = '';
  const sessionId = basename(sessionPath, '.jsonl');

  for (const line of lines) {
    let entry;
    try {
      entry = JSON.parse(line);
    } catch { continue; }

    // Track assistant messages for context
    if (entry.type === 'assistant' && entry.message?.content) {
      const content = entry.message.content;
      if (Array.isArray(content)) {
        // Extract text blocks from assistant content
        const textBlocks = content
          .filter(b => b.type === 'text')
          .map(b => b.text)
          .join('\n');        if (textBlocks) {
          prevAssistantContent = textBlocks;
          prevAssistantContext = textBlocks.substring(0, 200);
        }
      } else if (typeof content === 'string') {
        prevAssistantContent = content;
        prevAssistantContext = content.substring(0, 200);
      }
    }

    // Check user messages for corrections
    if (entry.type === 'user' && entry.userType === 'external') {
      const msgContent = entry.message?.content;
      const userText = typeof msgContent === 'string'
        ? msgContent
        : Array.isArray(msgContent)
          ? msgContent.filter(b => b.type === 'text').map(b => b.text).join('\n')
          : '';

      if (!userText) continue;

      const classification = classifyCorrection(userText, prevAssistantContent);
      if (classification) {
        corrections.push({
          ...classification,
          session_id: sessionId,
          timestamp: entry.timestamp || new Date().toISOString(),
          context: `Assistant was: ${prevAssistantContext}`,
          what_model_did: `(See assistant context above — model's last action before correction)`,
          what_mika_wanted: `(Inferred from correction: ${classification.detection_rule})`        });
      }
    }
  }

  return corrections;
}

/**
 * Parse and index a session, storing all found corrections.
 */
export function indexSession(sessionPath) {
  const corrections = parseSession(sessionPath);
  let stored = 0;
  for (const corr of corrections) {
    logCorrection(corr);
    stored++;
  }
  return {
    session: basename(sessionPath),
    corrections_found: corrections.length,
    corrections_stored: stored
  };
}

/**
 * Index all JSONL files in a directory.
 */
export function indexDirectory(dirPath) {
  if (!existsSync(dirPath)) {    throw new Error(`Directory not found: ${dirPath}`);
  }

  const files = readdirSync(dirPath).filter(f => f.endsWith('.jsonl'));
  const results = [];
  for (const file of files) {
    try {
      const result = indexSession(join(dirPath, file));
      results.push(result);
    } catch (err) {
      results.push({ session: file, error: err.message });
    }
  }
  return results;
}

/**
 * CLI entry point for indexing a session.
 */
export function indexSessionFromCLI() {
  const sessionPath = process.argv[2];
  if (!sessionPath) {
    console.error('Usage: node session-parser.js <path-to-session.jsonl>');
    process.exit(1);
  }
  const result = indexSession(sessionPath);
  console.log(JSON.stringify(result, null, 2));
}

export default { parseSession, indexSession, indexDirectory, indexSessionFromCLI };