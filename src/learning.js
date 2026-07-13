// Continuous Learning Engine
// Every application outcome is stored and fed back into agent decisions.
// KV keys: learn:outcomes, learn:styles

const OUTCOMES_KEY = 'learn:outcomes';
const STYLES_KEY   = 'learn:styles';

export async function loadLearningContext(env) {
  try {
    const [outcomeStr, styleStr] = await Promise.all([
      env.KV.get(OUTCOMES_KEY),
      env.KV.get(STYLES_KEY),
    ]);
    const outcomes = JSON.parse(outcomeStr || '{}');
    const styles   = JSON.parse(styleStr   || '[]');

    const arr    = Object.values(outcomes);
    const total  = arr.length;
    const positive = arr.filter(o => ['replied','interview','hired'].includes(o.outcome)).length;
    const scams  = arr.filter(o => o.outcome === 'scam').length;

    // Reply rate per score band (0-2, 2-4, … 8-10)
    const bands = {};
    for (const o of arr) {
      const b = Math.floor((o.score || 5) / 2) * 2;
      const key = `${b}-${b + 2}`;
      if (!bands[key]) bands[key] = { sent: 0, pos: 0 };
      bands[key].sent++;
      if (['replied','interview','hired'].includes(o.outcome)) bands[key].pos++;
    }
    const bandLines = Object.entries(bands)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `score ${k}: ${v.pos}/${v.sent} replies`)
      .join(' | ');

    // Best 5 opening lines from successful applications
    const winningOpenings = styles
      .filter(s => ['replied','interview','hired'].includes(s.outcome))
      .slice(-10)
      .map(s => s.opening)
      .filter(Boolean)
      .slice(-5);

    // Project sources that produced replies
    const goodSources = [...new Set(
      arr.filter(o => ['replied','interview','hired'].includes(o.outcome)).map(o => o.source)
    )].filter(Boolean);

    // Companies that ghosted 3+ times
    const ghostCounts = {};
    for (const o of arr.filter(o => o.outcome === 'ignored')) {
      const c = (o.company || '').toLowerCase();
      if (c) ghostCounts[c] = (ghostCounts[c] || 0) + 1;
    }
    const ghosted = Object.entries(ghostCounts).filter(([, n]) => n >= 3).map(([c]) => c);

    return {
      total_applied:     total,
      reply_rate_pct:    total > 5 ? ((positive / total) * 100).toFixed(1) : null,
      scam_count:        scams,
      score_band_stats:  bandLines || null,
      winning_openings:  winningOpenings,
      positive_sources:  goodSources,
      ghosted_companies: ghosted,
    };
  } catch { return {}; }
}

// One-line summary injected into every agent system prompt
export function learningPrompt(ctx) {
  if (!ctx?.total_applied) return '';
  const parts = [
    `[LEARNING: ${ctx.total_applied} sent` + (ctx.reply_rate_pct ? `, ${ctx.reply_rate_pct}% reply rate` : '') + ']',
    ctx.score_band_stats ? `Score performance: ${ctx.score_band_stats}.` : '',
    ctx.winning_openings?.length
      ? `Winning openings: ${ctx.winning_openings.map(o => `"${o.slice(0, 60)}"`).join(' / ')}.`
      : '',
    ctx.positive_sources?.length ? `Best sources: ${ctx.positive_sources.join(', ')}.` : '',
    ctx.ghosted_companies?.length ? `Low-priority (ghosted 3+x): ${ctx.ghosted_companies.join(', ')}.` : '',
  ];
  return parts.filter(Boolean).join('\n');
}

export async function recordOutcome(env, leadId, outcome, meta = {}) {
  try {
    const outcomes = JSON.parse(await env.KV.get(OUTCOMES_KEY) || '{}');
    outcomes[leadId] = { outcome, ts: Date.now(), ...meta };
    // Keep last 3000
    const keys = Object.keys(outcomes);
    if (keys.length > 3000) keys.slice(0, keys.length - 3000).forEach(k => delete outcomes[k]);
    await env.KV.put(OUTCOMES_KEY, JSON.stringify(outcomes));
  } catch { /* non-fatal */ }
}

export async function recordStyle(env, opening, outcome) {
  try {
    const styles = JSON.parse(await env.KV.get(STYLES_KEY) || '[]');
    styles.push({ opening: (opening || '').slice(0, 120), outcome, ts: Date.now() });
    await env.KV.put(STYLES_KEY, JSON.stringify(styles.slice(-500)));
  } catch { /* non-fatal */ }
}
