#!/usr/bin/env node

/**
 * Null Systems Correction Server — MCP Server
 *
 * Provides RAG-style correction retrieval for Claude Code instances.
 * Every session starts with accumulated wisdom from all past sessions.
 *
 * Tools (v8 — Corrections):
 *   get_recent_corrections  — Load recent corrections at session start
 *   get_relevant_corrections — Query corrections relevant to current task
 *   log_correction          — Record a new correction mid-session
 *   get_pattern_stats       — View pattern frequency and promotion status
 *   index_session           — Import corrections from a JSONL transcript
 *
 * Tools (v9 — Predictions & Learning Loop):
 *   log_prediction          — Record a prediction before acting/presenting options
 *   log_outcome             — Record Mika's actual response after a prediction
 *   get_residuals           — View current accuracy and residuals by category
 *   get_learning_phase      — Check learning phase for a category
 *   trigger_reality_check   — Force assumption validation (anti-hallucination)
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import {
  getRecentCorrections,
  getRelevantCorrections,
  logCorrection,
  getPatternStats,
} from './corrections-store.js';

import { indexSession, indexDirectory } from './session-parser.js';

import {
  logPrediction,
  logOutcome,
  getResiduals,
  getLearningPhase,
  triggerRealityCheck,
  incrementSessionCounters,
} from './predictions.js';

// ── Server Setup ───────────────────────────────────────────────────────────

const server = new Server(
  { name: 'null-systems-corrections', version: '1.0.0' },
  { capabilities: { tools: {} } }
);

// ── Tool Definitions ───────────────────────────────────────────────────────

server.setRequestHandler(ListToolsRequestSchema, async () => ({  tools: [
    {
      name: 'get_recent_corrections',
      description:
        'Get the most recent corrections from past sessions. Call this at the START of every session to load context. Returns corrections newest-first with pattern names, what went wrong, and detection rules.',
      inputSchema: {
        type: 'object',
        properties: {
          limit: {
            type: 'number',
            description: 'Number of corrections to return (default: 20)',
            default: 20,
          },
        },
      },
    },
    {
      name: 'get_relevant_corrections',
      description:
        'Search for corrections relevant to your current task. Call this BEFORE major actions (deploying, testing, reporting results, etc.) to check if past sessions had corrections for similar situations. Query with keywords describing what you are about to do.',
      inputSchema: {
        type: 'object',
        properties: {
          query: {
            type: 'string',
            description:
              'Keywords describing the current task/action (e.g., "deploying to production", "running full batch test", "reporting results to Mika")',
          },          limit: {
            type: 'number',
            description: 'Max corrections to return (default: 10)',
            default: 10,
          },
        },
        required: ['query'],
      },
    },
    {
      name: 'log_correction',
      description:
        'Record a correction that Mika just gave. Call this whenever you detect that Mika\'s message is correcting something you did wrong (not a new instruction). The correction is indexed permanently and will be served to future sessions.',
      inputSchema: {
        type: 'object',
        properties: {
          pattern_name: {
            type: 'string',
            description:
              'Name of the anti-pattern (e.g., "permission-seeking", "memory-neglect", "premature-victory", or a new pattern name)',
          },
          pattern_id: {
            type: 'number',
            description:
              'Pattern number (1-8 for known patterns, 0 for new/unknown)',
          },
          context: {
            type: 'string',
            description: 'What you were doing when the correction happened',
          },          what_model_did: {
            type: 'string',
            description: 'The specific action or output Mika is correcting',
          },
          what_mika_wanted: {
            type: 'string',
            description: 'What Mika wanted instead',
          },
          mika_exact_words: {
            type: 'string',
            description: "Mika's exact words (the correction message)",
          },
          detection_rule: {
            type: 'string',
            description:
              'A rule that would catch this in the future (written as an if-then)',
          },
          severity: {
            type: 'string',
            enum: ['low', 'medium', 'high'],
            description: 'How significant this correction is',
          },
        },
        required: [
          'pattern_name',
          'context',
          'what_model_did',
          'what_mika_wanted',
          'mika_exact_words',
        ],      },
    },
    {
      name: 'get_pattern_stats',
      description:
        'Get frequency statistics for all correction patterns. Shows which patterns recur most, how many sessions they appear in, and whether they have been promoted to hard rules. Use this for self-monitoring and to identify persistent behavioral issues.',
      inputSchema: {
        type: 'object',
        properties: {},
      },
    },
    {
      name: 'index_session',
      description:
        'Parse a Claude Code JSONL session transcript and extract corrections automatically. Use this to batch-import corrections from past sessions. Can also index an entire directory of transcripts.',
      inputSchema: {
        type: 'object',
        properties: {
          path: {
            type: 'string',
            description:
              'Path to a .jsonl session file OR a directory containing .jsonl files',
          },
        },
        required: ['path'],
      },
    },

    // ── v9 Prediction & Learning Loop Tools ─────────────────────────────
    {
      name: 'log_prediction',
      description:
        'Record a prediction before acting or presenting options. Every non-trivial decision should be logged. The prediction MUST cite an evidence source (past correction, stated preference, session event). Unsourced predictions get capped at 50% confidence.',
      inputSchema: {
        type: 'object',
        properties: {
          category: {
            type: 'string',
            description: 'Decision category (e.g., "build-approach", "strategic-priority", "communication-style", "deploy-strategy")',
          },
          situation: {
            type: 'string',
            description: 'Description of the decision point',
          },
          prediction: {
            type: 'string',
            description: 'What you predict Mika would choose/want',
          },
          confidence: {
            type: 'number',
            description: 'Confidence 0.0-1.0. Capped at 0.5 if no evidence_source.',
          },
          evidence_source: {
            type: 'string',
            description: 'Citation: correction ID, session reference, or stated Mika preference that supports this prediction',
          },
          alternatives: {            type: 'array',
            items: { type: 'string' },
            description: 'Other options considered',
          },
        },
        required: ['category', 'situation', 'prediction'],
      },
    },
    {
      name: 'log_outcome',
      description:
        'Record what Mika actually chose/said after a prediction was made. This updates residuals and may trigger phase transitions. Outcome types: explicit_confirm (strong learning), no_correction (weak learning), correction (residual grows), redirect (residual grows fast), frustration (maximum residual growth).',
      inputSchema: {
        type: 'object',
        properties: {
          prediction_id: {
            type: 'string',
            description: 'The prediction ID returned by log_prediction',
          },
          actual: {
            type: 'string',
            description: 'What Mika actually chose or wanted',
          },
          outcome_type: {
            type: 'string',
            enum: ['explicit_confirm', 'no_correction', 'correction', 'redirect', 'frustration'],
            description: 'How Mika responded',
          },
          mika_words: {
            type: 'string',            description: "Mika's exact words (if applicable)",
          },
        },
        required: ['prediction_id', 'actual', 'outcome_type'],
      },
    },
    {
      name: 'get_residuals',
      description:
        'Get current prediction accuracy and residual scores for all categories. Shows learning phase, decay status, convergence risk, and whether a reality check is due. Call at session start after loading corrections.',
      inputSchema: {
        type: 'object',
        properties: {},
      },
    },
    {
      name: 'get_learning_phase',
      description:
        'Get the current learning phase for a specific decision category. Phases: ACTIVE (present options), GUIDED (options when unsure), AUTONOMOUS (act silently). Also shows phase history and decay status.',
      inputSchema: {
        type: 'object',
        properties: {
          category: {
            type: 'string',
            description: 'The decision category to check',
          },
        },
        required: ['category'],
      },
    },    {
      name: 'trigger_reality_check',
      description:
        'Force a reality check — surfaces top assumptions that need Mika\'s explicit validation. Use this every 5 sessions OR when 3+ sessions pass without any corrections (to catch self-affirming loops). Returns assumptions ranked by risk.',
      inputSchema: {
        type: 'object',
        properties: {},
      },
    },
  ],
}));

// ── Tool Execution ─────────────────────────────────────────────────────────

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'get_recent_corrections': {
        const limit = args?.limit ?? 20;
        const corrections = getRecentCorrections(limit);
        return {
          content: [
            {
              type: 'text',
              text: corrections.length === 0
                ? 'No corrections logged yet. This is either a fresh install or all previous sessions were correction-free.'
                : JSON.stringify(corrections, null, 2),            },
          ],
        };
      }

      case 'get_relevant_corrections': {
        const query = args?.query ?? '';
        const limit = args?.limit ?? 10;
        const corrections = getRelevantCorrections(query, limit);
        return {
          content: [
            {
              type: 'text',
              text: corrections.length === 0
                ? `No corrections found matching "${query}". Proceeding without historical context for this action.`
                : JSON.stringify(corrections, null, 2),
            },
          ],
        };
      }

      case 'log_correction': {
        const result = logCorrection({
          pattern_id: args?.pattern_id ?? 0,
          pattern_name: args?.pattern_name,
          context: args?.context,
          what_model_did: args?.what_model_did,
          what_mika_wanted: args?.what_mika_wanted,
          mika_exact_words: args?.mika_exact_words,
          detection_rule: args?.detection_rule ?? '',          severity: args?.severity ?? 'medium',
          session_id: process.env.SESSION_ID || 'unknown',
        });
        return {
          content: [
            {
              type: 'text',
              text: `Correction logged: ${result.id}\nTotal corrections: ${result.total_corrections}\nThis pattern (${args?.pattern_name}) has occurred ${result.pattern_count} time(s) across ${result.pattern_sessions} session(s).${
                result.pattern_count >= 3 && result.pattern_sessions >= 2
                  ? '\n⚠️  PROMOTED TO HARD RULE — this pattern has crossed the promotion threshold.'
                  : ''
              }`,
            },
          ],
        };
      }

      case 'get_pattern_stats': {
        const stats = getPatternStats();
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(stats, null, 2),
            },
          ],
        };
      }

      case 'index_session': {
        const path = args?.path;        if (!path) {
          return {
            content: [{ type: 'text', text: 'Error: path is required' }],
            isError: true,
          };
        }

        let result;
        if (path.endsWith('.jsonl')) {
          result = indexSession(path);
        } else {
          result = indexDirectory(path);
        }
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(result, null, 2),
            },
          ],
        };
      }

      // ── v9 Prediction & Learning Loop Handlers ───────────────────────

      case 'log_prediction': {
        const result = logPrediction({
          category: args?.category,
          situation: args?.situation,
          prediction: args?.prediction,          confidence: args?.confidence,
          evidence_source: args?.evidence_source,
          alternatives: args?.alternatives || [],
          session_id: process.env.SESSION_ID || 'unknown',
        });
        return {
          content: [{
            type: 'text',
            text: `Prediction logged: ${result.prediction_id}\nConfidence: ${result.confidence}${result.confidence_capped ? ' (CAPPED — no evidence source provided)' : ''}\nCategory phase: ${result.phase}`,
          }],
        };
      }

      case 'log_outcome': {
        const result = logOutcome({
          prediction_id: args?.prediction_id,
          actual: args?.actual,
          outcome_type: args?.outcome_type,
          mika_words: args?.mika_words || '',
        });
        if (result.error) {
          return { content: [{ type: 'text', text: `Error: ${result.error}` }], isError: true };
        }
        return {
          content: [{
            type: 'text',
            text: `Outcome logged for ${result.prediction_id}\nPrediction correct: ${result.prediction_correct}\nOutcome: ${result.outcome_type}\nResidual change: ${result.residual_change > 0 ? '+' : ''}${result.residual_change}\nCategory: ${result.category} — ${result.category_accuracy} accuracy — Phase: ${result.category_phase}${result.phase_changed ? `\n⚠️  PHASE ${result.phase_direction}` : ''}`,
          }],
        };
      }
      case 'get_residuals': {
        incrementSessionCounters(); // Track session age
        const residuals = getResiduals();
        return {
          content: [{
            type: 'text',
            text: JSON.stringify(residuals, null, 2),
          }],
        };
      }

      case 'get_learning_phase': {
        const phase = getLearningPhase(args?.category);
        return {
          content: [{
            type: 'text',
            text: JSON.stringify(phase, null, 2),
          }],
        };
      }

      case 'trigger_reality_check': {
        const check = triggerRealityCheck();
        return {
          content: [{
            type: 'text',
            text: JSON.stringify(check, null, 2),
          }],
        };
      }
      default:
        return {
          content: [{ type: 'text', text: `Unknown tool: ${name}` }],
          isError: true,
        };
    }
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: `Error executing ${name}: ${error.message}`,
        },
      ],
      isError: true,
    };
  }
});

// ── Start Server ───────────────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('Null Systems Correction Server running on stdio');
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});