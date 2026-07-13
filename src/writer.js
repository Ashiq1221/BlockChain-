// Writer Squad — Writer → Critic → Editor per lead
// All AI via CF Workers AI; style memory, drafts, and learning context in CF KV

import { loadLearningContext, learningPrompt } from './learning.js';

const CF_MODEL = '@cf/meta/llama-3.3-70b-instruct-fp8-fast';

const CANDIDATE_PROFILE = `Name: Ashiq (Cypher)
Positioning: Web3 Growth, Social & Content Operator | AI Operations Specialist
Verified metrics: 16,000+ followers grown organically; built & managed a 6,000+ member community
Core skills: community building & moderation, content creation, social media management,
  AI data annotation & QA, prompt engineering, workflow automation, multi-agent AI pipelines
Languages: English, Hindi, Urdu, Kashmiri
Portfolio: available on request`;

async function callCF(env, system, messages, maxTokens = 1200) {
  if (env.AI) {
    try {
      const result = await env.AI.run(CF_MODEL, {
        messages: [{ role: 'system', content: system }, ...messages],
        max_tokens: maxTokens,
      });
      return result?.response?.trim() ?? '';
    } catch { /* fall through */ }
  }
  if (!env.CF_GLOBAL_KEY) return '';
  try {
    const r = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/ai/run/${CF_MODEL}`,
      {
        method: 'POST',
        headers: { 'X-Auth-Email': env.CF_EMAIL, 'X-Auth-Key': env.CF_GLOBAL_KEY, 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: [{ role: 'system', content: system }, ...messages], max_tokens: maxTokens }),
      }
    );
    if (!r.ok) return '';
    const d = await r.json();
    return d.result?.choices?.[0]?.message?.content?.trim() ?? d.result?.response?.trim() ?? '';
  } catch { return ''; }
}

// ── Style memory: winning drafts teach the Writer ─────────────────────────────

async function loadStyleMemory(env) {
  try {
    const outcomes = JSON.parse(await env.KV.get('draft_outcomes') || '[]');
    const drafts   = JSON.parse(await env.KV.get('drafts') || '{}');
    const winners  = [], losers = [];
    for (const o of outcomes.slice(-20)) {
      const draft = drafts[o.lead_id];
      if (!draft) continue;
      if (o.outcome === 'replied' || o.outcome === 'interview') winners.push(`--- WON A ${o.outcome.toUpperCase()} ---\n${draft.slice(0, 900)}`);
      else if (o.outcome === 'ignored') losers.push(draft.slice(0, 300));
    }
    const parts = [];
    if (winners.length) parts.push(`STYLE EXAMPLES THAT GOT REPLIES (emulate tone/structure):\n${winners.slice(-3).join('\n\n')}`);
    if (losers.length)  parts.push(`RECENT DRAFTS THAT GOT IGNORED (avoid what these did):\n${losers.slice(-2).join('\n---\n')}`);
    return parts.length ? '\n\n' + parts.join('\n\n') : '';
  } catch { return ''; }
}

export async function logDraftOutcome(env, leadId, outcome) {
  const outcomes = JSON.parse(await env.KV.get('draft_outcomes') || '[]');
  outcomes.push({ lead_id: leadId, outcome, logged_at: new Date().toISOString() });
  await env.KV.put('draft_outcomes', JSON.stringify(outcomes.slice(-200)));
}

// ── Draft pipeline: Writer → Critic → Editor ─────────────────────────────────

export async function draftApplication(env, verdict) {
  const [styleMemory, lCtx] = await Promise.all([loadStyleMemory(env), loadLearningContext(env)]);
  const lLine = learningPrompt(lCtx);

  const WRITER_SYSTEM = `You are the WRITER. Produce two artifacts for this job lead:

1. APPLICATION (150-250 words): tailored to the role, leads with the Judge's angle, cites the candidate's verified metrics, references something SPECIFIC about the project from the dossier. No generic filler.
2. FOUNDER DM (under 60 words): casual-professional, one specific hook about their project, one credential, one clear ask. Written to be sent from the candidate's own account personally.

Candidate profile:
${CANDIDATE_PROFILE}${styleMemory}${lLine ? '\n\n' + lLine : ''}

Format your response exactly as:
## APPLICATION
<text>
## DM
<text>`;

  const CRITIC_SYSTEM = `You are the CRITIC. Tear this draft apart on:
- Generic phrases a founder has read 100 times
- Claims not backed by the profile
- Missing the assigned angle
- DM over 60 words or with no specific hook
- Anything that smells like a template
List concrete fixes. Max 120 words. If genuinely strong, say so and name the 1-2 weakest lines.`;

  const EDITOR_SYSTEM = `You are the EDITOR. Apply the Critic's fixes and output the FINAL version in exactly this format, nothing else:
## APPLICATION
<text>
## DM
<text>`;

  const brief = [
    `ROLE: ${verdict.title} at ${verdict.project}`,
    `JUDGE'S ANGLE: ${verdict.angle || ''}`,
    `KNOWN RISKS: ${(verdict.risks || []).join(', ')}`,
    `FOUNDER HANDLES: ${(verdict.founder_handles || []).join(', ') || 'see dossier'}`,
    `\nDEBATE HIGHLIGHTS:\n${(verdict.transcript || '').slice(0, 2000)}`,
  ].join('\n');

  const draft    = await callCF(env, WRITER_SYSTEM, [{ role: 'user', content: brief }]);
  if (!draft) return null;
  const critique = await callCF(env, CRITIC_SYSTEM,  [{ role: 'user', content: `BRIEF:\n${brief}\n\nDRAFT:\n${draft}` }]);
  const final    = await callCF(env, EDITOR_SYSTEM,  [{ role: 'user', content: `BRIEF:\n${brief}\n\nDRAFT:\n${draft}\n\nCRITIQUE:\n${critique}` }]);

  const doc = [`# ${verdict.project} — ${verdict.title}`,
    `Score: ${verdict.score}/10 | Angle: ${verdict.angle || ''}`,
    `Contacts: ${(verdict.founder_handles || []).join(', ') || 'check dossier'}`,
    '', final || draft, '', `---\nCritic's notes:\n${critique}`].join('\n');

  const drafts = JSON.parse(await env.KV.get('drafts') || '{}');
  drafts[verdict.lead_id] = doc;
  const keys = Object.keys(drafts);
  if (keys.length > 100) delete drafts[keys[0]];
  await env.KV.put('drafts', JSON.stringify(drafts));

  const appMatch = (final || draft).match(/## APPLICATION\s*([\s\S]*?)(?=## DM|$)/);
  const dmMatch  = (final || draft).match(/## DM\s*([\s\S]*?)$/);

  return {
    lead_id: verdict.lead_id, project: verdict.project, title: verdict.title,
    score: verdict.score, angle: verdict.angle || '', risks: verdict.risks || [],
    founder_handles: verdict.founder_handles || [],
    application: appMatch?.[1]?.trim() || final || draft,
    dm: dmMatch?.[1]?.trim() || '',
    doc,
  };
}

export async function draftBatch(env, verdicts) {
  if (!verdicts.length) return [];
  const queue = verdicts.filter(v => v.verdict === 'apply').sort((a, b) => b.score - a.score);
  const results = await Promise.all(queue.map(v => draftApplication(env, v).catch(() => null)));
  return results.filter(Boolean);
}

// ── Learning report ───────────────────────────────────────────────────────────

export async function learningReport(env) {
  const verdicts = JSON.parse(await env.KV.get('debate_verdicts') || '[]');
  const outcomes = [
    ...JSON.parse(await env.KV.get('debate_outcomes') || '[]'),
    ...JSON.parse(await env.KV.get('draft_outcomes')  || '[]'),
  ];
  if (!outcomes.length) return { report: 'No outcomes logged yet.', by_band: {} };
  const byId = Object.fromEntries(verdicts.map(v => [v.lead_id, v]));
  const byBand = {};
  for (const o of outcomes) {
    const v = byId[o.lead_id];
    if (!v) continue;
    const band = `${v.score}`;
    if (!byBand[band]) byBand[band] = { sent: 0, won: 0 };
    byBand[band].sent++;
    if (['replied','interview','hired'].includes(o.outcome)) byBand[band].won++;
  }
  const totalSent = Object.values(byBand).reduce((s, b) => s + b.sent, 0);
  const totalWon  = Object.values(byBand).reduce((s, b) => s + b.won, 0);
  return {
    by_band: Object.fromEntries(
      Object.entries(byBand).sort(([a],[b]) => +b - +a).map(([band, s]) => [
        `${band}/10`, { ...s, reply_rate: `${s.sent ? Math.round(s.won/s.sent*100) : 0}%` }
      ])
    ),
    overall: { sent: totalSent, won: totalWon, reply_rate: `${totalSent ? Math.round(totalWon/totalSent*100) : 0}%` },
  };
}

export async function getQueue(env) {
  const verdicts = JSON.parse(await env.KV.get('debate_verdicts') || '[]');
  const drafts   = JSON.parse(await env.KV.get('drafts') || '{}');
  const seen = new Set();
  const queue = [];
  for (const v of verdicts) {
    if (v.verdict === 'apply' && !seen.has(v.lead_id)) {
      seen.add(v.lead_id);
      queue.push({ score: v.score, project: v.project, title: v.title, lead_id: v.lead_id,
        angle: v.angle, drafted: !!drafts[v.lead_id], judged_at: v.judged_at });
    }
  }
  return queue.sort((a, b) => b.score - a.score);
}
