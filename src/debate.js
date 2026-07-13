// Debate Chamber — Advocate vs Skeptic (2 rounds) → Judge (strict JSON verdict)
// All AI calls via CF Workers AI (@cf/meta/llama-3.3-70b-instruct-fp8-fast)
// Memory: CF KV + continuous learning from real outcomes

import { loadLearningContext, learningPrompt, recordOutcome } from './learning.js';

const CF_MODEL    = '@cf/meta/llama-3.3-70b-instruct-fp8-fast';
const MAX_RETRIES = 4;
const CALIBRATION_MAX = 8;

const CANDIDATE_PROFILE = `Name: Ashiq (Cypher)
Positioning: Web3 Growth, Social & Content Operator | AI Operations Specialist
Location: Kashmir, India (remote-first)
Verified metrics: 16,000+ followers grown organically; built & managed a 6,000+ member community
Core skills: community building & moderation, content creation, social media management,
  AI data annotation & QA, prompt engineering, chatbot testing, workflow automation,
  multi-agent AI pipelines
Languages: English, Hindi, Urdu, Kashmiri (multilingual data/localization work)
Target roles: community manager/mod, content & social ops, growth, AI model evaluation,
  data annotation, localization, ambassador/KOL programs
Constraints: remote roles preferred; paid roles prioritized over unpaid ambassador gigs`;

// ── CF Workers AI ─────────────────────────────────────────────────────────────

async function callCF(env, system, messages, maxTokens = 1200) {
  // Prefer direct AI binding (no API key needed, faster, always available)
  if (env.AI) {
    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      try {
        const result = await env.AI.run(CF_MODEL, {
          messages: [{ role: 'system', content: system }, ...messages],
          max_tokens: maxTokens,
        });
        return result?.response?.trim() ?? '';
      } catch (e) {
        if (attempt < MAX_RETRIES - 1) await new Promise(r => setTimeout(r, (2 ** attempt) * 500));
      }
    }
    return '';
  }
  // Fallback: external API (requires CF_GLOBAL_KEY secret)
  if (!env.CF_GLOBAL_KEY) return '';
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      const r = await fetch(
        `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/ai/run/${CF_MODEL}`,
        {
          method: 'POST',
          headers: { 'X-Auth-Email': env.CF_EMAIL, 'X-Auth-Key': env.CF_GLOBAL_KEY, 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: [{ role: 'system', content: system }, ...messages], max_tokens: maxTokens }),
        }
      );
      if (r.ok) {
        const d = await r.json();
        return d.result?.choices?.[0]?.message?.content?.trim() ?? d.result?.response?.trim() ?? '';
      }
      if (r.status === 429) {
        await new Promise(res => setTimeout(res, Math.min((2 ** attempt) * 1000 + Math.random() * 500, 30000)));
        continue;
      }
    } catch { /* retry */ }
  }
  return '';
}

function extractJson(text) {
  if (!text) return null;
  const clean = text.replace(/```(?:json)?/g, '').trim().replace(/^`+|`+$/g, '');
  const s = clean.indexOf('{'), e = clean.lastIndexOf('}') + 1;
  if (s < 0 || e <= s) return null;
  try { return JSON.parse(clean.slice(s, e)); } catch { return null; }
}

// ── CF KV memory ──────────────────────────────────────────────────────────────

async function loadOutcomes(env) {
  try { return JSON.parse(await env.KV.get('debate_outcomes') || '[]'); } catch { return []; }
}

async function loadVerdicts(env) {
  try { return JSON.parse(await env.KV.get('debate_verdicts') || '[]'); } catch { return []; }
}

async function saveVerdicts(env, verdicts) {
  const existing = await loadVerdicts(env);
  await env.KV.put('debate_verdicts', JSON.stringify([...existing, ...verdicts].slice(-200)));
}

export async function logOutcome(env, leadId, outcome) {
  // Write to both legacy key and the new learning engine
  const outcomes = await loadOutcomes(env);
  outcomes.push({ lead_id: leadId, outcome, logged_at: new Date().toISOString() });
  await env.KV.put('debate_outcomes', JSON.stringify(outcomes.slice(-200)));
  await recordOutcome(env, leadId, outcome, {});
}

async function loadCalibration(env) {
  const outcomes = await loadOutcomes(env);
  if (!outcomes.length) return '';
  const verdicts = await loadVerdicts(env);
  const byId = Object.fromEntries(verdicts.map(v => [v.lead_id, v]));
  const examples = outcomes
    .filter(o => byId[o.lead_id])
    .map(o => {
      const v = byId[o.lead_id];
      return `- Project: ${v.project} | Role: ${v.title} | Scored ${v.score} (${v.verdict}) | REAL OUTCOME: ${o.outcome}`;
    })
    .slice(-CALIBRATION_MAX);
  if (!examples.length) return '';
  return `\n\nCALIBRATION FROM REAL OUTCOMES (adjust scoring so high scores predict replies/interviews):\n${examples.join('\n')}`;
}

// ── Agent prompts ─────────────────────────────────────────────────────────────

const ADVOCATE_SYSTEM = `You are the ADVOCATE in a hiring-fit debate chamber.
Make the strongest honest case that this candidate should apply to this lead.

Candidate profile:
${CANDIDATE_PROFILE}

Rules:
- Argue from SPECIFIC evidence in the lead and dossier, not generic hype.
- Identify the single sharpest angle — what in the candidate's profile this project most needs.
- Be honest: a weak case signals weak fit. Max 200 words.`;

const SKEPTIC_SYSTEM = `You are the SKEPTIC in a hiring-fit debate chamber.
Make the strongest honest case AGAINST applying — poor fit, red flags, low pay probability, dead project, scam signals.

Candidate profile:
${CANDIDATE_PROFILE}

Rules:
- Attack from SPECIFIC evidence: vague posts, no funding, anonymous team, botted engagement, unpaid ambassador patterns.
- The candidate's time is scarce. Every weak application has opportunity cost.
- Be honest: if genuinely strong, concede and focus on real residual risks. Max 200 words.`;

const REBUTTAL_INSTRUCTION = `Write your REBUTTAL. Directly respond to your opponent's specific points — reference at least two of their claims and counter or concede each. No new generic arguments. Max 150 words.`;

function judgeSystem(calibration) {
  return `You are the JUDGE in a hiring-fit debate chamber. You have read a 2-round debate.

Candidate profile:
${CANDIDATE_PROFILE}

Scoring rubric:
9-10: exceptional fit + credible project + clear paid role. Apply immediately.
7-8: strong fit, minor unknowns. Apply.
5-6: plausible but weak signal or notable risk. Watch list.
3-4: poor fit or serious red flags. Skip.
1-2: scam signals or dead project. Skip and blacklist.

Weigh the Skeptic's concessions and Advocate's specificity heavily.${calibration}

Respond with ONLY a valid JSON object, no extra text:
{"score":<int 1-10>,"verdict":"apply"|"watch"|"skip","angle":"<one sentence or empty>","risks":["<risk1>","<risk2>"],"reasoning":"<2 sentences max>"}`;
}

// ── The debate ────────────────────────────────────────────────────────────────

function leadBlock(lead) {
  return `LEAD:\nTitle: ${lead.title}\nProject: ${lead.project}\nSource: ${lead.source || 'x.com'}\n\nPosting:\n${lead.description}\n\nResearch dossier:\n${lead.dossier || '(no dossier — argue from posting alone)'}`;
}

export async function runDebate(env, lead) {
  const lb = leadBlock(lead);

  // Round 1: openings in parallel
  const [advOpen, skeOpen] = await Promise.all([
    callCF(env, ADVOCATE_SYSTEM, [{ role: 'user', content: lb + '\n\nWrite your OPENING argument.' }]),
    callCF(env, SKEPTIC_SYSTEM,  [{ role: 'user', content: lb + '\n\nWrite your OPENING argument.' }]),
  ]);

  // Round 2: rebuttals in parallel (each sees opponent's opening)
  const [advRebut, skeRebut] = await Promise.all([
    callCF(env, ADVOCATE_SYSTEM, [
      { role: 'user',      content: lb + '\n\nWrite your OPENING argument.' },
      { role: 'assistant', content: advOpen },
      { role: 'user',      content: `Opponent (Skeptic) argued:\n${skeOpen}\n\n${REBUTTAL_INSTRUCTION}` },
    ]),
    callCF(env, SKEPTIC_SYSTEM, [
      { role: 'user',      content: lb + '\n\nWrite your OPENING argument.' },
      { role: 'assistant', content: skeOpen },
      { role: 'user',      content: `Opponent (Advocate) argued:\n${advOpen}\n\n${REBUTTAL_INSTRUCTION}` },
    ]),
  ]);

  const transcript = [
    `=== ADVOCATE OPENING ===\n${advOpen}`,
    `=== SKEPTIC OPENING ===\n${skeOpen}`,
    `=== ADVOCATE REBUTTAL ===\n${advRebut}`,
    `=== SKEPTIC REBUTTAL ===\n${skeRebut}`,
  ].join('\n\n');

  const [calibration, lCtx] = await Promise.all([loadCalibration(env), loadLearningContext(env)]);
  const lLine = learningPrompt(lCtx);
  const judgeRaw = await callCF(
    env, judgeSystem(calibration + (lLine ? '\n\n' + lLine : '')),
    [{ role: 'user', content: lb + '\n\nDEBATE TRANSCRIPT:\n' + transcript }],
  );

  const j = extractJson(judgeRaw);
  if (!j) return null;

  const score   = parseInt(j.score, 10);
  const verdict = String(j.verdict || '').toLowerCase();
  if (!(score >= 1 && score <= 10) || !['apply', 'watch', 'skip'].includes(verdict)) return null;

  return {
    lead_id:   lead.lead_id || lead.company,
    project:   lead.project || lead.company,
    title:     lead.title,
    score, verdict,
    angle:     j.angle     || '',
    risks:     j.risks     || [],
    reasoning: j.reasoning || '',
    transcript,
    judged_at: new Date().toISOString(),
  };
}

export async function judgeLeads(env, leads) {
  const results = await Promise.all(leads.map(async lead => {
    try { return await runDebate(env, lead); } catch { return null; }
  }));
  const verdicts = results.filter(Boolean);
  if (verdicts.length) await saveVerdicts(env, verdicts);
  return {
    apply: verdicts.filter(v => v.verdict === 'apply').sort((a, b) => b.score - a.score),
    watch: verdicts.filter(v => v.verdict === 'watch'),
    skip:  verdicts.filter(v => v.verdict === 'skip'),
  };
}
