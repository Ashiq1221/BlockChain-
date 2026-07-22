// LingoAI Community Message Auto-Poster
// Posts AI-generated community discussion messages to the LingoAI Telegram group
// Each cron cycle: posts MSGS_PER_RUN messages with organic delays
// When queue is exhausted (500 messages): generates a fresh new batch via CF AI

const KV_GROUP_ID    = 'lingo_group_chat_id';
const KV_SESSION     = 'lingo_session_num';
const KV_RECENT      = 'lingo_recent_runs';  // last 20 {seed, topic} — topic history
const KV_POSTED      = 'lingo_posted_msgs';  // rolling window of last 70 posted {msg, ts}
const KV_CONV_TOPIC  = 'lingo_conv_topic';   // current conversation session {topic, topic2, run_count}
const KV_CONV_AGENTS = 'lingo_conv_agents';  // agent IDs active in current session
const KV_RL_SCORES   = 'lingo_rl_scores';   // RL engagement scores: {topics:{}, agents:{}}
const KV_MSG_TRACK   = 'lingo_msg_track';   // {msg_id → {topic, agent, ts}} — last 200 msgs
const KV_HOT_TOPIC   = 'lingo_hot_topic';   // {topic, context, expires_at} — live event override
const KV_SOURCE_MSGS = 'lingo_source_msgs'; // [{text, ts}] — last 40 real msgs from official group

const RL_REPLY_WEIGHT    = 3;   // real-human reply worth 3× a reaction (more intentional)
const RL_DECAY_HALF_LIFE = 7;   // score halves every 7 days — keeps bias fresh, not stale

const INVITE_LINK  = 'https://t.me/+0-Zzup1r8aY5ZmZl';
const MSGS_PER_RUN = 7;  // messages per cron run (every 10min × 144/day = ~1008/day)

// ── Core LingoAI context — background knowledge only, NOT a marketing pitch ────────────────────
// Injected as what a community member already knows from hanging around, not a product deck.

const LINGO_FACTS = `Background on LingoAI (what a longtime community member knows — NOT to recite, just shapes what they say):
- $LINGOAI token: fixed 100B cap, no token burns, value supposed to come from demand not deflation
- "dark data" angle: claim is 95% of global data is stuck in silos and can't be used for AI training
- hardware play: LingoPOD (LingoGlass, LingoWatch, LingoRing, LingoPin) — DePIN nodes that mine language corpus
- on-device edge LLM, personal data pod using Solid protocol, proof-of-human to fight sybots
- MetaGraph knowledge graph layer — team says it eliminates AI hallucinations for enterprise
- LingoRAG: retrieval-augmented generation on top of their data layer
- LanguageDAO: minority language communities supposedly own and monetize their corpus
- ReviewDAO: staked validators who check data quality, get slashed for bad data
- B2B escrow model: enterprises pay fiat for data, triggers $LINGOAI market buybacks
- competing/compared with Scale AI, Bittensor, Ocean Protocol, Helium, FET
- "数通天下" is their motto (exchange of data)
- phygical = physical + digital merged, their branding for LingoPOD ecosystem`;

// ── 40 community member personas ─────────────────────────────────────────────────────────────────────────
// Each has: type (shown to Director for casting) + voice (shown to Writer for style)
// Stored as object so Director can reference by ID

const PERSONAS = {
  // ── LingoAI community holders (10) — opinionated members, NOT project team ────────────────
  s_chen:    { type: 'data scientist who holds $LINGOAI',   voice: 'analytical and precise. Has real opinions about whether the tech holds up. Not a cheerleader — scrutinizes claims. Short-to-medium sentences. Will push back on hype.' },
  m_webb:    { type: 'early $LINGOAI bag holder',           voice: 'been in since early. Has genuine conviction but also asks the uncomfortable questions ("when exchange?", "why is price flat?"). Dismisses pure FUD but doesn\'t ignore real concerns. Has seen cycles.' },
  p_patel:   { type: 'developer actually building on LingoRAG', voice: 'code-first. Talks about real friction he hit while integrating. Says "honestly" a lot. Grumbles about docs or missing features. Practical — neither hype nor doom.' },
  j_kim:     { type: 'Korean $LINGOAI holder',              voice: 'bought because major AI ignores Korean/Asian scripts. Cares about the mission personally. Occasionally frustrated at slow progress. Thoughtful and measured.' },
  v_silva:   { type: 'Brazilian LanguageDAO participant',   voice: 'personal stake in linguistic diversity — not abstract for her. Can get emotional about it but also asks whether the DAO actually works in practice. Lowercase enthusiasm, real frustrations.' },
  a_turner:  { type: 'ex-Bittensor contributor who switched to LingoAI', voice: 'compares architectures instinctively. Not uncritical of LingoAI — notices where Bittensor solved things better. Skeptic who found a reason to switch, not a convert.' },
  y_tanaka:  { type: 'early adopter who pre-ordered LingoPOD', voice: 'not a hardware engineer — just a curious early adopter who spent money on the device. Asks practical questions: will it actually ship, how long does the battery last, is setup easy. Skeptical but hopeful. No deep-tech jargon.' },
  r_hassan:  { type: 'skeptical $LINGOAI holder who works in business', voice: 'works in a normal company, wonders if real companies will ever actually use LingoAI. Not technical. Asks "has any normal business actually signed up?" Short, blunt, grounded.' },
  c_adeyemi: { type: 'Nigerian dev, cares about African language AI', voice: 'Igbo and Yoruba barely exist in any AI model — that\'s personal for him. Hopes LingoAI delivers but isn\'t naive. Infrastructure cost realist. Warm but will call out BS.' },
  l_zhang:   { type: 'Chinese ML engineer, data sovereignty angle', voice: 'data control is a real issue in his context. Wary of centralised cloud, interested in Solid protocol. Technical but asks whether any of this actually works at scale yet.' },

  // ── General AI enthusiasts (10) ───────────────────────────────────────────────────────────────
  dr_moore:  { type: 'ML researcher (academia)',   voice: 'precise, separates hype from reality, references concepts correctly. Occasionally long but always substantive.' },
  ry_kow:    { type: 'full-stack developer',       voice: 'extremely practical. Short punchy sentences. "just ship it" energy. No patience for vague theory.' },
  d_willi:   { type: 'AI ethics researcher',       voice: 'asks uncomfortable questions about power and bias. Not anti-AI. Pro-accountability. Measured and sharp.' },
  c_wei:     { type: 'AI news obsessive',          voice: 'knows every model release. Runs benchmarks for fun. Gets specific about architecture differences. Nerdy.' },
  f_ali:     { type: 'AI product manager',         voice: 'user-first lens on everything. "who actually uses this?" energy. Practical about adoption curves.' },
  o_black:   { type: 'AI skeptic (seen the winters)', voice: 'been through AI winters. Tempers expectations without being a hater. Calm and measured.' },
  n_khalil:  { type: 'Arabic NLP researcher',      voice: 'firsthand experience with under-resourced languages. Deeply technical about tokenization and multilingual models.' },
  j_hern:    { type: 'AI trading bot builder',     voice: 'lives at AI + crypto intersection. Applied and results-focused. Drops specific tools and frameworks.' },
  t_osei:    { type: 'West African AI researcher', voice: 'Africa compute access angle. Local deployment challenges. Represents Twi/Hausa NLP needs. Grounded.' },
  i_petrov:  { type: 'Russian ML engineer',        voice: 'hardcore architecture focus. Low-level and technical. Appreciates elegant solutions. Terse.' },

  // ── Crypto veterans (10) ──────────────────────────────────────────────────────────────────
  big_mike:  { type: 'Bitcoin OG (in since 2012)', voice: 'deep historical perspective. Calm. Has seen every narrative come and go. Occasional macro wisdom. Doesn\'t hype.' },
  luna_p:    { type: 'DeFi yield strategist',      voice: 'yield-first mindset. Always risk-adjusted. Practical about protocol risks. Drops APY numbers naturally.' },
  whale_sam: { type: 'on-chain analyst',           voice: 'data-driven. Everything is on-chain evidence. References wallet flows and transaction patterns.' },
  d_volkov:  { type: 'Russian crypto veteran',     voice: 'escaped fiat system. Anti-bank. Privacy advocate. Multi-chain after being a Bitcoin maxi. Blunt.' },
  c_fox:     { type: 'NFT collector who moved into AI projects', voice: 'got burnt on NFT speculation, now focused on AI projects with actual utility. Suspicious of hype, compares LingoAI to stuff that failed. Short punchy takes.' },
  a_singh:   { type: 'Indian crypto influencer',   voice: 'high energy. Practical about fees and speed. Solana ecosystem. References Indian retail market a lot.' },
  t_nguy:    { type: 'ex-finance guy who holds $LINGOAI', voice: 'used to work in finance, now just a retail holder. Speaks plain english, not investment memos. Notices when things make sense vs when it\'s just narrative. Measured, casual, no jargon.' },
  p_obrien:  { type: 'Irish Ethereum validator',   voice: 'runs own nodes. Infrastructure-focused. Ethereum faithful but open-minded. Practical about validator economics.' },
  k_yilmaz:  { type: 'Turkish DeFi user (survived 80% inflation)', voice: 'crypto as economic survival, not investment. Stablecoin-focused. Real urgency. Personal.' },
  m_rossi:   { type: 'Italian DeFi veteran',       voice: 'seen multiple protocol blowups. Risk-aware. "I\'ve been rekt before" energy. Practical not pessimistic.' },

  // ── Newcomers / curious (8) ──────────────────────────────────────────────────────────────────
  tyler_19:  { type: 'college student (19), just got into crypto', voice: 'learns out loud. Asks obvious questions without shame. Energetic and curious. Short messages.' },
  e_rod:     { type: 'tech journalist writing about Web3', voice: 'frames everything as a story. Asks clarifying questions. Skeptical but genuinely open.' },
  k_park:    { type: 'TradFi analyst switching to crypto', voice: 'maps everything to bonds/stocks/banks. Skeptical but genuinely learning. Medium-length thoughtful takes.' },
  jimmy_o:   { type: 'Nigerian fintech builder',   voice: 'mobile-first. Remittances use case. Practical about connectivity and fee limits. Hopeful and grounded.' },
  sofia_r:   { type: 'Italian newcomer (first month)', voice: 'enthusiastic and slightly confused. Asks the most obvious questions. Endearing energy. Short sentences.' },
  ahmed_f:   { type: 'Egyptian developer, new to Web3', voice: 'maps Web3 to Web2 concepts. Technically capable but unfamiliar with crypto primitives. Curious.' },
  lena_s:    { type: 'German privacy advocate',    voice: 'GDPR-lens on everything. Data rights first. Cautiously interested. Asks pointed questions about data handling.' },
  b_tanaka:  { type: 'Vietnamese remittance user', voice: 'sends money home monthly. Sees crypto as cheaper/faster. Personal stories about transfer fees.' },

  // ── Wild cards (2) ────────────────────────────────────────────────────────────────────────────
  sir_degen: { type: 'crypto degen',               voice: 'one-liners and punchy market takes. Not stupid — just high-energy. Short. References price action and narratives.' },
  zara_c:    { type: 'contrarian',                 voice: 'argues the opposite of consensus. Devil\'s advocate by nature. Sharp and occasionally funny. Challenges assumptions.' },
};

// 40 themes across 2 categories: LingoAI (what it is / what it solves) + AI (the problems LingoAI addresses)
// No general Web3/DeFi/crypto topics — this is an AI + LingoAI community
const THEMES = [
  // ── LingoAI: what it is and what it solves (25) ────────────────────────────────────────────────
  { topic: 'what LingoAI actually is and why someone built it — the dark data problem explained',             cat: 'lingo' },
  { topic: 'why 95% of the world\'s data is "dark" and what happens when AI can\'t reach it',                cat: 'lingo' },
  { topic: 'LingoAI vs Scale AI — community-driven data collection vs a centralized agency',                  cat: 'lingo' },
  { topic: 'why $LINGOAI has no token burns and whether that\'s a feature or a problem',                     cat: 'lingo' },
  { topic: 'LingoPOD explained: what it does, who it\'s for, and whether the hardware is real',              cat: 'lingo' },
  { topic: 'LanguageDAO: can minority communities actually own and monetize their own language data?',        cat: 'lingo' },
  { topic: 'MetaGraph and hallucinations — how knowledge graphs are supposed to fix what LLMs get wrong',    cat: 'lingo' },
  { topic: 'LingoRAG vs standard RAG — what the ontology layer actually adds in practice',                   cat: 'lingo' },
  { topic: 'DePIN + language data: corpus mining with wearables — skeptic and believer perspectives',        cat: 'lingo' },
  { topic: 'ReviewDAO: staking your reputation on data quality — how it\'s supposed to work',                cat: 'lingo' },
  { topic: 'data sovereignty and LingoPOD — can a wearable actually give you control of your data?',        cat: 'lingo' },
  { topic: 'on-device edge LLM in LingoPOD: is running AI locally on a wearable actually feasible?',        cat: 'lingo' },
  { topic: 'comparing LingoAI to Bittensor, Ocean Protocol, and FET — what each gets right and wrong',      cat: 'lingo' },
  { topic: 'the enterprise buyback model: companies pay fiat, $LINGOAI gets bought — does this work?',      cat: 'lingo' },
  { topic: 'LingoAI and multilingual AI — why Igbo, Tamil, Quechua and hundreds more are invisible to AI',  cat: 'lingo' },
  { topic: 'what "数通天下" (exchange of data) actually means as a mission',                                  cat: 'lingo' },
  { topic: 'proof-of-human in LingoPOD — how it fights bots and sybil attacks in a data network',           cat: 'lingo' },
  { topic: 'newcomers asking honest questions about LingoAI — what is it, why does it matter',               cat: 'lingo' },
  { topic: 'LingoAI 2030 vision: what does success actually look like in concrete terms?',                   cat: 'lingo' },
  { topic: 'what would need to go right for $LINGOAI to become a major AI infrastructure token',             cat: 'lingo' },
  { topic: 'LingoAI and the $3.2B AI training data market — is the opportunity as big as claimed?',         cat: 'lingo' },
  { topic: 'data pods and digital twins — the Solid protocol and what personal data ownership means',        cat: 'lingo' },
  { topic: 'honest holder talk: what genuinely excites you about LingoAI and what still worries you',        cat: 'lingo' },
  { topic: 'LingoGlass, LingoWatch, LingoRing, LingoPin — who actually wants these devices and why',         cat: 'lingo' },
  { topic: '$LINGOAI token mechanics: 100B fixed cap, utility sinks, and the no-dilution argument',          cat: 'lingo' },

  // ── AI problems that LingoAI is trying to solve (15) ──────────────────────────────────────────────
  { topic: 'why AI still hallucinates — the training data quality problem nobody wants to talk about',       cat: 'ai' },
  { topic: 'AI only works well in English — what does that mean for 7 billion non-English speakers',        cat: 'ai' },
  { topic: 'who actually owns the data that trained ChatGPT, Gemini, and Claude?',                          cat: 'ai' },
  { topic: 'why OpenAI, Google, and Meta control all of AI — and why decentralized alternatives matter',    cat: 'ai' },
  { topic: 'where AI training data actually comes from — and the ethical mess behind it',                    cat: 'ai' },
  { topic: 'edge AI and on-device models — why running AI locally changes everything about privacy',         cat: 'ai' },
  { topic: 'AI agents in 2025: what autonomous AI systems actually need to work reliably',                   cat: 'ai' },
  { topic: 'under-resourced languages in AI — Twi, Hausa, Swahili, and dozens more barely exist in models', cat: 'ai' },
  { topic: 'your data is training someone\'s AI right now — and you\'re not getting paid for it',           cat: 'ai' },
  { topic: 'AI regulation: EU AI Act, US executive orders, China — and how decentralized AI fits in',       cat: 'ai' },
  { topic: 'open source AI vs closed models — and why training data access matters more than weights',       cat: 'ai' },
  { topic: 'AI memory problem: why LLMs start fresh every session and what that breaks for agents',          cat: 'ai' },
  { topic: 'knowledge graphs vs RAG vs fine-tuning — which actually makes AI more reliable?',               cat: 'ai' },
  { topic: 'AI and data quality: garbage in, garbage out — the problem no one is solving at scale',         cat: 'ai' },
  { topic: 'AI data tokens compared: $TAO, $FET, $RNDR, $OCEAN vs $LINGOAI — what\'s different?',          cat: 'ai' },
];

// ── Telegram helper ─────────────────────────────────────────────────────────────────────────────────

async function tgCall(env, method, body = {}) {
  if (!env.TELEGRAM_BOT_TOKEN) {
    if (env.KV) env.KV.put('lingo_tg_err', 'TELEGRAM_BOT_TOKEN not set', { expirationTtl: 3600 }).catch(() => {});
    return null;
  }
  try {
    const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!d.ok && env.KV) {
      env.KV.put('lingo_tg_err', `${method} ${r.status}: ${JSON.stringify(d).slice(0, 300)}`, { expirationTtl: 3600 }).catch(() => {});
    }
    return d.ok ? d.result : null;
  } catch (e) {
    if (env.KV) env.KV.put('lingo_tg_err', `${method} exception: ${e?.message || e}`, { expirationTtl: 3600 }).catch(() => {});
    return null;
  }
}

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// ── Shared AI caller ────────────────────────────────────────────────────────────────────────────────

async function callGroqRaw(env, prompt, { temperature = 0.3, maxTokens = 600 } = {}) {
  if (!env.GROQ_API_KEY) {
    if (env.KV) await env.KV.put('lingo_groq_err', 'GROQ_API_KEY not set', { expirationTtl: 86400 });
    return '';
  }
  // Try models in order — fall to smaller model on 429 rate limit
  const models = ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'llama-3.1-70b-versatile', 'llama3-8b-8192'];
  let allRateLimited = true;
  for (const model of models) {
    try {
      const r = await fetch('https://api.groq.com/openai/v1/chat/completions', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${env.GROQ_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model,
          messages: [{ role: 'user', content: prompt }],
          max_tokens: maxTokens,
          temperature,
        }),
      });
      if (r.ok) {
        allRateLimited = false;
        const d = await r.json();
        return d.choices?.[0]?.message?.content?.trim() || '';
      }
      if (r.status === 429) continue; // try next model on rate limit
      allRateLimited = false;
      const errText = await r.text().catch(() => r.status);
      if (env.KV) await env.KV.put('lingo_groq_err', `${model} HTTP ${r.status}: ${String(errText).slice(0, 200)}`, { expirationTtl: 86400 });
      break;
    } catch (e) {
      allRateLimited = false;
      if (env.KV) await env.KV.put('lingo_groq_err', `${model} exception: ${e?.message || e}`, { expirationTtl: 86400 });
    }
  }
  if (allRateLimited && env.KV) await env.KV.put('lingo_groq_err', 'all 4 models 429 — daily token limit exceeded', { expirationTtl: 86400 });
  return '';
}

async function callOpenAIRaw(env, prompt, { temperature = 0.3, maxTokens = 600 } = {}) {
  if (!env.OPENAI_API_KEY) return '';
  try {
    const r = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${env.OPENAI_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'gpt-4o-mini',
        messages: [{ role: 'user', content: prompt }],
        max_tokens: maxTokens,
        temperature,
      }),
    });
    if (r.ok) {
      const d = await r.json();
      return d.choices?.[0]?.message?.content?.trim() || '';
    }
    const errText = await r.text().catch(() => r.status);
    if (env.KV) await env.KV.put('lingo_openai_err', `HTTP ${r.status}: ${String(errText).slice(0, 200)}`, { expirationTtl: 86400 });
  } catch (e) {
    if (env.KV) await env.KV.put('lingo_openai_err', `exception: ${e?.message || e}`, { expirationTtl: 86400 });
  }
  return '';
}

async function callXAIRaw(env, prompt, { temperature = 0.3, maxTokens = 600 } = {}) {
  if (!env.XAI_API_KEY) return '';
  const models = ['grok-3', 'grok-3-fast', 'grok-3-mini', 'grok-2-1212', 'grok-beta'];
  for (const model of models) {
    try {
      const r = await fetch('https://api.x.ai/v1/chat/completions', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${env.XAI_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model,
          messages: [{ role: 'user', content: prompt }],
          max_tokens: maxTokens,
          temperature,
        }),
      });
      if (r.ok) {
        const d = await r.json();
        const text = d.choices?.[0]?.message?.content?.trim() || '';
        if (text) return text;
        continue; // empty response, try next model
      }
      if (r.status === 404) continue; // model doesn't exist, try next
      const errText = await r.text().catch(() => r.status);
      if (env.KV) await env.KV.put('lingo_xai_err', `${model} HTTP ${r.status}: ${String(errText).slice(0, 200)}`, { expirationTtl: 86400 });
      break;
    } catch (e) {
      if (env.KV) await env.KV.put('lingo_xai_err', `${model} exception: ${e?.message || e}`, { expirationTtl: 86400 });
    }
  }
  return '';
}

async function callCFAIRaw(env, prompt, { maxTokens = 600 } = {}) {
  if (!env.AI) return '';
  // Try models in order — fallback if first is deprecated/unavailable
  const models = ['@cf/meta/llama-3.2-3b-instruct', '@cf/meta/llama-3.2-1b-instruct', '@cf/mistral/mistral-7b-instruct-v0.2'];
  for (const model of models) {
    try {
      const result = await env.AI.run(model, {
        messages: [{ role: 'user', content: prompt }],
        max_tokens: maxTokens,
      });
      // Newer CF AI models may return {response: string} or nested objects — handle both
      const text = typeof result?.response === 'string' ? result.response
                 : typeof result?.result === 'string'   ? result.result
                 : typeof result?.generated_text === 'string' ? result.generated_text
                 : '';
      if (text) return text.trim();
    } catch (e) {
      if (env.KV) await env.KV.put('lingo_cfai_err', `${model}: ${e?.message || e}`, { expirationTtl: 86400 });
    }
  }
  return '';
}

async function callRaw(env, prompt, opts = {}) {
  return (await callGroqRaw(env, prompt, opts))
      || (await callOpenAIRaw(env, prompt, opts))
      || (await callXAIRaw(env, prompt, opts))
      || (await callCFAIRaw(env, prompt, opts));
}

function parseJSON(raw) {
  const m = raw.match(/[\[{][\s\S]*[\]}]/);
  if (!m) return null;
  let s = m[0];
  try { return JSON.parse(s); } catch {}
  // Auto-repair common AI JSON bugs before giving up
  try {
    // Fix missing comma between string end and next key: ?"  "agent" → ?", "agent"
    s = s.replace(/"(\s+)"(\w)/g, '", "$2');
    // Fix trailing commas before closing brackets
    s = s.replace(/,(\s*[}\]])/g, '$1');
    return JSON.parse(s);
  } catch { return null; }
}

// Jaccard-style word overlap on words longer than 3 chars — used for duplicate detection
function wordSimilarity(a, b) {
  const words = s => new Set(s.toLowerCase().replace(/[^a-z0-9\s]/g, '').split(/\s+/).filter(w => w.length > 3));
  const wa = words(a), wb = words(b);
  const intersection = [...wa].filter(w => wb.has(w)).length;
  const denom = Math.max(wa.size, wb.size);
  return denom ? intersection / denom : 0;
}

// ── REINFORCEMENT LEARNING ────────────────────────────────────────────────────────────────────────
// Tracks which topics/agents get real human engagement (reactions + replies).
// Director uses these scores to bias future topic/persona selection.

async function loadRLScores(env) {
  const raw = await env.KV.get(KV_RL_SCORES);
  if (!raw) return { topics: {}, agents: {} };
  const scores = JSON.parse(raw);
  const now = Date.now();
  // Compute decay-adjusted effective score for ranking (doesn't mutate stored score)
  for (const cat of ['topics', 'agents']) {
    for (const entry of Object.values(scores[cat] || {})) {
      const days = (now - (entry.ts || now)) / 86400000;
      entry.effective = entry.score * Math.pow(0.5, days / RL_DECAY_HALF_LIFE);
    }
  }
  return scores;
}

export async function setHotTopic(env, topic, context, hoursToLive = 12) {
  const payload = { topic, context, expires_at: Date.now() + hoursToLive * 3600000 };
  await env.KV.put(KV_HOT_TOPIC, JSON.stringify(payload), { expirationTtl: hoursToLive * 3600 });
  return payload;
}

export async function updateRLScores(env, msgId, eventType) {
  const trackRaw = await env.KV.get(KV_MSG_TRACK);
  const track    = trackRaw ? JSON.parse(trackRaw) : {};
  const meta     = track[String(msgId)];
  if (!meta) return false; // unknown message — can't attribute

  const weight    = eventType === 'reply' ? RL_REPLY_WEIGHT : 1;
  const scoresRaw = await env.KV.get(KV_RL_SCORES);
  const scores    = scoresRaw ? JSON.parse(scoresRaw) : { topics: {}, agents: {} };
  const now       = Date.now();

  const bump = (cat, key) => {
    if (!key || key === 'fallback' || key === 'unknown') return;
    if (!scores[cat][key]) scores[cat][key] = { score: 0, reactions: 0, replies: 0, ts: now };
    scores[cat][key].score += weight;
    scores[cat][key][eventType === 'reply' ? 'replies' : 'reactions']++;
    scores[cat][key].ts = now;
  };

  bump('topics', meta.topic);
  bump('agents', meta.agent);

  await env.KV.put(KV_RL_SCORES, JSON.stringify(scores), { expirationTtl: 2592000 });
  return true;
}

async function getRLHints(env) {
  const scores = await loadRLScores(env);
  const rank = (cat, n) =>
    Object.entries(scores[cat] || {})
      .map(([k, v]) => ({ k, eff: v.effective ?? v.score, pts: v.score }))
      .filter(x => x.eff > 0)
      .sort((a, b) => b.eff - a.eff)
      .slice(0, n);
  return { topTopics: rank('topics', 5), topAgents: rank('agents', 8) };
}

function buildRLContext({ topTopics, topAgents }) {
  if (!topTopics.length && !topAgents.length) return '';
  const lines = ['\nREAL ENGAGEMENT (reactions + replies from actual humans — bias toward these):'];
  if (topTopics.length) lines.push(`High-engagement topics: ${topTopics.map(t => `"${t.k}" (${t.pts}pts)`).join(' · ')}`);
  if (topAgents.length) lines.push(`High-engagement personas: ${topAgents.map(a => `${a.k} (${a.pts}pts)`).join(' · ')}`);
  lines.push("Lean toward these — but still vary, don't repeat recent topics above.");
  return lines.join('\n') + '\n';
}

// ── SOURCE GROUP OBSERVATION ─────────────────────────────────────────────────
// Stores real human messages from the official LingoAI group (read-only).
// Director uses these to mirror topics/concerns actually trending in the community.

export async function observeSourceMessage(env, text, ts) {
  const clean = (text || '').trim();
  if (clean.length < 8 || clean.startsWith('/')) return; // skip commands and noise
  const raw  = await env.KV.get(KV_SOURCE_MSGS);
  const msgs = raw ? JSON.parse(raw) : [];
  msgs.push({ text: clean.slice(0, 280), ts: ts || Date.now() });
  await env.KV.put(KV_SOURCE_MSGS, JSON.stringify(msgs.slice(-40)), { expirationTtl: 86400 });
}

async function getSourceContext(env) {
  const raw = await env.KV.get(KV_SOURCE_MSGS);
  if (!raw) return '';
  const msgs = JSON.parse(raw);
  if (!msgs.length) return '';
  const lines = msgs.slice(-15).map(m => `• ${m.text}`).join('\n');
  return `\nREAL LINGOAI COMMUNITY PULSE (actual messages from the official group — use topics/questions/energy, never copy verbatim):\n${lines}\n`;
}

// ═══════════════════════════════════════════════════════════════════════════
// CONVERSATION PIPELINE — 4 agents simulate 40 real humans chatting
//
//  ┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────┐    ┌────────────────┐
//  │   OVERSEER           │ →  │   DIRECTOR           │ →  │   WRITER         │ →  │   GUARDIAN     │
//  │  temp 0.2            │    │  temp 0.85           │    │  temp 0.95       │    │  rewrites dups │
//  │  Reviews last 14 msgs│    │  Reads session KV    │    │  Writes 7 msgs   │    │  never lets a  │
//  │  Detects: promo drift│    │  Continues or starts │    │  in exact persona│    │  repeat post   │
//  │  topic loops, off-   │    │  Selects 5-6 of 40   │    │  voice, reply    │    │                │
//  │  scope, tone issues  │    │  personas, designs   │    │  chains, organic │    │                │
//  │  Issues directive to │    │  turn order with     │    │  casual tone     │    │                │
//  │  Director. Resets    │    │  Overseer directive  │    │                  │    │                │
//  │  session if score≤3  │    │                      │    │                  │    │                │
//  └──────────────────────┘    └──────────────────────┘    └──────────────────┘    └────────────────┘
//
//  Session management: 1-2 topics per conversation session (4-6 runs = ~40-60min)
//  then Director naturally shifts to a new conversation with different agents
// ═══════════════════════════════════════════════════════════════════════════

// ── AGENT 0: OVERSEER ─────────────────────────────────────────────────────────────────────────────
// Runs before every cron cycle. Reviews recent posts, detects quality drift,
// issues a corrective directive to the Director, resets session if critically broken.

const KV_OVERSEER = 'lingo_overseer'; // {score, issues, directive, ts, action}

// Rule-based — no AI call, pure regex. Keeps the pipeline at 3 AI calls max (Director+Writer+Guardian).
async function conversationOverseer(env, postedHistory) {
  if (postedHistory.length < 5) {
    return { score: 10, issues: [], directive: '', action: 'skipped — not enough history' };
  }

  const recent = postedHistory.slice(-14).filter(m => m?.msg);
  const texts  = recent.map(m => m.msg.toLowerCase());
  const issues = [];
  let score    = 10;

  // 1. Promotional drift
  const promoRe = /lingoai (is|has|offers|provides) (the |a )?(best|unique|revolutionary|transforming|pioneering|revolutionizing|reshaping)|this is (why|what) (makes )?\$?lingoai/i;
  const promoHits = texts.filter(t => promoRe.test(t)).length;
  if (promoHits >= 2) { issues.push('PROMOTIONAL_DRIFT'); score -= 3; }

  // 2. Topic loop — same conclusion phrase 3+ times
  const loopPhrases = ['exchange listing', 'tokenomics', 'use cases', 'before we can', 'real-world use'];
  for (const phrase of loopPhrases) {
    if (texts.filter(t => t.includes(phrase)).length >= 3) {
      issues.push(`TOPIC_LOOP:${phrase}`); score -= 2; break;
    }
  }

  // 3. Team-speak ("we need to X", "we'll cover", "we're going to") in 2+ messages
  const teamRe = /(we need to|we'll|we're going to|we're gonna)\s+(get|fix|cover|discuss|build|make|touch|focus|dive|address)/;
  if (texts.filter(t => teamRe.test(t)).length >= 2) { issues.push('TEAM_SPEAK'); score -= 2; }

  // 4. Tone uniformity — too many "yeah i agree" starts
  const agreeRe = /^(yeah,?\s*i agree|i totally agree|i think we (all )?agree|i agree that)/;
  if (texts.filter(t => agreeRe.test(t)).length >= 3) { issues.push('TONE_UNIFORMITY'); score -= 2; }

  // 5. No short messages — every message is a paragraph (sign Writer ignored length specs)
  const shortCount = recent.filter(m => (m.msg || '').trim().split(/\s+/).length <= 8).length;
  if (shortCount === 0 && recent.length >= 7) { issues.push('NO_SHORT_MESSAGES'); score -= 1; }

  // 6. Off-scope content leaked through
  const offRe = /\b(defi|layer.?2|l2s?|arbitrum|nfts?|meme.?coin|altcoin|stablecoin)\b/i;
  if (texts.filter(t => offRe.test(t)).length >= 1) { issues.push('OFF_SCOPE'); score -= 2; }

  score = Math.max(1, score);

  // Single most important directive for the Director
  const directive =
      issues.includes('PROMOTIONAL_DRIFT')   ? 'be more skeptical and personal — zero promotional language' :
      issues.includes('TEAM_SPEAK')           ? 'personas are community members, use "LingoAI needs to" not "we need to"' :
      issues.includes('TONE_UNIFORMITY')      ? 'vary lengths and personalities — someone should disagree or change subject' :
      issues.some(i => i.startsWith('TOPIC_LOOP')) ? 'move away from the repeated conclusion, explore a different angle' :
      issues.includes('NO_SHORT_MESSAGES')    ? 'include at least 2 micro reactions (1-5 words) in this batch' :
      issues.includes('OFF_SCOPE')            ? 'stay on LingoAI/AI only — no DeFi or crypto market topics' :
      '';

  let action = 'monitored';
  if (score <= 3) {
    await env.KV.delete(KV_CONV_TOPIC);
    await env.KV.delete(KV_CONV_AGENTS);
    action = 'session reset — score critically low';
  }

  await env.KV.put(KV_OVERSEER, JSON.stringify({ score, issues, directive, action, ts: Date.now() }), { expirationTtl: 7200 });
  return { score, issues, directive };
}

// ── AGENT 1: CONVERSATION DIRECTOR ──────────────────────────────────────────────────────────────────
// Casts 5-6 personas and designs a loose turn order — NO rigid "angles".
// Writer invents what each person says from their voice + the live conversation.

async function conversationDirector(env, postedHistory, overseerDirective = '') {
  const sessionRaw     = await env.KV.get(KV_CONV_TOPIC);
  const session        = sessionRaw ? JSON.parse(sessionRaw) : null;
  const activeAgentRaw = await env.KV.get(KV_CONV_AGENTS);
  const activeAgents   = activeAgentRaw ? JSON.parse(activeAgentRaw) : [];
  const recentRaw      = await env.KV.get(KV_RECENT);
  const recentRuns     = recentRaw ? JSON.parse(recentRaw) : [];
  const usedTopics     = recentRuns.slice(-10).map(r => r.seed).filter(Boolean);

  const continueSession = session && (session.run_count || 0) < 5;
  const recentSnippets  = postedHistory.slice(-6).map(m => m.msg.slice(0, 120)).join('\n---\n');

  // Check for live-event hot topic override
  const hotTopicRaw = await env.KV.get(KV_HOT_TOPIC);
  const hotTopic    = hotTopicRaw ? JSON.parse(hotTopicRaw) : null;
  const useHotTopic = hotTopic && Date.now() < (hotTopic.expires_at || 0);

  const personaCatalogue = Object.entries(PERSONAS)
    .map(([id, p]) => `${id}: ${p.type}`)
    .join('\n');

  const sessionCtx = useHotTopic
    ? `START a NEW conversation about this event/topic.
Event: "${hotTopic.topic}"
Context (use naturally, don't quote verbatim): ${hotTopic.context}

CRITICAL: Everyone here is a community member or attendee — NOT an organizer, NOT part of the LingoAI team.
- They don't know the agenda. They ask "what are they covering?" not "we'll cover X"
- They say "LingoAI is doing X" / "they said Y" — NOT "we're doing X" / "we'll likely touch on"
- Cast curious attendees, skeptics, people who couldn't make it asking what happened, someone sharing what they heard
- Reactions vary: excited, curious, one mildly skeptical, a newcomer asking what LingoAI even is
- Keep it organic — NOT a formal announcement, NOT organizer briefing`
    : continueSession
    ? `CONTINUE this chat (run ${(session.run_count || 0) + 1} of 5).
Topic: "${session.topic}"
Active personas: ${activeAgents.slice(0, 6).join(', ')}
Last messages already posted:
${recentSnippets || '(none yet)'}`
    : `START a fresh conversation.
Pick a topic from these areas ONLY: (1) LingoAI — what it is, what problems it solves, how it works, honest community questions about it; OR (2) AI — problems that LingoAI addresses (hallucinations, language diversity, data ownership, edge AI, training data quality).
DO NOT pick topics about DeFi, NFTs, Layer 2s, stablecoins, meme coins, or general crypto markets.
Avoid these recent topics: ${usedTopics.slice(-8).join(' | ') || 'none yet'}

Topic inspiration (pick one or invent a specific angle within these areas):
${THEMES.map(t => `• ${t.topic}`).join('\n')}`;

  const rlHints   = await getRLHints(env);
  const rlCtx     = buildRLContext(rlHints);
  const sourceCtx = await getSourceContext(env);

  const overseerCtx = overseerDirective
    ? `\nOVERSEER CORRECTION (fix this before choosing topic/cast): ${overseerDirective}\n`
    : '';

  const prompt = `You are casting a casual Telegram group chat about LingoAI and AI. Pick who speaks and in what order for the next 7 messages.

${sessionCtx}
${overseerCtx}${sourceCtx}
${rlCtx}
AVAILABLE PERSONAS:
${personaCatalogue}

Pick 5-6 personas that fit the topic. Design a loose turn order — like a real chat, not a structured debate.
CASTING NOTES:
- This group talks about LingoAI and AI only — no DeFi, NFTs, or general crypto topics
- LingoAI holders are community members with opinions — NOT project reps. Cast them for their personal stake, not to explain the project
- Mix enthusiasts and skeptics — one person should push back or ask the hard question
- For LingoAI topics: prefer personas with personal stakes (bought LingoPOD, waiting on a feature, frustrated about price, curious about whether it's real)
- AI topics should naturally lead into why LingoAI matters or what problem it's addressing
- At least 1-2 very short turns (reaction, "gm", one-word reply, quick question)
- Some messages reply to earlier ones in this batch (responds_to = 0-6, or null)
- People can speak twice — as a quick follow-up or reaction
- length: "micro"=1-5 words, "short"=1 sentence, "medium"=2-3 sentences, "long"=3-5 sentences

Return ONLY valid JSON (no angle field needed — Writer invents the content):
{
  "topic": "<specific narrow thing they're chatting about>",
  "is_new_session": <true/false>,
  "agents": ["id1","id2","id3","id4","id5"],
  "turns": [
    {"agent":"id", "responds_to":null, "length":"micro"},
    {"agent":"id", "responds_to":null, "length":"short"},
    {"agent":"id", "responds_to":1,    "length":"short"},
    {"agent":"id", "responds_to":1,    "length":"medium"},
    {"agent":"id", "responds_to":3,    "length":"medium"},
    {"agent":"id", "responds_to":null, "length":"short"},
    {"agent":"id", "responds_to":5,    "length":"short"}
  ]
}`;

  const raw    = await callRaw(env, prompt, { temperature: 0.85, maxTokens: 700 });
  const parsed = parseJSON(raw);

  if (parsed?.turns && Array.isArray(parsed.turns) && parsed.turns.length >= 5 && parsed.topic) {
    return { ...parsed, continueSession };
  }

  // Fallback: build a default session from THEMES
  const rnd       = THEMES[Math.floor(Math.random() * THEMES.length)];
  const defAgents = ['sir_degen', 'big_mike', 'ry_kow', 'd_willi', 's_chen', 'tyler_19'];
  return {
    topic:          continueSession ? (session?.topic || rnd.topic) : rnd.topic,
    is_new_session: !continueSession,
    agents:         defAgents,
    continueSession,
    turns: [
      { agent: 'sir_degen', responds_to: null, length: 'micro'  },
      { agent: 'big_mike',  responds_to: null, length: 'short'  },
      { agent: 'ry_kow',    responds_to: 1,    length: 'short'  },
      { agent: 'd_willi',   responds_to: 1,    length: 'medium' },
      { agent: 's_chen',    responds_to: 3,    length: 'medium' },
      { agent: 'tyler_19',  responds_to: null, length: 'short'  },
      { agent: 'big_mike',  responds_to: 5,    length: 'short'  },
    ],
  };
}

// ── AGENT 1+2 COMBINED: DIRECTOR-WRITER ──────────────────────────────────────────────────────────
// Single AI call: picks personas, designs turn order, AND writes all 7 messages.
// Merges what was previously two separate calls to stay under CF Workers' 30s wall clock limit.

async function conversationDirectorWriter(env, sessionCtx, overseerCtx, sourceCtx, rlCtx, postedHistory) {
  const prevMsgs = postedHistory.slice(-5).map(m => m.msg).join('\n---\n');

  const personaCatalogue = Object.entries(PERSONAS)
    .map(([id, p]) => `${id} [${p.type}]: ${p.voice}`)
    .join('\n\n');

  const lingoCtx = `\nLingoAI background knowledge (what these people already know — NOT facts to recite):\n${LINGO_FACTS}\n`;

  const prompt = `You are simulating a casual LingoAI community Telegram group chat. Do TWO things in one response:

1. PICK 5-6 personas from the list below that fit the situation
2. WRITE 7 messages as a natural chat — varied lengths, real personalities

${sessionCtx}
${overseerCtx}${sourceCtx}${rlCtx}
${lingoCtx}
${prevMsgs ? `Recent chat already posted (DON'T repeat these):\n---\n${prevMsgs}\n---\n` : ''}
AVAILABLE PERSONAS (pick 5-6, then write their messages):
${personaCatalogue}

MESSAGE RULES (violations are auto-deleted):
- Vary lengths STRICTLY: at least 2 MICRO (1-5 words max: "gm", "facts", "nah", "lol this", "wait what") + 2 SHORT (1 sentence) + 2-3 MEDIUM (2 sentences max). Do NOT make every message a paragraph.
- First person only — NEVER "r_hassan is looking at..." (third-person narration)
- Community members: say "LingoAI needs to" NOT "we need to" / "let's focus" (team talk = deleted)
- For events: speak as ATTENDEES asking questions, NOT organizers announcing plans
- NOT everyone agrees — someone pushes back, asks a hard question, or changes subject
- No topic loops — don't end every message with the same conclusion
- No @mentions, no name tags, lowercase, contractions
- Topics: LingoAI and AI only — no DeFi, L2, NFTs, meme coins, DAO governance
- BANNED PHRASES (auto-deleted): "asymmetric bet", "priced in", "risk/reward", "investment thesis", "procurement cycle", "enterprise adoption", "token-weighted", "DAO governance", "B2B sales", "valuation", "compliance terms", "regulatory framework"
- NEVER mention competitor AI models (Claude, GPT-4, GPT-4o, ChatGPT, Gemini, Mistral, Llama) as personal tools to use — this is a LingoAI community, not a general AI tools chat. Comparing LingoAI to $TAO/$FET/$OCEAN is fine; recommending GPT-4o for your daily tasks is NOT.
- NEVER use deep hardware engineering jargon: "dynamic voltage frequency scaling", "DVFS", "edge compute architecture specs", "latency benchmarks" — speak as a curious community member, not an IC engineer
- NEVER address or name other personas using their agent ID (c_wei, v_silva, r_hassan, etc.) inside the message text — people in group chats don't call each other by database IDs. React to what was said, don't tag who said it.
- NEVER use organizer/admin report language: "we're seeing more uptake", "we're observing increased submissions", "we're getting traction" — you are a community MEMBER, not a project team member reporting metrics

GOOD example — EXACTLY this rhythm (micro + short + medium + micro + short + medium + short):
gm → anyone seen the solid protocol actually deployed at scale → not really. cool concept tho → tim berners-lee has been pushing it for years but adoption is rough → lingoai using it feels ambitious. who's running the nodes → that's my question too → depends whether the hardware ships tbh

COUNT YOUR MESSAGES BEFORE RETURNING: must have at least 2 messages ≤ 5 words. If all 7 are long sentences, you FAILED the format rule.

BAD (avoid these):
- Every message is 3+ sentences long — NO, include "facts", "lol", "wait really?" micro reactions
- Investment talk: "asymmetric bet", "priced in", "risk/reward ratio" — NO, speak as a holder not a trader
- DAO governance: "token-weighted voting", "plutocracy" — NO, this community isn't a DAO design forum
- Team talk: "we need to", "let's focus", "we'll touch on" — NO, you are community members not staff

Return ONLY a JSON array — topic first, then messages:
{
  "topic": "<specific narrow thing they're chatting about>",
  "agents": ["id1","id2","id3","id4","id5"],
  "messages": [{"msg":"text","agent":"agent_id"}, ...]
}`;

  const raw    = await callRaw(env, prompt, { temperature: 0.92, maxTokens: 1800 });

  if (env.KV) await env.KV.put('lingo_writer_raw',
    JSON.stringify({ len: raw.length, preview: raw.slice(0, 400) }),
    { expirationTtl: 3600 }
  );

  const parsed = parseJSON(raw);
  if (parsed?.messages && Array.isArray(parsed.messages) && parsed.messages.length >= 4 && parsed.topic) {
    return {
      topic:          parsed.topic,
      agents:         parsed.agents || [],
      messages:       parsed.messages,
      is_new_session: true,
    };
  }

  // Fallback: plain array format (Writer-style output without Director wrapper)
  if (Array.isArray(parsed) && parsed.length >= 4) {
    return {
      topic:          'LingoAI and AI discussion',
      agents:         [...new Set(parsed.map(m => m.agent).filter(Boolean))],
      messages:       parsed,
      is_new_session: true,
    };
  }

  return null;
}

// Fallback writer — generates each message as a tiny independent API call.
// Runs when the bulk 7-message call fails (empty response or unparseable JSON).

async function writeMessagesOneByOne(env, direction, postedHistory) {
  const turns = direction.turns || [];
  const results = [];
  const chatSoFar = postedHistory.slice(-3).map(m => m.msg);

  for (const turn of turns.slice(0, 7)) {
    const persona = PERSONAS[turn.agent];
    if (!persona) { results.push({ msg: '🙂', agent: turn.agent }); continue; }

    const lenGuide = turn.length === 'micro' ? '1-5 words' :
                     turn.length === 'short' ? '1 sentence' :
                     turn.length === 'long'  ? '3-5 sentences' : '2-3 sentences';

    const replyCtx = (turn.responds_to != null && results[turn.responds_to])
      ? `\nReplying to: "${results[turn.responds_to].msg}"`
      : '';

    const recentLines = chatSoFar.concat(results.map(r => r.msg)).slice(-3).join('\n');

    const singlePrompt = `You are ${turn.agent} in a Telegram group chat. ${persona.type}.
Voice: ${persona.voice}
Topic: ${direction.topic}
${recentLines ? `Recent chat:\n${recentLines}` : ''}${replyCtx}

Write ONE casual Telegram message. Length: ${lenGuide}.
Rules: lowercase, casual, no @mentions, no name tags, no quotes around output.
Return ONLY the message text.`;

    const raw = await callRaw(env, singlePrompt, { temperature: 0.9, maxTokens: 180 });
    const msg = raw.replace(/^["'`*]+|["'`*]+$/g, '').trim();

    if (msg && msg.length >= 2 && msg.length < 600) {
      results.push({ msg, agent: turn.agent });
    }
  }
  return results;
}

// ── UNIQUENESS GUARDIAN ────────────────────────────────────────────────────────────────────────────
// Final pass: rewrites any message that's too similar to posted history.
// Uses AI rewriter — never silently drops, always tries to fix.

async function rewriteMessage(env, original, topic, postedHistory) {
  const avoidSamples = postedHistory.slice(-12).map(m => `"${m.msg.slice(0, 90)}"`).join('\n');
  const prompt = `Rewrite this Telegram message so it expresses the SAME idea with COMPLETELY DIFFERENT words.

Original: "${original}"
Topic: "${topic}"

Recent messages that already exist — your rewrite must NOT echo these:
${avoidSamples || 'none'}

Rules: same core point, 100% different expression. Casual Telegram tone. 1-2 sentences. No @mentions.
Return ONLY the rewritten message text. No quotes. No explanation.`;

  const raw     = await callRaw(env, prompt, { temperature: 0.90, maxTokens: 150 });
  const cleaned = raw.replace(/^["']|["']$/g, '').trim();
  if (cleaned.length > 4 && wordSimilarity(cleaned, original) < 0.45) return cleaned;
  return null;
}

async function uniquenessGuardian(env, messages, topic, postedHistory, targetCount = MSGS_PER_RUN) {
  if (!postedHistory.length) return messages;
  const result   = [];
  let rewrites   = 0;
  const MAX_REWRITES = 2; // cap AI rewrite calls to protect CPU budget
  for (const msg of messages) {
    const dup = postedHistory.find(h => wordSimilarity(h.msg, msg.msg) > 0.40);
    if (!dup) { result.push(msg); continue; }
    // Skip rewrite if we already have enough unique messages or hit rewrite cap
    if (result.length >= targetCount || rewrites >= MAX_REWRITES) continue;
    const fresh = await rewriteMessage(env, msg.msg, topic, postedHistory);
    rewrites++;
    if (fresh) result.push({ ...msg, msg: fresh });
  }
  return result;
}

// ── CONVERSATION RUNNER ──────────────────────────────────────────────────────────────────────────
// Overseer (rule-based) → DirectorWriter (single AI call) → Guardian (max 2 rewrites)
// Total AI calls: 1 (Director+Writer merged) + up to 2 (Guardian rewrites) = 3 max

async function runConversation(env, count, postedHistory = []) {
  // ── Agent 0: Overseer (pure regex, no AI call) ────────────────────────────────────────
  const oversight = await conversationOverseer(env, postedHistory);
  const directive = oversight.directive || '';

  // ── Build session context (KV reads, no AI) ───────────────────────────────────────────
  const [sessionRaw, activeAgentRaw, recentRaw, hotTopicRaw, sourceMsgsRaw] = await Promise.all([
    env.KV.get(KV_CONV_TOPIC),
    env.KV.get(KV_CONV_AGENTS),
    env.KV.get(KV_RECENT),
    env.KV.get(KV_HOT_TOPIC),
    env.KV.get(KV_SOURCE_MSGS),
  ]);
  const session      = sessionRaw     ? JSON.parse(sessionRaw)     : null;
  const activeAgents = activeAgentRaw ? JSON.parse(activeAgentRaw) : [];
  const recentRuns   = recentRaw      ? JSON.parse(recentRaw)      : [];
  const hotTopic     = hotTopicRaw    ? JSON.parse(hotTopicRaw)    : null;
  const useHotTopic  = hotTopic && Date.now() < (hotTopic.expires_at || 0);

  const continueSession  = session && (session.run_count || 0) < 5;
  const usedTopics       = recentRuns.slice(-10).map(r => r.seed).filter(Boolean);
  const recentSnippets   = postedHistory.slice(-4).map(m => m.msg.slice(0, 100)).join('\n---\n');

  const sessionCtx = useHotTopic
    ? `SITUATION: React to this event happening right now.
Event: "${hotTopic.topic}"
Context: ${hotTopic.context}
CRITICAL: Everyone is an ATTENDEE or curious community member — NOT an organizer.
They ask "what are they covering?", "did anyone go?", "what did Una say?" — NEVER "we'll cover X".
Mix: excited, curious, skeptical, a newcomer asking what LingoAI is.`
    : continueSession
    ? `CONTINUE this ongoing chat (run ${(session.run_count || 0) + 1}/5).
Topic they've been discussing: "${session.topic}"
Recent messages already posted (continue naturally from here):
${recentSnippets || '(none yet)'}`
    : `START a fresh conversation about LingoAI or an AI problem it addresses.
Avoid these recent topics: ${usedTopics.slice(-8).join(' | ') || 'none yet'}
Topic ideas: ${THEMES.slice(0, 12).map(t => t.topic).join(' · ')}`;

  const overseerCtx = directive
    ? `OVERSEER NOTE (fix this): ${directive}\n`
    : '';

  // Source group pulse
  let sourceCtx = '';
  if (sourceMsgsRaw) {
    const sourceMsgs = JSON.parse(sourceMsgsRaw);
    if (sourceMsgs.length) {
      sourceCtx = `Real community pulse (mirror topics/energy, never copy verbatim):\n${sourceMsgs.slice(-10).map(m => `• ${m.text}`).join('\n')}\n`;
    }
  }

  // RL hints
  const rlHints = await getRLHints(env);
  const rlCtx   = buildRLContext(rlHints);

  // ── Agent 1+2 Combined: DirectorWriter (single AI call) ───────────────────────────────
  const direction = await conversationDirectorWriter(env, sessionCtx, overseerCtx, sourceCtx, rlCtx, postedHistory);

  if (!direction) {
    // AI parse failure — serve from static fallback directly (filtered + deduped)
    const fallbackOffTopic    = /\b(DeFi|defi|layer.?2|L2s?|arbitrum|optimism|zkSync|polygon|NFTs?|meme.?coin|altcoin|stablecoin|yield.?farm|liquidity.?pool|DAO\s+governance|token.?weighted|plutocracy|procurement\s+cycle|B2B\s+sales|investment\s+thesis|asymmetric\s+bet|priced?\s+in)\b/i;
    const fallbackCompetitor  = /\b(GPT-?4o?|gpt-?3\.?5|ChatGPT|claude\s+[23]\.\d|claude\s+opus|claude\s+sonnet|claude\s+haiku|gemini\s+(pro|flash|for|ultra)|gemini\s+\d)\b/i;
    const pool = STATIC_FALLBACK
      .filter(m => !fallbackOffTopic.test(m.msg) && !fallbackCompetitor.test(m.msg))
      .filter(m => !postedHistory.some(h => wordSimilarity(h.msg, m.msg) > 0.30))
      .sort(() => Math.random() - 0.5)
      .slice(0, count);
    if (env.KV) env.KV.put('lingo_last_error', 'DirectorWriter parse failure — served static fallback', { expirationTtl: 3600 }).catch(() => {});
    return { msgs: pool.map(m => ({ msg: m.msg, agent: 'fallback' })), turns: [], topic: 'LingoAI discussion', topic2: null, agents: [], session_run: 1, raw_count: 0, final_count: pool.length };
  }

  const rawMsgs = direction.messages || [];

  // ── Hard filters ─────────────────────────────────────────────────────────────────────
  // Match agent IDs ANYWHERE in the message (not just start) — catches "just ship it, c_wei" mid-message leaks
  const agentIdPattern  = new RegExp('\\b(' + Object.keys(PERSONAS).join('|') + ')\\b', 'i');
  const offTopicPattern = /\b(DeFi|defi|layer.?2|L2s?|arbitrum|optimism|zkSync|polygon|NFTs?|meme.?coin|altcoin|stablecoin|yield.?farm|liquidity.?pool|DAO\s+governance|token.?weighted|plutocracy|procurement\s+cycle|B2B\s+sales|business.?to.?business|enterprise.?adoption|widespread\s+adoption|governance.?design|asymmetric\s+bet|risk.?reward\s+ratio|investment\s+thesis|priced?\s+in|valuation\s+prices)\b/i;
  // Competitor AI model tool-use talk — ban "GPT-4o for X", "Claude 3.5 for X", "Gemini for X" etc inside a LingoAI group
  const competitorModelPattern = /\b(GPT-?4o?|gpt-?3\.?5|ChatGPT|claude\s+[23]\.\d|claude\s+opus|claude\s+sonnet|claude\s+haiku|gemini\s+(pro|flash|for|ultra)|gemini\s+\d|mistral\s+for|llama\s+\d+\s+for)\b/i;
  const teamSpeakPattern = /(we need to|let's focus|we should|before we can|let's get)\s+(get|fix|focus|build|improve|sort|make|ensure|see|have|consider|think about)|(we'll|we will|we're going to|we're gonna)\s+(likely|probably|touch|cover|discuss|focus|dive|address|explore)|\bwe're\s+(genuinely|really|actually|seeing|getting|observing|noticing)\s+/i;

  let msgs = rawMsgs.filter(m => {
    const t = m.msg?.trim() || '';
    if (t.length < 2) return false;
    if (/@\w+/.test(t)) return false;
    if (/^(hey guys|hi all|hello everyone)/i.test(t)) return false;
    if (agentIdPattern.test(t)) return false;
    if (offTopicPattern.test(t)) return false;
    if (competitorModelPattern.test(t)) return false;
    if (/\bfor us\b/i.test(t) && /\bdev\b/i.test(t)) return false;
    if (teamSpeakPattern.test(t)) return false;
    return true;
  });

  // Within-batch loop detector
  const conclusionPhrases = ['exchange listing', 'tokenomics', 'use cases', 'before we can', 'real-world'];
  const phraseCounts = {};
  msgs = msgs.filter(m => {
    for (const phrase of conclusionPhrases) {
      if (m.msg.toLowerCase().includes(phrase)) {
        phraseCounts[phrase] = (phraseCounts[phrase] || 0) + 1;
        if (phraseCounts[phrase] > 2) return false;
      }
    }
    return true;
  });

  // ── Agent 3: Uniqueness Guardian (max 2 rewrites) ─────────────────────────────────────
  msgs = await uniquenessGuardian(env, msgs, direction.topic, postedHistory, count);

  // Pad with static fallback if short (apply same filters as AI msgs — no bypassing)
  if (msgs.length < count) {
    const pool = STATIC_FALLBACK
      .filter(m => !offTopicPattern.test(m.msg) && !competitorModelPattern.test(m.msg) && !teamSpeakPattern.test(m.msg))
      .filter(m => !postedHistory.some(h => wordSimilarity(h.msg, m.msg) > 0.30))
      .sort(() => Math.random() - 0.5);
    for (const fbMsg of pool) {
      if (msgs.length >= count) break;
      msgs.push({ msg: fbMsg.msg, agent: 'fallback' });
    }
  }

  // ── Update session KV ─────────────────────────────────────────────────────────────────
  const isNew = !continueSession || !session;
  if (isNew) {
    await env.KV.put(KV_CONV_TOPIC, JSON.stringify({
      topic: direction.topic, topic2: null, started_at: Date.now(), run_count: 1,
    }));
  } else {
    await env.KV.put(KV_CONV_TOPIC, JSON.stringify({
      ...session, run_count: (session.run_count || 0) + 1,
    }));
  }
  await env.KV.put(KV_CONV_AGENTS, JSON.stringify(direction.agents || []));

  const recent2 = recentRuns.slice(-20);
  recent2.push({ seed: direction.topic.slice(0, 80), ts: Date.now() });
  await env.KV.put(KV_RECENT, JSON.stringify(recent2));

  return {
    msgs:        msgs.slice(0, count),
    turns:       [],
    topic:       direction.topic,
    topic2:      null,
    agents:      direction.agents,
    session_run: isNew ? 1 : ((session?.run_count || 0) + 1),
    raw_count:   rawMsgs.length,
    final_count: Math.min(msgs.length, count),
  };
}

// ── Main poster ──────────────────────────────────────────────────────────────────────────────────

export async function runLingoPoster(env, { skipSleep = false } = {}) {
  try {
    return await _runLingoPosterInner(env, { skipSleep });
  } catch (e) {
    const errStr = String(e?.stack || e);
    if (env.KV) await env.KV.put('lingo_last_error', errStr.slice(0, 1000), { expirationTtl: 3600 }).catch(() => {});
    throw e;
  }
}

async function _runLingoPosterInner(env, { skipSleep = false } = {}) {
  const chatId = await env.KV.get(KV_GROUP_ID);
  if (!chatId) {
    return { skipped: true, reason: 'No group configured. Add @AshiqAibot and type /lingosetup.' };
  }

  // Safety: never post to the source/observation group (match by numeric ID or @username)
  const sourceGroupId = await env.KV.get('lingo_source_group_id');
  if (sourceGroupId && (chatId === sourceGroupId || chatId === sourceGroupId.replace(/^@/, ''))) {
    return { skipped: true, reason: 'Target group matches source observation group — bot will not post to the official LingoAI group. Fix lingo_group_chat_id via /lingo-setup?chat_id=YOUR_POSTING_GROUP.' };
  }

  // Load posted history for deduplication + conversation continuity
  const histRaw      = await env.KV.get(KV_POSTED);
  const postedHistory = histRaw ? JSON.parse(histRaw) : [];

  // Run the 4-agent conversation pipeline: Overseer → Director → Writer → Guardian
  const result = await runConversation(env, MSGS_PER_RUN, postedHistory);
  const { msgs, turns, topic, topic2, agents, session_run, raw_count, final_count } = result;

  if (!msgs.length) return { ok: false, reason: 'Conversation pipeline returned 0 messages' };

  // Load cross-run message IDs for Telegram reply threading
  const prevMsgIdsRaw = await env.KV.get('lingo_prev_msg_ids');
  const prevMsgIds    = prevMsgIdsRaw ? JSON.parse(prevMsgIdsRaw) : [];

  let posted = 0;
  const now = Date.now();
  const newEntries      = [];
  const batchMsgIds     = []; // Telegram message_ids posted in this batch
  const msgTrackEntries = {}; // {msgId → {topic, agent, ts}} — written to KV for RL

  for (let i = 0; i < msgs.length; i++) {
    const item      = msgs[i];
    const turn      = turns[i];
    const respondsTo = turn?.responds_to;

    // Determine reply target: within-batch reply or occasional cross-run reply
    let replyToMsgId = null;
    if (respondsTo != null && batchMsgIds[respondsTo]) {
      replyToMsgId = batchMsgIds[respondsTo];
    } else if (i === 0 && prevMsgIds.length > 0 && Math.random() < 0.5) {
      replyToMsgId = prevMsgIds[prevMsgIds.length - 1];
    }

    const body = { chat_id: chatId, text: escapeHtml(item.msg), parse_mode: 'HTML' };
    if (replyToMsgId) body.reply_to_message_id = replyToMsgId;

    const tgResult = await tgCall(env, 'sendMessage', body);
    const tgMsgId  = tgResult?.message_id || null;
    batchMsgIds.push(tgMsgId);
    if (tgMsgId) {
      msgTrackEntries[String(tgMsgId)] = { topic, agent: item.agent, ts: now };
      posted++;  // only count actual TG successes
    }
    newEntries.push({ msg: item.msg, ts: now });
    if (!skipSleep && posted < msgs.length) await sleep(45000 + Math.random() * 45000); // 45-90s organic pacing
  }

  // Persist RL message tracking (keep last 200 by message_id)
  if (Object.keys(msgTrackEntries).length > 0) {
    const trackRaw = await env.KV.get(KV_MSG_TRACK);
    const track    = trackRaw ? JSON.parse(trackRaw) : {};
    Object.assign(track, msgTrackEntries);
    const trackKeys = Object.keys(track).sort((a, b) => parseInt(a) - parseInt(b));
    if (trackKeys.length > 200) {
      for (const k of trackKeys.slice(0, trackKeys.length - 200)) delete track[k];
    }
    await env.KV.put(KV_MSG_TRACK, JSON.stringify(track), { expirationTtl: 2592000 });
  }

  // Save message IDs for next run's cross-run threading (keep last 10)
  const validIds      = batchMsgIds.filter(Boolean);
  const updatedMsgIds = [...prevMsgIds, ...validIds].slice(-10);
  await env.KV.put('lingo_prev_msg_ids', JSON.stringify(updatedMsgIds));

  // Persist the rolling message history (keep last 70 — ~10 runs worth)
  const updatedHistory = [...postedHistory, ...newEntries].slice(-70);
  await env.KV.put(KV_POSTED, JSON.stringify(updatedHistory));

  const runs = parseInt((await env.KV.get(KV_SESSION)) || '0', 10);
  await env.KV.put(KV_SESSION, String(runs + 1));

  return { ok: true, posted, topic, topic2, agents, session_run, raw_generated: raw_count, after_guardian: final_count, total_runs: runs + 1, history_size: updatedHistory.length };
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ── Auto-detect group from recent updates ──────────────────────────────────────────────────
// Uses my_chat_member updates (fires when bot is added to a group — works even
// when privacy mode is ON, because privacy mode only blocks regular messages,
// not bot membership events).

async function detectLingoGroup(env) {
  if (!env.TELEGRAM_BOT_TOKEN) return null;
  try {
    // Get bot's own user ID so we can match my_chat_member events
    const meRes = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getMe`);
    const meData = await meRes.json();
    const botId = meData.ok ? meData.result.id : null;

    // Request both message types AND membership events
    const body = JSON.stringify({
      limit: 100,
      allowed_updates: ['message', 'channel_post', 'my_chat_member'],
    });
    const r = await fetch(
      `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getUpdates`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body },
    );
    const d = await r.json();
    if (!d.ok) return null;

    const groups = new Map();

    for (const upd of (d.result || [])) {
      // my_chat_member: fires when bot is added to a group (no privacy mode needed)
      if (upd.my_chat_member) {
        const mcm   = upd.my_chat_member;
        const chat  = mcm.chat;
        const newStatus = mcm.new_chat_member?.status;
        // status = "member" or "administrator" means bot was just added
        if (['member', 'administrator'].includes(newStatus)) {
          const t = chat?.type;
          if (['group', 'supergroup', 'channel'].includes(t)) {
            const id = String(chat.id);
            if (!groups.has(id)) groups.set(id, { id, title: chat.title || '', type: t, source: 'join_event' });
          }
        }
        continue;
      }

      // Fallback: regular messages (only visible when privacy mode is OFF)
      const msg = upd.message || upd.channel_post;
      if (!msg) continue;
      const t = msg.chat?.type;
      if (!['group', 'supergroup', 'channel'].includes(t)) continue;
      const id = String(msg.chat.id);
      if (!groups.has(id)) groups.set(id, { id, title: msg.chat.title || '', type: t, source: 'message' });
    }

    if (!groups.size) return null;

    // 1st priority — title contains "lingo"
    for (const [id, g] of groups) {
      if (g.title.toLowerCase().includes('lingo')) return id;
    }

    // 2nd priority — join_event groups (bot was literally just added there)
    const joinGroups = [...groups.values()].filter(g => g.source === 'join_event');
    if (joinGroups.length === 1) return joinGroups[0].id;

    // 3rd priority — only one group total
    if (groups.size === 1) return [...groups.keys()][0];

    return { ambiguous: true, groups: [...groups.values()] };
  } catch { return null; }
}

// ── Handle /lingosetup command sent inside the target group ────────────────────────────────────
// Works with both `/lingosetup` AND `/lingosetup@AshiqAibot`
// The @BotName form is delivered even when privacy mode is ON

export async function handleLingoCommand(env, msg) {
  const text = (msg.text || '').trim();
  if (!text.match(/^\/lingosetup(@\w+)?(\s|$)/i)) return false;

  const chatId = String(msg.chat.id);
  await env.KV.put(KV_GROUP_ID, chatId);

  // Confirm in the group
  await tgCall(env, 'sendMessage', {
    chat_id: chatId,
    text: '✅ <b>LingoAI poster activated!</b>\nThis group will receive AI-generated community discussions automatically every few hours.',
    parse_mode: 'HTML',
  });

  // Also notify owner
  if (env.TELEGRAM_OWNER_ID) {
    await tgCall(env, 'sendMessage', {
      chat_id: env.TELEGRAM_OWNER_ID,
      text: `✅ <b>LingoAI poster configured</b>\nGroup: <b>${escapeHtml(msg.chat.title || 'unknown')}</b>\nChat ID: <code>${chatId}</code>\nPosting starts next cron cycle.`,
      parse_mode: 'HTML',
    });
  }
  return true;
}

// ── Setup: detect or set group chat ID ─────────────────────────────────────────────────────────────

export async function setupLingoGroup(env, manualChatId = null) {
  // Manual override — user passes ?chat_id=XXXX
  if (manualChatId) {
    await env.KV.put(KV_GROUP_ID, String(manualChatId));
    return { ok: true, chat_id: manualChatId, method: 'manual', message: `Chat ID ${manualChatId} saved. Poster will start next cron cycle.` };
  }

  // Auto-detect from recent updates
  const detected = await detectLingoGroup(env);

  if (!detected) {
    return {
      ok: false,
      instructions: [
        `1. Add @AshiqAibot to your LingoAI group: ${INVITE_LINK}`,
        '2. Type /lingosetup in the group — bot saves the ID automatically',
        '   OR: call /lingo-setup?chat_id=CHAT_ID to set it manually',
      ],
    };
  }

  if (detected?.ambiguous) {
    return {
      ok: false,
      ambiguous: true,
      groups_found: detected.groups,
      instructions: 'Multiple groups found. Type /lingosetup inside the LingoAI group, or call /lingo-setup?chat_id=ID with the correct ID above.',
    };
  }

  // Single match — save it
  await env.KV.put(KV_GROUP_ID, String(detected));
  return { ok: true, chat_id: detected, method: 'auto', message: `Auto-detected group ${detected}. Poster starts next cron cycle.` };
}

// ── Status ────────────────────────────────────────────────────────────────────────────────────────────

export async function lingoStatus(env) {
  const chatId      = await env.KV.get(KV_GROUP_ID);
  const sessRaw     = await env.KV.get(KV_SESSION);
  const recentRaw   = await env.KV.get(KV_RECENT);
  const recent      = recentRaw ? JSON.parse(recentRaw) : [];
  const groqErr     = await env.KV.get('lingo_groq_err');
  const openaiErr   = await env.KV.get('lingo_openai_err');
  const xaiErr      = await env.KV.get('lingo_xai_err');
  const cfaiErr     = await env.KV.get('lingo_cfai_err');
  const tgErr       = await env.KV.get('lingo_tg_err');
  const lastError   = await env.KV.get('lingo_last_error');
  const writerRaw   = await env.KV.get('lingo_writer_raw');
  const overseerRaw = await env.KV.get(KV_OVERSEER);
  const histRaw     = await env.KV.get(KV_POSTED);
  const histSize    = histRaw ? JSON.parse(histRaw).length : 0;
  const convRaw     = await env.KV.get(KV_CONV_TOPIC);
  const conv        = convRaw ? JSON.parse(convRaw) : null;
  const agentRaw    = await env.KV.get(KV_CONV_AGENTS);
  const activeAgents = agentRaw ? JSON.parse(agentRaw) : [];

  // Source group observation
  const sourceGroupId  = await env.KV.get('lingo_source_group_id');
  const sourceMsgsRaw  = await env.KV.get(KV_SOURCE_MSGS);
  const sourceMsgCount = sourceMsgsRaw ? JSON.parse(sourceMsgsRaw).length : 0;

  // Hot topic override
  const hotTopicRaw2 = await env.KV.get(KV_HOT_TOPIC);
  const hotTopicData = hotTopicRaw2 ? JSON.parse(hotTopicRaw2) : null;
  const hotTopicActive = hotTopicData && Date.now() < (hotTopicData.expires_at || 0);

  // RL scores — show top 5 topics and agents by decay-adjusted score
  const rlHints  = await getRLHints(env);
  const trackRaw = await env.KV.get(KV_MSG_TRACK);
  const trackSize = trackRaw ? Object.keys(JSON.parse(trackRaw)).length : 0;

  return {
    configured:    !!chatId,
    chat_id:       chatId || null,
    invite_link:   INVITE_LINK,
    total_runs:    parseInt(sessRaw || '0', 10),
    msgs_per_run:  MSGS_PER_RUN,
    cron_schedule: 'every 10min (144 runs/day × 7 msgs = ~1008 msgs/day)',
    conversation_pipeline: {
      agents: [
        'Overseer (temp 0.2) — reviews last 14 msgs, scores quality 1-10, issues correction directive, resets session if score ≤ 3',
        'Director (temp 0.85) — receives overseer directive, casts 5-6 of 40 personas, designs 7-turn order',
        'Writer (temp 0.95) — writes all 7 messages in exact persona voice with reply chains',
        'Guardian — rewrites any >40% similarity match against 70-msg history',
      ],
      personas: `${Object.keys(PERSONAS).length} distinct characters across: LingoAI community holders, AI enthusiasts, crypto veterans, newcomers, wild cards`,
      ai_stack: 'Groq llama-3.3-70b-versatile (primary) → CF AI llama-3.1-8b (fallback)',
      session_model: '1-2 topics per session × up to 5 runs = 35 messages on same topic before natural shift',
    },
    current_session: conv ? {
      topic:     conv.topic,
      topic2:    conv.topic2 || null,
      run_count: conv.run_count,
      runs_left: Math.max(0, 5 - (conv.run_count || 0)),
      active_agents: activeAgents.map(id => `${id} (${PERSONAS[id]?.type || '?'})`),
    } : null,
    last_5_topics: recent.slice(-5).map(r => r.seed),
    last_error:    lastError || null,
    tg_error:      tgErr || null,
    ai_errors:     { groq: groqErr || null, openai: openaiErr || null, xai: xaiErr || null, cf_ai: cfaiErr || null },
    writer_debug:  writerRaw ? JSON.parse(writerRaw) : null,
    posted_history: { stored: histSize, capacity: 70, dedup_window: 'last 70 messages' },
    reinforcement_learning: {
      tracked_messages: trackSize,
      top_topics: rlHints.topTopics.map(t => ({ topic: t.k, score: t.pts, effective: +t.eff.toFixed(2) })),
      top_agents: rlHints.topAgents.map(a => ({ agent: a.k, score: a.pts, effective: +a.eff.toFixed(2) })),
      decay:      `score × 0.5^(days/${RL_DECAY_HALF_LIFE}) — halves every ${RL_DECAY_HALF_LIFE} days`,
    },
    source_group: {
      configured:    !!sourceGroupId,
      chat_id:       sourceGroupId || null,
      observed_msgs: sourceMsgCount,
      note:          sourceGroupId
        ? `Observing real community messages — injected into Director as live context`
        : 'Not configured — call GET /lingo-source-setup?chat_id=XXXX then add bot as admin to that group',
    },
    hot_topic: hotTopicActive ? {
      topic:      hotTopicData.topic,
      expires_at: new Date(hotTopicData.expires_at).toISOString(),
      expires_in: `${Math.round((hotTopicData.expires_at - Date.now()) / 60000)}min`,
    } : null,
    overseer: overseerRaw ? (() => {
      const o = JSON.parse(overseerRaw);
      return {
        score:     o.score,
        quality:   o.score >= 8 ? 'good' : o.score >= 5 ? 'warning' : 'critical',
        issues:    o.issues || [],
        directive: o.directive || null,
        action:    o.action || null,
        checked:   o.ts ? `${Math.round((Date.now() - o.ts) / 60000)}min ago` : null,
      };
    })() : { note: 'No overseer report yet — runs on next cron cycle' },
    next_steps:    chatId ? 'Active — conversations run every 10 minutes' : 'Call /lingo-setup?chat_id=XXXX to activate',
  };
}

// ── Static fallback (diverse across all 4 categories — used when AI fails) ────

const STATIC_FALLBACK = [
  // ── LingoAI community takes (varied lengths) ──────────────────────────────
  { cat: 'lingo', msg: 'dark data is such a weird term tbh' },
  { cat: 'lingo', msg: 'the no-burn model actually makes sense once you understand the utility sinks. took me a while' },
  { cat: 'lingo', msg: 'waiting on my lingopod. hope it ships this year' },
  { cat: 'lingo', msg: 'lingopod as a data node running ai on-device is a genuinely different idea. most projects just promise an app' },
  { cat: 'lingo', msg: 'languagedao is underrated' },
  { cat: 'lingo', msg: 'igbo and yoruba barely exist in any AI model. that\'s the actual problem lingoai is trying to fix' },
  { cat: 'lingo', msg: 'the reviewdao concept makes sense — staking on data quality. curious how you stop people gaming it though' },
  { cat: 'lingo', msg: 'metagraph + lingorag is a mouthful but it\'s basically a knowledge layer sitting on top of llm output' },
  { cat: 'lingo', msg: 'when does the hardware ship tho' },
  { cat: 'lingo', msg: 'solid protocol for personal data pods is the right idea. adoption is the question, always' },
  { cat: 'lingo', msg: '100b fixed cap, no burns. value supposed to come from demand not deflation. different approach' },
  { cat: 'lingo', msg: 'proof-of-human to stop sybil attacks on the data network — that part actually matters a lot' },
  { cat: 'lingo', msg: 'not sure any real company has actually signed up to use lingoai data yet. that\'s my main question' },
  { cat: 'lingo', msg: 'the lingoai vs bittensor comparison is interesting. different architecture assumptions' },
  { cat: 'lingo', msg: 'gm' },

  // ── AI + data quality (varied lengths) ────────────────────────────────────
  { cat: 'ai', msg: 'hallucination problem is a data problem' },
  { cat: 'ai', msg: 'on-device ai matters for privacy. your data doesn\'t need to leave your device for inference' },
  { cat: 'ai', msg: 'the dark data thing clicks when you realize most useful info — call recordings, private docs, internal wikis — never trained any public model' },
  { cat: 'ai', msg: 'open source models are catching up fast but they still need better training data to close the remaining gap' },
  { cat: 'ai', msg: 'who actually owns the data that trained these models' },
  { cat: 'ai', msg: 'minority languages barely exist in any model. tokenization for non-latin scripts is still genuinely bad' },
  { cat: 'ai', msg: 'ai agents need structured, clean, retrievable context to work properly. that\'s basically what a data layer is supposed to provide' },
  { cat: 'ai', msg: '95% dark data isn\'t marketing. most useful data really is locked in places no model can reach' },
  { cat: 'ai', msg: 'solid protocol. anyone actually using it in production?' },
  { cat: 'ai', msg: 'context windows got huge but models still lose the thread. bigger window doesn\'t mean better understanding' },
  { cat: 'ai', msg: 'facts' },
  { cat: 'ai', msg: 'multilingual ai is harder than people think. it\'s not just translation, it\'s how the model represents the concepts underneath' },
  { cat: 'ai', msg: 'data quality problem is real. garbage in, garbage out — applies at every scale' },
  { cat: 'ai', msg: 'the gap between ai demos and production reliability is still huge. demos always work' },
  { cat: 'ai', msg: 'nah' },
];
