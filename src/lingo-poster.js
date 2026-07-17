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
  y_tanaka:  { type: 'hardware engineer who pre-ordered LingoPOD', voice: 'deep on device specs, latency, edge compute. Interested but has real doubts about hardware timelines. Asks pointed questions about power consumption and supply chain.' },
  r_hassan:  { type: 'B2B sales guy watching $LINGOAI closely', voice: 'thinks in deals and procurement cycles. Skeptical about whether enterprise clients will actually pay in $LINGOAI. Grounded, not promotional. Has seen vendor promises fail before.' },
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
  c_fox:     { type: 'NFT-turned-DAO governance nerd', voice: 'started with NFTs, now obsessed with governance design. Sees community coordination as the real product.' },
  a_singh:   { type: 'Indian crypto influencer',   voice: 'high energy. Practical about fees and speed. Solana ecosystem. References Indian retail market a lot.' },
  t_nguy:    { type: 'institutional crypto (ex-Goldman)', voice: 'TradFi lens. Regulatory-aware. Speaks in risk and compliance terms. Measured. Doesn\'t hype.' },
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

// 50 themes across 4 categories — 50 × 10 = 500 messages per batch
// category: 'lingo' | 'ai' | 'web3' | 'trending'
const THEMES = [
  // ── LingoAI (20) ────────────────────────────────────────────────────────────────────────────
  { topic: 'token economics, utility sinks, and why there are no token burns',                                             cat: 'lingo' },
  { topic: 'LingoPOD hardware features, corpus mining, and the DePIN network',                                            cat: 'lingo' },
  { topic: 'language diversity mission and why second/third-tier languages are ignored by AI',                             cat: 'lingo' },
  { topic: 'MetaGraph architecture and how it eliminates AI hallucinations for enterprises',                               cat: 'lingo' },
  { topic: 'comparing LingoAI to Scale AI, Helium, FET, Ocean Protocol, and Bittensor',                                   cat: 'lingo' },
  { topic: 'ReviewDAO and LanguageDAO governance models and contributor economics',                                        cat: 'lingo' },
  { topic: 'newcomers asking LingoAI questions and experienced holders answering naturally',                               cat: 'lingo' },
  { topic: '$16B data market opportunity, DePIN cost advantage, and $LINGOAI value thesis',                               cat: 'lingo' },
  { topic: 'LingoRAG technical architecture: ontologies, multi-agent query decomposition',                                cat: 'lingo' },
  { topic: 'LingoPOD as a personal data sovereignty device — Solid protocol, digital twin',                               cat: 'lingo' },
  { topic: '$LINGOAI fixed 100B supply, no dilution, no burns — structural scarcity explained',                           cat: 'lingo' },
  { topic: 'B2B data escrow mechanics — enterprises pay fiat, triggering $LINGOAI buybacks',                             cat: 'lingo' },
  { topic: 'DePIN passive income: LingoWatch, LingoRing, LingoGlass, LingoPin earning $LINGOAI daily',                   cat: 'lingo' },
  { topic: 'hardware bonding mechanics — how LingoPOD pre-orders lock circulating supply',                                cat: 'lingo' },
  { topic: 'dark data: 95% of global data trapped in silos — LingoAI unlocks all of it',                                 cat: 'lingo' },
  { topic: 'LanguageDAO — minority communities owning and monetizing their own linguistic corpus',                         cat: 'lingo' },
  { topic: 'proof-of-human protocol in LingoPOD — fighting bots and sybil attacks in Web3',                              cat: 'lingo' },
  { topic: 'on-device edge LLM in LingoPOD vs cloud AI — privacy, latency, data ownership',                              cat: 'lingo' },
  { topic: 'LingoAI 2030 vision: global multilingual AI data infrastructure',                                             cat: 'lingo' },
  { topic: 'real talk: accumulation strategy for $LINGOAI and upcoming catalyst events',                                  cat: 'lingo' },

  // ── General AI (10) ────────────────────────────────────────────────────────────────────────────
  { topic: 'ChatGPT vs Claude vs Gemini vs Grok — which AI is actually best right now',                                  cat: 'ai' },
  { topic: 'AI agents and autonomous systems — where this is heading in 2025 and beyond',                                 cat: 'ai' },
  { topic: 'open source AI models vs closed models: Llama, Mistral, Qwen vs GPT-4o, Claude',                             cat: 'ai' },
  { topic: 'AI hallucination problem — why LLMs still confidently make things up',                                       cat: 'ai' },
  { topic: 'edge AI and on-device LLMs — phones running models locally without internet',                                 cat: 'ai' },
  { topic: 'AI replacing jobs — which roles are actually at risk vs which ones are safe',                                 cat: 'ai' },
  { topic: 'AI regulation globally — EU AI Act, US executive orders, China vs the West',                                  cat: 'ai' },
  { topic: 'multimodal AI (vision, voice, video generation) — what is impressive and what is hype',                      cat: 'ai' },
  { topic: 'AI memory and context — why LLMs forget and how long-term memory is being solved',                           cat: 'ai' },
  { topic: 'AI coding assistants — Cursor, Copilot, Claude Code — which actually makes devs faster',                    cat: 'ai' },

  // ── General Web3 (10) ───────────────────────────────────────────────────────────────────────────
  { topic: 'DeFi yield strategies in 2025 — what is working, what is risky, where to look',                              cat: 'web3' },
  { topic: 'Layer 2 scaling wars — Arbitrum vs Optimism vs Base vs zkSync — who wins',                                  cat: 'web3' },
  { topic: 'DePIN sector: Helium, Render, Hivemapper, Grass — the passive income thesis',                               cat: 'web3' },
  { topic: 'Solana vs Ethereum for builders — ecosystems, tooling, fees, community',                                     cat: 'web3' },
  { topic: 'RWA (real world assets) on-chain — tokenized treasuries, real estate, credit',                              cat: 'web3' },
  { topic: 'Web3 gaming in 2025 — what GameFi 2.0 looks like vs the 2021 P2E era',                                     cat: 'web3' },
  { topic: 'crypto wallet security — seed phrases, hardware wallets, phishing — how to stay safe',                       cat: 'web3' },
  { topic: 'stablecoins landscape — USDT vs USDC vs DAI vs new entrants — risks and trade-offs',                        cat: 'web3' },
  { topic: 'DAO governance in practice — what actually works and what kills participation',                               cat: 'web3' },
  { topic: 'NFT evolution — PFPs are dead, what NFTs become in utility, gaming, IP licensing',                           cat: 'web3' },

  // ── Trending Topics (10) ──────────────────────────────────────────────────────────────────────────
  { topic: 'AI crypto tokens price action and fundamentals: $FET, $RNDR, $TAO, $OCEAN, $WLD',                           cat: 'trending' },
  { topic: 'BlackRock and institutional Bitcoin/ETH adoption — what it actually means for retail',                       cat: 'trending' },
  { topic: 'altcoin season signals — how to spot the rotation early and which sectors run first',                        cat: 'trending' },
  { topic: 'AI + crypto convergence: autonomous AI agents running DeFi wallets in 2025',                                 cat: 'trending' },
  { topic: 'meme coins culture — why communities form around them and how to tell signal from noise',                    cat: 'trending' },
  { topic: 'prediction markets going mainstream — Polymarket, Kalshi, and what that means for info',                    cat: 'trending' },
  { topic: 'crypto bear market survival tactics — DCA, staking, portfolio allocation psychology',                        cat: 'trending' },
  { topic: 'Elon Musk, X (Twitter), xAI and Grok — the intersection of social media and crypto',                       cat: 'trending' },
  { topic: 'central bank digital currencies (CBDCs) — threat to crypto or irrelevant',                                  cat: 'trending' },
  { topic: 'crypto alpha sources — best channels, newsletters, on-chain analytics tools to follow',                     cat: 'trending' },
];

// ── Telegram helper ─────────────────────────────────────────────────────────────────────────────────

async function tgCall(env, method, body = {}) {
  if (!env.TELEGRAM_BOT_TOKEN) return null;
  try {
    const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    return d.ok ? d.result : null;
  } catch { return null; }
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
  const models = ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'llama3-70b-8192', 'llama3-8b-8192'];
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
  try { return JSON.parse(m[0]); } catch { return null; }
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
// CONVERSATION PIPELINE — 3 agents simulate 40 real humans chatting
//
//  ┌──────────────────────┐    ┌─────────────────────────┐    ┌────────────────┐
//  │   DIRECTOR           │ →  │       WRITER             │ →  │   GUARDIAN     │
//  │  temp 0.85           │    │      temp 0.95            │    │  rewrites dups │
//  │  Reads session KV    │    │  Writes 7 messages in     │    │  never lets a  │
//  │  Continues or starts │    │  the EXACT voice of each  │    │  repeat post   │
//  │  a new conversation  │    │  selected agent — reply   │    │                │
//  │  Selects 5-6 of 40   │    │  chains, mixed lengths,   │    │                │
//  │  personas            │    │  organic casual tone      │    │                │
//  │  Designs turn order  │    │                           │    │                │
//  └──────────────────────┘    └─────────────────────────┘    └────────────────┘
//
//  Session management: 1-2 topics per conversation session (4-6 runs = ~40-60min)
//  then Director naturally shifts to a new conversation with different agents
// ═══════════════════════════════════════════════════════════════════════════

// ── AGENT 1: CONVERSATION DIRECTOR ──────────────────────────────────────────────────────────────────
// Casts 5-6 personas and designs a loose turn order — NO rigid "angles".
// Writer invents what each person says from their voice + the live conversation.

async function conversationDirector(env, postedHistory) {
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
    ? `START a NEW conversation. A LIVE EVENT is happening right now — make it the topic.
Event: "${hotTopic.topic}"
Context (use naturally, don't quote verbatim): ${hotTopic.context}
Have people react as if someone in the group just posted about this or they just saw it. Some are excited, some ask questions, one might be skeptical about the "data sovereignty" angle, a newcomer asks what LingoAI actually is. Keep it organic — NOT a formal announcement.`
    : continueSession
    ? `CONTINUE this chat (run ${(session.run_count || 0) + 1} of 5).
Topic: "${session.topic}"
Active personas: ${activeAgents.slice(0, 6).join(', ')}
Last messages already posted:
${recentSnippets || '(none yet)'}`
    : `START a fresh conversation.
Avoid these recent topics: ${usedTopics.slice(-8).join(' | ') || 'none yet'}`;

  const rlHints   = await getRLHints(env);
  const rlCtx     = buildRLContext(rlHints);
  const sourceCtx = await getSourceContext(env);

  const prompt = `You are casting a casual Telegram group chat. Pick who speaks and in what order for the next 7 messages.

${sessionCtx}
${sourceCtx}
${rlCtx}
AVAILABLE PERSONAS:
${personaCatalogue}

Pick 5-6 personas that fit the topic. Design a loose turn order — like a real chat, not a structured debate.
CASTING NOTES:
- LingoAI holders are community members with opinions — NOT project reps. Cast them when they'd naturally have something personal to say, not to explain the project
- Mix enthusiasts and skeptics, even on LingoAI topics — one person might push back or ask the hard question
- For LingoAI topics, prefer personas who have personal stakes (someone who bought LingoPOD, someone waiting on a feature, someone frustrated about price) over generic "insider" framing
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

// ── AGENT 2: CONVERSATION WRITER ─────────────────────────────────────────────────────────────────
// Writes all messages as natural Telegram chat — no rigid angles.
// Each message is invented from the persona's voice + what's already been said.

async function conversationWriter(env, direction, postedHistory) {
  const selectedIds = direction.agents || [];
  const prevMsgs    = postedHistory.slice(-5).map(m => m.msg).join('\n---\n');

  const voiceProfiles = selectedIds
    .filter(id => PERSONAS[id])
    .map(id => `${id} [${PERSONAS[id].type}]: ${PERSONAS[id].voice}`)
    .join('\n\n');

  const lingoIds = ['s_chen','m_webb','p_patel','j_kim','v_silva','a_turner','y_tanaka','r_hassan','c_adeyemi','l_zhang'];
  const needsLingo = selectedIds.some(id => lingoIds.includes(id))
    || (direction.topic || '').toLowerCase().includes('lingo');
  const lingoCtx = needsLingo ? `\nLingoAI background knowledge (what these people already know — NOT facts to recite, just informs what they mention naturally in conversation):\n${LINGO_FACTS}\n` : '';

  const turns = direction.turns || [];
  const turnList = turns.map((t, i) => {
    const lenGuide = t.length === 'micro' ? '1-5 words' : t.length === 'short' ? '1 sentence' : t.length === 'long' ? '3-5 sentences' : '2-3 sentences';
    const replyNote = t.responds_to != null ? ` [replies to msg ${t.responds_to}]` : '';
    return `[${i}] ${t.agent}${replyNote} — ${lenGuide}`;
  }).join('\n');

  const prompt = `Write a real Telegram group chat. These ${turns.length} people are actually talking — casual, unscripted, human.

Topic drifting around: "${direction.topic}"
${lingoCtx}
${prevMsgs ? `Chat already in progress (DON'T repeat these):\n---\n${prevMsgs}\n---\n` : ''}
VOICES (write each person in their exact voice):
${voiceProfiles}

WHO SPEAKS NEXT:
${turnList}

CRITICAL RULES — break these and the whole thing fails:
1. These are COMMUNITY MEMBERS with personal opinions — not the project team, not spokespersons
2. LingoAI holders can be excited AND doubtful AND frustrated in the same conversation. That's normal
3. NEVER: "LingoAI is revolutionizing...", "This is why $LINGOAI is special", reciting bullet points as facts
4. DO: "tbh the no-burn model confused me at first", "anyone actually used LingoRAG in prod?", "price has been flat for weeks tho", "i get the vision but the hardware timeline worries me"
5. Disagreement, honest questions, and "wait but..." moments make conversations feel real
6. micro = literally 1-5 words ("gm", "facts", "nah", "wait what", "this")
7. if replying, react to the SPECIFIC thing said — not a new point
8. no @mentions, no name tags, lowercase, contractions
9. each person sounds DIFFERENT — don't let them blur into each other

EXAMPLE of the energy we want (different topic, just showing naturalness):
[0] gm
[1] anyone else think AI memory is the most underrated unsolved problem
[2] 100%. every new chat starts cold
[3] to be fair there's RAG and vector stores — issue is retrieval quality not storage
[4] ok but why does it still hallucinate stuff from "past" sessions tho
[5] because context window ≠ memory. it's a very long prompt not actual recall
[6] so basically every AI assistant has anterograde amnesia lol

Return ONLY a JSON array:
[{"msg":"text","agent":"agent_id"},...]`;

  const raw    = await callRaw(env, prompt, { temperature: 0.95, maxTokens: 1600 });

  // Debug: log raw output length + preview so /lingo-status can show what happened
  if (env.KV) await env.KV.put('lingo_writer_raw',
    JSON.stringify({ len: raw.length, preview: raw.slice(0, 400) }),
    { expirationTtl: 3600 }
  );

  const parsed = parseJSON(raw);

  if (Array.isArray(parsed) && parsed.length > 0) {
    return parsed
      .filter(m => typeof m.msg === 'string' && m.msg.trim().length > 1)
      .map(m => ({ msg: m.msg.trim(), agent: m.agent || 'unknown' }));
  }

  // Bulk generation failed — fall back to generating each message individually.
  // Smaller prompts (< 300 tokens each) are far more reliable across all AI providers.
  if (env.KV) await env.KV.put('lingo_writer_raw',
    JSON.stringify({ len: raw.length, preview: raw.slice(0, 400), fallback: 'one_by_one' }),
    { expirationTtl: 3600 }
  );
  return writeMessagesOneByOne(env, direction, postedHistory);
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

async function uniquenessGuardian(env, messages, topic, postedHistory) {
  if (!postedHistory.length) return messages;
  const result = [];
  for (const msg of messages) {
    const dup = postedHistory.find(h => wordSimilarity(h.msg, msg.msg) > 0.40);
    if (!dup) { result.push(msg); continue; }
    const fresh = await rewriteMessage(env, msg.msg, topic, postedHistory);
    if (fresh) result.push({ ...msg, msg: fresh });
  }
  return result;
}

// ── CONVERSATION RUNNER ──────────────────────────────────────────────────────────────────────────
// Director → Writer → Guardian, with session + history tracking

async function runConversation(env, count, postedHistory = []) {
  // ── Agent 1: Director ──────────────────────────────────────────────────────────────────
  const direction = await conversationDirector(env, postedHistory);

  // ── Agent 2: Writer ───────────────────────────────────────────────────────────────────
  const raw = await conversationWriter(env, direction, postedHistory);

  // Hard filter: remove @mentions and blank/single-word messages; allow "gm", one-liners
  let msgs = raw.filter(m =>
    !/@\w+/.test(m.msg) &&
    m.msg.trim().length >= 2 &&
    !/^(hey guys|hi all|hello everyone)/i.test(m.msg)
  );

  // ── Agent 3: Uniqueness Guardian ───────────────────────────────────────────────────────────
  msgs = await uniquenessGuardian(env, msgs, direction.topic, postedHistory);

  // Pad if short — rewrite static fallback messages rather than posting verbatim
  if (msgs.length < count) {
    const pool = STATIC_FALLBACK
      .filter(m => !postedHistory.some(h => wordSimilarity(h.msg, m.msg) > 0.30))
      .sort(() => Math.random() - 0.5);
    for (const fbMsg of pool) {
      if (msgs.length >= count) break;
      const fresh = await rewriteMessage(env, fbMsg.msg, direction.topic, postedHistory);
      if (fresh) msgs.push({ msg: fresh, agent: 'fallback' });
    }
  }

  // ── Update conversation session ──────────────────────────────────────────────────────────────────
  const sessionRaw = await env.KV.get(KV_CONV_TOPIC);
  const session    = sessionRaw ? JSON.parse(sessionRaw) : null;

  if (direction.is_new_session || !session) {
    await env.KV.put(KV_CONV_TOPIC, JSON.stringify({
      topic:     direction.topic,
      topic2:    direction.topic2 || null,
      started_at: Date.now(),
      run_count: 1,
    }));
  } else {
    await env.KV.put(KV_CONV_TOPIC, JSON.stringify({
      ...session,
      run_count: (session.run_count || 0) + 1,
      topic2:    direction.topic2 || session.topic2,
    }));
  }
  await env.KV.put(KV_CONV_AGENTS, JSON.stringify(direction.agents || []));

  // ── Update topic history (for Director's "avoid repeating" context) ──────────────────────
  const recentRaw = await env.KV.get(KV_RECENT);
  const recent    = recentRaw ? JSON.parse(recentRaw) : [];
  recent.push({ seed: direction.topic.slice(0, 80), ts: Date.now() });
  await env.KV.put(KV_RECENT, JSON.stringify(recent.slice(-20)));

  return {
    msgs:        msgs.slice(0, count),
    turns:       direction.turns || [],  // passed to poster for reply threading
    topic:       direction.topic,
    topic2:      direction.topic2 || null,
    agents:      direction.agents,
    session_run: direction.is_new_session ? 1 : ((session?.run_count || 0) + 1),
    raw_count:   raw.length,
    final_count: Math.min(msgs.length, count),
  };
}

// ── Main poster ──────────────────────────────────────────────────────────────────────────────────

export async function runLingoPoster(env) {
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

  // Run the 3-agent conversation pipeline: Director → Writer → Guardian
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
    }
    newEntries.push({ msg: item.msg, ts: now });
    posted++;
    if (posted < msgs.length) await sleep(45000 + Math.random() * 45000); // 45-90s organic pacing
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
  const writerRaw   = await env.KV.get('lingo_writer_raw');
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
        'Director (temp 0.85) — reads session KV, casts 5-6 of 40 personas, designs 7-turn order',
        'Writer (temp 0.95) — writes all 7 messages in exact persona voice with reply chains',
        'Guardian — rewrites any >40% similarity match against 70-msg history',
      ],
      personas: `${Object.keys(PERSONAS).length} distinct characters across: LingoAI insiders, AI enthusiasts, crypto veterans, newcomers, wild cards`,
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
    next_steps:    chatId ? 'Active — conversations run every 10 minutes' : 'Call /lingo-setup?chat_id=XXXX to activate',
  };
}

// ── Static fallback (diverse across all 4 categories — used when AI fails) ────

const STATIC_FALLBACK = [
  // lingo
  { cat: 'lingo', msg: 'Just read the LingoAI whitepaper. The "no token burn" model actually makes more sense than I expected — the utility sinks replace burns entirely.' },
  { cat: 'lingo', msg: 'LingoRAG + MetaGraph for language ontologies is genuinely different from every other AI project I\'ve seen. This isn\'t GPT wrapper #5000.' },
  { cat: 'lingo', msg: '95% dark data unlocked = the entire addressable market for $LINGOAI just waiting to be captured. Timing is perfect.' },
  { cat: 'lingo', msg: 'LingoPOD as a DePIN node that pays you to collect real-world data while running your personal AI on-device. The hardware moat is real.' },
  { cat: 'lingo', msg: 'B2B procurement escrow keeps a constant % of supply locked in active business transactions. That\'s structural, not speculative.' },
  { cat: 'lingo', msg: 'MetaGraph eliminates hallucinations through knowledge graph structure + staked verification. Enterprises terrified of LLM errors will pay a premium for this.' },
  { cat: 'lingo', msg: 'As someone from a country where our language is ignored by all major AI models, LingoAI feels personal. LanguageDAO is the right model.' },
  { cat: 'lingo', msg: 'Fixed supply + infinite data value growth = token price must appreciate. That\'s the mathematical core of the $LINGOAI thesis.' },
  { cat: 'lingo', msg: 'ReviewDAO with staked collateral for data quality is exactly the right incentive design. Bad data gets slashed. Quality compounds.' },
  { cat: 'lingo', msg: 'When all the hardware bonds hit at LingoPOD launch, circulating supply is going to drop hard. Watch the float carefully.' },

  // ai
  { cat: 'ai', msg: 'Claude 3.5 Sonnet for coding, GPT-4o for general tasks, Gemini for long context. At this point we\'re all running different models for different jobs lol' },
  { cat: 'ai', msg: 'Honestly the open source models have closed the gap way faster than anyone predicted. Llama 3.3 70B is competitive with GPT-4 from a year ago.' },
  { cat: 'ai', msg: 'The hallucination problem isn\'t going away with scale. It\'s a data quality issue. Models trained on garbage confidently output garbage.' },
  { cat: 'ai', msg: 'On-device AI is going to be massive. Your phone running a capable LLM locally with your personal data never leaving your device — that\'s the future.' },
  { cat: 'ai', msg: 'AI agents that can actually browse, code, and take actions autonomously — we\'re not there yet but 2025 is moving fast. Watch the agent frameworks.' },
  { cat: 'ai', msg: 'EU AI Act is going to hit US AI companies harder than people realize. The compliance overhead for "high risk" systems is brutal.' },
  { cat: 'ai', msg: 'Cursor changed how I code. I don\'t use an IDE without AI completion anymore. The productivity delta is too real to ignore.' },
  { cat: 'ai', msg: 'The multimodal stuff (vision + voice + video) is impressive in demos but still inconsistent in production. We\'re in the "impressive prototype" phase.' },
  { cat: 'ai', msg: 'AI replacing jobs debate: it\'s not about replacing jobs, it\'s about one person doing the work of five. That\'s what companies are quietly figuring out.' },
  { cat: 'ai', msg: 'Long context windows solved one problem but created another — models still lose coherence past a certain point. Context != understanding.' },

  // web3
  { cat: 'web3', msg: 'Base TVL growth this year has been wild. Coinbase quietly building the most accessible L2 while everyone debates Arbitrum vs Optimism.' },
  { cat: 'web3', msg: 'DePIN is the narrative I\'m most bullish on right now. Physical infrastructure + token incentives + real utility. Helium proved the model works.' },
  { cat: 'web3', msg: 'Real World Assets on-chain is moving faster than most people realize. Tokenized treasuries already doing billions in volume. This is early.' },
  { cat: 'web3', msg: 'DAO governance participation is the biggest unsolved problem in Web3. Token-weighted voting consistently produces plutocracy. We need better models.' },
  { cat: 'web3', msg: 'NFTs aren\'t dead — they\'re just not JPEGs anymore. Gaming items, ticketing, IP licensing. The use cases are finally getting real.' },
  { cat: 'web3', msg: 'DeFi yields came back. If you know where to look, there\'s still 15-20% APY on stablecoins with manageable risk. Not 2021 numbers but not nothing.' },
  { cat: 'web3', msg: 'Your seed phrase IS your money. One phishing click away from losing everything. Use hardware wallets. Don\'t connect to sketchy dApps. Stay paranoid.' },
  { cat: 'web3', msg: 'Solana developer experience has genuinely improved. Still prefer EVM for the ecosystem but Solana TPS and fees make a strong argument for certain use cases.' },
  { cat: 'web3', msg: 'USDC vs USDT risk profile is very different. USDC has regulatory clarity, USDT has Tether\'s reserves question. Know what you\'re holding.' },
  { cat: 'web3', msg: 'Web3 gaming is finally building actual games first, token economies second. That\'s the right order. The P2E model where the game IS the extraction failed.' },

  // trending
  { cat: 'trending', msg: '$TAO is interesting but the valuation already prices in a lot of the AI data narrative. $LINGOAI might be the more asymmetric bet on the same thesis.' },
  { cat: 'trending', msg: 'BlackRock tokenizing everything tells you where this goes. When the largest asset manager on earth is building on-chain, the direction is set.' },
  { cat: 'trending', msg: 'AI agents with their own crypto wallets executing DeFi strategies autonomously — this is already happening. The agent economy is not hypothetical.' },
  { cat: 'trending', msg: 'Altcoin season rotation signal: BTC dominance dropping + ETH/BTC ratio rising = alts getting the liquidity next. Watch the dominance chart.' },
  { cat: 'trending', msg: 'Polymarket being right about almost everything before mainstream media catches on is wild. Prediction markets are genuinely useful information aggregators.' },
  { cat: 'trending', msg: 'Meme coins aren\'t going away. They\'re community coordination mechanisms with speculation layered on top. DOGE proved the cultural staying power.' },
  { cat: 'trending', msg: 'CBDC vs crypto: governments want programmable money that they control. That\'s literally the opposite of what Bitcoin was built to prevent.' },
  { cat: 'trending', msg: 'For on-chain alpha: Nansen for wallet tracking, Dune for custom queries, DefiLlama for TVL, Coinglass for futures data. That\'s the stack.' },
  { cat: 'trending', msg: 'The AI crypto sector ($FET, $OCEAN, $RNDR, $TAO) is repricing relative to the broader AI stock rally. Convergence trade is real.' },
  { cat: 'trending', msg: 'Bear market DCA thesis: accumulate the projects with real revenue, real users, and teams that shipped through the last bear. Filter is simple. Execution isn\'t.' },
];
