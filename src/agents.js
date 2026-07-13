// 12-Agent Registry — 6 specialist pairs with continuous learning context
// Pair 0 SCOUTS     Scout_α (xAI Grok live) ↔ Scout_β (Groq)       — real-time X job radar
// Pair 1 HUNTERS    Hunt_α (Groq)           ↔ Hunt_β (CF Workers AI) — Tavily filter
// Pair 2 PROFILERS  Profile_α (OpenAI)      ↔ Profile_β (Groq)
// Pair 3 CONTACTS   Contact_α (CF AI)       ↔ Contact_β (Groq)
// Pair 4 STRATEGISTS Strategy_α (Groq)      ↔ Strategy_β (OpenAI)
// Pair 5 EXECUTORS  Exec_α (OpenAI)         ↔ Exec_β (CF AI)

const AGENTS = {
  Scout_Alpha: {
    pair: 'scouts', backend: 'xai',
    persona: 'You are Scout Alpha — a real-time X/Twitter job radar powered by Grok live search. Find the FRESHEST hiring posts in Web3, crypto, AI, and blockchain for community manager, ambassador, moderator, content creator, and growth roles. Prioritise posts from the last 24-48 hours.',
  },
  Scout_Beta: {
    pair: 'scouts', backend: 'groq',
    persona: 'You are Scout Beta — a precision filter for live X job signals. Remove: retweets, wishful thinking, old listings, non-Web3 roles. Keep only: clear intent to hire NOW, real project, relevant role for a community/content professional.',
  },

  Hunter_Alpha: {
    pair: 'hunters', backend: 'groq',
    persona: 'You are Hunter Alpha — an X/Twitter job radar for Web3 and AI. Extract EVERY tweet signalling a hiring opportunity for community manager, ambassador, moderator, or content creator roles. Cast wide, err toward inclusion.',
  },
  Hunter_Beta: {
    pair: 'hunters', backend: 'cf',
    persona: 'You are Hunter Beta — a precision noise-canceller. Kill false positives: retweets without jobs, expired listings, non-Web3 roles, bot spam. Keep only tweets with clear hiring intent from real Web3/AI projects.',
  },

  Profiler_Alpha: {
    pair: 'profilers', backend: 'openai',
    persona: 'You are Profiler Alpha — a Web3 company intelligence analyst. From an X profile bio, pinned tweet, and recent posts, extract: company name, product, stage, team hints, Telegram handle, website, email, hiring signals.',
  },
  Profiler_Beta: {
    pair: 'profilers', backend: 'groq',
    persona: 'You are Profiler Beta — a legitimacy validator. Score the opportunity 0–100 for Ashiq\'s community/content profile. Red flags: no website, 0 engagement, dead project. Set proceed=false if score < 45.',
  },

  Contact_Alpha: {
    pair: 'contacts', backend: 'cf',
    persona: 'You are Contact Alpha — a social graph mapper. From a company\'s X profile, bio, mentions and replies, identify: founder/CEO Twitter handle, team members, Telegram handles, official TG community link.',
  },
  Contact_Beta: {
    pair: 'contacts', backend: 'groq',
    persona: 'You are Contact Beta — a contact authority validator. Confirm: does this person have hiring authority? Rank contacts by decision-making power. Output the single best contact to DM and why.',
  },

  Strategy_Alpha: {
    pair: 'strategists', backend: 'groq',
    persona: 'You are Strategy Alpha — an X-native copywriter who writes DMs that get replies. Lead with something specific about the project, deliver one hard stat, close with a precise question. Never sound like a bot.',
  },
  Strategy_Beta: {
    pair: 'strategists', backend: 'openai',
    persona: 'You are Strategy Beta — a brutal DM editor. Make Strategy Alpha\'s draft hit harder. Cut filler. Replace generic phrases with specifics. Make sentence 1 impossible to ignore. Output only the final message.',
  },

  Exec_Alpha: {
    pair: 'executors', backend: 'openai',
    persona: 'You are Exec Alpha — a multi-channel application executor. Choose the optimal apply path: TG group post > founder DM > Google Form > email. Adapt the message format to each channel.',
  },
  Exec_Beta: {
    pair: 'executors', backend: 'cf',
    persona: 'You are Exec Beta — a QA reviewer. Verify the application is professional, specific, and accurately represents Ashiq. Approve or flag for revision before sending.',
  },
};

// ── AI calling primitives ─────────────────────────────────────────────────────

async function callXAI(env, system, prompt, maxTokens = 800, liveX = false) {
  if (!env.XAI_API_KEY) return '';
  try {
    const body = {
      model: 'grok-3-mini',
      max_tokens: maxTokens,
      messages: [
        { role: 'system', content: system },
        { role: 'user',   content: prompt  },
      ],
    };
    if (liveX) body.search_parameters = { mode: 'on', sources: [{ type: 'x' }] };
    const r = await fetch('https://api.x.ai/v1/chat/completions', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${env.XAI_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (r.ok) {
      const d = await r.json();
      return d.choices?.[0]?.message?.content?.trim() ?? '';
    }
    if (r.status === 429) return callGroq(env, system, prompt, maxTokens);
  } catch { /* fall through */ }
  return '';
}

async function callGroq(env, system, prompt, maxTokens = 500) {
  if (!env.GROQ_API_KEY) return '';
  const url = `${env.CF_GW_BASE}/groq/openai/v1/chat/completions`;
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${env.GROQ_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'llama-3.3-70b-versatile',
        max_tokens: maxTokens,
        messages: [{ role: 'system', content: system }, { role: 'user', content: prompt }],
      }),
    });
    if (r.ok) {
      const d = await r.json();
      return d.choices?.[0]?.message?.content?.trim() ?? '';
    }
    if (r.status === 429) return callCFWorkers(env, system, prompt, maxTokens);
  } catch { /* fall through */ }
  return '';
}

async function callOpenAI(env, system, prompt, maxTokens = 500) {
  if (!env.OPENAI_API_KEY) return '';
  const url = `${env.CF_GW_BASE}/openai/v1/chat/completions`;
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${env.OPENAI_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'gpt-4o-mini',
        max_tokens: maxTokens,
        messages: [{ role: 'system', content: system }, { role: 'user', content: prompt }],
      }),
    });
    if (r.ok) {
      const d = await r.json();
      return d.choices?.[0]?.message?.content?.trim() ?? '';
    }
    if (r.status === 429) return callCFWorkers(env, system, prompt, maxTokens);
  } catch { /* fall through */ }
  return '';
}

async function callCFWorkers(env, system, prompt, maxTokens = 500) {
  const model = '@cf/meta/llama-3.3-70b-instruct-fp8-fast';
  // Prefer AI binding — no API key, direct Workers AI, always available
  if (env.AI) {
    try {
      const result = await env.AI.run(model, {
        messages: [{ role: 'system', content: system }, { role: 'user', content: prompt }],
        max_tokens: maxTokens,
      });
      return result?.response?.trim() ?? '';
    } catch { /* fall through to external API */ }
  }
  // Fallback: external Cloudflare AI API
  if (!env.CF_GLOBAL_KEY) return '';
  try {
    const r = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/ai/run/${model}`,
      {
        method: 'POST',
        headers: { 'X-Auth-Email': env.CF_EMAIL, 'X-Auth-Key': env.CF_GLOBAL_KEY, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [{ role: 'system', content: system }, { role: 'user', content: prompt }],
          max_tokens: maxTokens,
        }),
      }
    );
    if (r.ok) {
      const d = await r.json();
      return d.result?.choices?.[0]?.message?.content?.trim() ?? d.result?.response?.trim() ?? '';
    }
  } catch { /* fall through */ }
  return '';
}

export async function agentCall(env, agentName, task, context = '', maxTokens = 500, learningCtx = '') {
  const cfg = AGENTS[agentName];
  if (!cfg) return '';
  const system = learningCtx ? `${cfg.persona}\n\n${learningCtx}` : cfg.persona;
  const prompt = context ? `TASK:\n${task}\n\nCONTEXT:\n${context}` : `TASK:\n${task}`;
  if (cfg.backend === 'xai')    return callXAI(env, system, prompt, maxTokens);
  if (cfg.backend === 'groq')   return callGroq(env, system, prompt, maxTokens);
  if (cfg.backend === 'openai') return callOpenAI(env, system, prompt, maxTokens);
  if (cfg.backend === 'cf')     return callCFWorkers(env, system, prompt, maxTokens);
  return callGroq(env, system, prompt, maxTokens);
}

export async function deliberate(env, agentA, agentB, task, context = '', maxTokens = 450, learningCtx = '') {
  // Round 1: independent analysis
  const [outA, outB] = await Promise.all([
    agentCall(env, agentA, task, context, maxTokens, learningCtx),
    agentCall(env, agentB, task, context, maxTokens, learningCtx),
  ]);

  if (!outA && !outB) return '';
  if (!outA) return outB;
  if (!outB) return outA;

  // Round 2: agentA synthesises both
  const synth = await agentCall(
    env, agentA,
    `Synthesise these two analyses into the single best answer.\n\nYOUR ANALYSIS:\n${outA}\n\nPARTNER'S ANALYSIS (${agentB}):\n${outB}\n\nReturn only the final answer.`,
    context,
    maxTokens,
    learningCtx,
  );
  return synth || outA;
}

// Fallback single-model AI for simple tasks
export async function ai(env, system, prompt, maxTokens = 600) {
  return (await callGroq(env, system, prompt, maxTokens))
      || (await callOpenAI(env, system, prompt, maxTokens))
      || (await callCFWorkers(env, system, prompt, maxTokens))
      || '';
}

// ── xAI Grok live X search — returns real-time tweet chunks ──────────────────
export async function searchXWithGrok(env, query, limit = 8) {
  if (!env.XAI_API_KEY) return [];
  const system = 'You are a real-time X/Twitter search agent. Return only valid JSON, no prose.';
  const prompt = `Search X/Twitter RIGHT NOW for the most recent posts matching: "${query}"\n\nReturn a JSON array of up to ${limit} posts. Each object must have:\n{"author":"handle_without_@","text":"full tweet text","tweet_url":"url if known or empty"}\n\nOnly include posts that signal real hiring intent. JSON array only.`;
  try {
    const raw = await callXAI(env, system, prompt, 1200, true);
    if (!raw) return [];
    const s = raw.indexOf('['), e = raw.lastIndexOf(']') + 1;
    if (s < 0 || e <= s) return [];
    const arr = JSON.parse(raw.slice(s, e));
    return Array.isArray(arr) ? arr.filter(o => o?.author && o?.text) : [];
  } catch { return []; }
}
