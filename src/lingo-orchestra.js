// ─────────────────────────────────────────────────────────────────────────────
// LingoAI AI Orchestra — Multi-Agent Community Bot
// Powered by Groq llama-3.3-70b-versatile (primary) + CF Workers AI (fallback)
// No external API dependencies beyond what's already deployed.
//
// Architecture:
//   Maestro → Researcher → [HypeWriter + AnalystWriter + CommunityWriter] → Judge → Post
//   (Writers run in parallel; Judge picks best N with diversity enforcement)
// ─────────────────────────────────────────────────────────────────────────────

const BOT_USERNAME = 'AshiqAibot';

// ── LingoAI Knowledge Base ────────────────────────────────────────────────────
const LINGOAI_KB = `
=== LingoAI — MASTER KNOWLEDGE BASE ===

CORE PHILOSOPHY:
- "Web3.0 = Data 3.0 + Finance 3.0" — LingoAI unifies the data economy with decentralized finance
- Token = "Digital Receipt" for humanity's collective intelligence
- "数通天下" (Data Connects the World) — the founding mantra
- Mission: democratize AI for the world's 7,000+ languages (mainstream AI covers ~100)

TOKEN ($LINGOAI):
- Hard cap: 100 billion tokens — NO burns, ever. Fixed supply + growing demand = appreciation.
- Not deflationary by design: value comes from real utility growth, not artificial scarcity
- Multiple demand drivers create sustained buy pressure from real economic activity

FIVE TOKEN SINK MECHANISMS (reduce circulating supply):
1. ReviewDAO Staking — validators stake $LINGOAI to participate in data quality review; bad data = slashed stake
2. B2B Data Escrow — enterprise AI labs lock tokens in smart contracts during dataset procurement
3. Personal Data Pod Deposits — every user maintains minimum token balance to keep their data pod active
4. MetaGraph Knowledge Node Collateral — minting Knowledge Nodes requires locking tokens as truth collateral
5. DePIN Hardware Bond — LingoPOD owners must bond tokens to activate their device as a corpus mining node

TOKEN DEMAND DRIVERS:
- Enterprise AI labs (like OpenAI, Google, etc.) MUST buy $LINGOAI to license multilingual datasets
- MetaGraph-as-a-Service subscriptions paid in tokens
- Corpus mining rewards drive DePIN node operator demand
- Fiat B2B revenue → Foundation buys back $LINGOAI from open market (direct buy pressure)
- AI training data market: $3.2B now → $16B+ by 2034 (5x growth runway)

PRODUCTS IN DETAIL:
1. LingoRAG — RAG (Retrieval Augmented Generation) platform. Multi-agent, multilingual, multimodal.
   Connects LLMs to verified knowledge graphs — eliminates hallucinations at retrieval layer.

2. LingoGraph — Structured semantic ontologies for language understanding.
   Gives LLMs precise context through data relationships rather than raw text.

3. MetaGraph — The "Truth Engine." Metaontology that maps ALL knowledge sources.
   Every fact is staked: wrong claim = slashed collateral. AI literally cannot afford to hallucinate.
   Extended by community via staked Knowledge Nodes. Multi-agent dispatch system.

4. LingoPOD — Wearable DePIN hardware family:
   • LingoGlass — smart glasses with embedded edge AI + camera
   • LingoWatch — smartwatch with always-on corpus mining
   • LingoRing — minimalist ring with passive data collection
   • LingoPin — wearable pin/badge for ambient environment capture

LINGOPOD TECHNICAL FEATURES:
- On-device (edge) LLM — AI runs locally, not in the cloud
- Personal Data Pod (Solid protocol) — YOUR data stays on YOUR device, you control it
- Decentralized identity management via blockchain
- Autonomous Digital Twin — AI agent that acts on your behalf 24/7
- Proof-of-Human Protocol — cryptographically verifies you're a real person
- "Phygical" (physical+digital) reality — bridges real world data to blockchain
- DePIN corpus mining — your device passively collects embodied AI + IoT training data

DATA ECONOMY THESIS:
- 95% of global data is "Dark Data" — trapped in corporate silos, never monetized
- Solid protocol Personal Data Pods "clear" this dark data for market use
- "1+1>2 data nuclear fusion" — clinical data + wearable data = exponentially more valuable together
- Decentralized collection is 10x more cost-efficient than Scale AI (no central workforce)
- Community-driven RLHF fine-tuning outperforms lab-controlled fine-tuning for rare languages

GOVERNANCE:
- ReviewDAO — staked validators verify data quality; earn rewards for good reviews, lose stake for bad ones
- LanguageDAO — language communities own, govern, and monetize their own linguistic corpus
- Token-weighted governance: long-term holders make decisions, short-term traders don't

COMPETITIVE ADVANTAGES:
- vs Scale AI: 10x cheaper via DePIN decentralized collection; also has token layer Scale doesn't
- vs Ocean Protocol: has the AI model + inference layer (MetaGraph, LingoRAG) that Ocean lacks
- vs Fetch.ai (FET): has the real-world data collection infrastructure FET doesn't have
- vs Bittensor (TAO): has physical DePIN wearables + real-world embodied data; TAO is compute-only
- vs WorldCoin: privacy-preserving (data never leaves your device); WorldCoin centralizes biometrics
- vs Helium: Helium does wireless connectivity DePIN; LingoAI does AI data DePIN — different layer
- Unique position: ONLY project that combines DePIN hardware + data marketplace + AI inference + DAO governance

REVENUE MODEL:
- B2B dataset licensing (enterprises pay in $LINGOAI or fiat → buyback)
- MetaGraph-as-a-Service API subscriptions
- DePIN hardware sales (LingoPOD devices)
- ReviewDAO review fees (percentage of each data transaction)
- LanguageDAO corpus commercialization (communities earn, LingoAI takes small fee)
`;

// ── AI Callers ────────────────────────────────────────────────────────────────

async function callGroq(env, system, user, { maxTokens = 2000, temperature = 0.85 } = {}) {
  if (!env.GROQ_API_KEY) return null;
  // Try models in order — fallback if one is overloaded
  const models = ['llama-3.3-70b-versatile', 'llama-3.1-70b-versatile', 'mixtral-8x7b-32768'];
  const base   = env.CF_GW_BASE ? `${env.CF_GW_BASE}/groq/openai` : 'https://api.groq.com/openai';
  for (const model of models) {
    try {
      const r = await fetch(`${base}/v1/chat/completions`, {
        method:  'POST',
        headers: { 'Authorization': `Bearer ${env.GROQ_API_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model,
          max_tokens:  maxTokens,
          temperature,
          messages: [
            { role: 'system', content: system },
            { role: 'user',   content: user   },
          ],
        }),
      });
      const d    = await r.json();
      const text = d.choices?.[0]?.message?.content;
      if (text) return text;
    } catch {}
  }
  return null;
}

async function callCFAI(env, system, user, { maxTokens = 1500 } = {}) {
  if (!env.AI) return null;
  const models = [
    '@cf/meta/llama-3.3-70b-instruct-fp8-fast',
    '@cf/meta/llama-3.1-70b-instruct',
  ];
  for (const model of models) {
    try {
      const r = await env.AI.run(model, {
        messages:   [{ role: 'system', content: system }, { role: 'user', content: user }],
        max_tokens: maxTokens,
      });
      if (r?.response) return r.response;
    } catch {}
  }
  return null;
}

// Primary router: Groq (larger context, faster) → CF AI fallback
async function ai(env, system, user, { maxTokens = 2000, temperature = 0.85 } = {}) {
  const g = await callGroq(env, system, user, { maxTokens, temperature });
  if (g) return g;
  const c = await callCFAI(env, system, user, { maxTokens: Math.min(maxTokens, 1500) });
  return c || '';
}

// ── JSON parser with AI self-repair ──────────────────────────────────────────
function tryParseJSON(raw) {
  if (!raw) return null;
  try {
    const m = raw.match(/[\[{][\s\S]*[\]}]/);
    return m ? JSON.parse(m[0]) : null;
  } catch { return null; }
}

// If first parse fails, ask the AI to fix its own output
async function parseJSONWithRepair(env, raw, schema) {
  const first = tryParseJSON(raw);
  if (first) return first;
  const fixed = await ai(env,
    `You are a JSON fixer. The user provides broken JSON text. Extract and return ONLY valid JSON matching: ${schema}. No markdown, no explanation.`,
    `Fix this and return valid JSON only:\n${raw}`,
    { maxTokens: 800, temperature: 0.1 }
  );
  return tryParseJSON(fixed);
}

// ── Helper ────────────────────────────────────────────────────────────────────
function sleep(ms)       { return new Promise(r => setTimeout(r, ms)); }
function escHtml(s)      { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function shuffle(arr)    { return [...arr].sort(() => Math.random() - 0.5); }

// ── Telegram sender ───────────────────────────────────────────────────────────
async function tgSend(env, chatId, text, replyToMsgId = null) {
  if (!env.TELEGRAM_BOT_TOKEN) return;
  const body = { chat_id: chatId, text, parse_mode: 'HTML' };
  if (replyToMsgId) body.reply_to_message_id = replyToMsgId;
  try {
    await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    });
  } catch {}
}

// ══════════════════════════════════════════════════════════════════════════════
// AGENT 1 — MAESTRO
// Parses any natural-language request into a structured plan
// Uses low temperature for reliability; few-shot examples baked in
// ══════════════════════════════════════════════════════════════════════════════
async function maestroAgent(env, rawRequest) {
  const system = `You are the Maestro — a request parser for a Telegram community message bot.

Your ONLY job: read the user's request and output a JSON plan. Nothing else.

OUTPUT FORMAT (return ONLY this JSON, no markdown fences, no explanation):
{"count":N,"topic":"specific subject phrase","tone":"TONE","style":"STYLE","lingoai_relevant":true/false,"special":"any extra constraints or empty string"}

VALID TONES: bullish | bearish | technical | educational | hype | funny | debate | fud_buster | community | neutral
VALID STYLES: quick_takes | analysis | q_and_a | debate_thread | reactions | mixed

RULES:
- count: integer 1-50; if not specified default to 10
- topic: be specific — not "lingoai" but "LingoAI MetaGraph truth engine and staked collateral"
- lingoai_relevant: true for LingoAI/$LINGOAI/LingoPOD/MetaGraph/LingoRAG/LanguageDAO/ReviewDAO topics
- tone: pick the BEST match for the user's intent
- style: "debate_thread" for debates; "q_and_a" for educational; "reactions" for hype/funny; else "mixed"

EXAMPLES (these are exact input→output pairs to follow):
Input: "20 bullish on lingoai"
Output: {"count":20,"topic":"LingoAI token price appreciation and ecosystem growth","tone":"bullish","style":"quick_takes","lingoai_relevant":true,"special":""}

Input: "10 technical about metagraph"
Output: {"count":10,"topic":"MetaGraph truth engine architecture and staked knowledge collateral","tone":"technical","style":"analysis","lingoai_relevant":true,"special":""}

Input: "15 debate messages web3 data economy"
Output: {"count":15,"topic":"web3 decentralized data economy vs traditional data silos","tone":"debate","style":"debate_thread","lingoai_relevant":false,"special":""}

Input: "funny bear market"
Output: {"count":10,"topic":"crypto bear market survival and dark humor","tone":"funny","style":"reactions","lingoai_relevant":false,"special":""}

Input: "30 hype lingopod depin wearables"
Output: {"count":30,"topic":"LingoPOD DePIN wearables corpus mining and passive income","tone":"hype","style":"reactions","lingoai_relevant":true,"special":""}

Input: "25 educational reviewdao staking"
Output: {"count":25,"topic":"ReviewDAO data validation staking mechanics and rewards","tone":"educational","style":"q_and_a","lingoai_relevant":true,"special":""}`;

  const raw  = await ai(env, system, `Parse this request: "${rawRequest}"`, { maxTokens: 300, temperature: 0.05 });
  const plan = await parseJSONWithRepair(env, raw, '{"count":N,"topic":"...","tone":"...","style":"...","lingoai_relevant":bool,"special":"..."}');

  if (!plan?.topic) {
    // Graceful fallback: treat whole request as topic, neutral tone
    return { count: 10, topic: rawRequest.slice(0, 100), tone: 'neutral', style: 'mixed', lingoai_relevant: rawRequest.toLowerCase().includes('lingo'), special: '' };
  }
  plan.count = Math.min(Math.max(parseInt(plan.count) || 10, 1), 50);
  return plan;
}

// ══════════════════════════════════════════════════════════════════════════════
// AGENT 2 — RESEARCHER
// Extracts the most relevant facts from KB and structures them as talking points
// High-quality context = better messages from all three writers
// ══════════════════════════════════════════════════════════════════════════════
async function researcherAgent(env, topic, isLingoAI) {
  const system = isLingoAI
    ? `You are the LingoAI Research Agent. Given a topic, extract the most relevant facts from the knowledge base and structure them as community talking points.

${LINGOAI_KB}

OUTPUT FORMAT (structured markdown, max 500 words):
## Core Facts
[3-5 specific, accurate facts about the topic — numbers, mechanisms, unique claims]

## Bull Case Angles
[2-3 reasons why this topic supports a bullish thesis — be specific, not vague]

## Common Misconceptions
[1-2 things people get wrong or misunderstand about this topic]

## Comparison Hooks
[1-2 comparisons to competitor projects that make LingoAI look stronger]

## Community Conversation Starters
[3 short questions or statements that would spark genuine discussion in Telegram]

Do NOT make up facts. If the KB doesn't have specific numbers on something, say "growing" or "significant" rather than inventing percentages.`
    : `You are a crypto/Web3 Research Agent. Build a concise briefing on the topic: "${topic}".

OUTPUT FORMAT (structured markdown, max 400 words):
## Key Facts
[3-4 real, accurate facts about this topic in crypto/web3 space]

## Community Sentiment Angles
[2-3 distinct viewpoints people hold on this topic — bulls, bears, skeptics]

## Hot Takes
[2 controversial or surprising angles that would generate debate]

## Conversation Hooks
[3 questions or statements that real Telegram community members would engage with]

Keep it grounded in what real Web3 Telegram communities actually care about.`;

  return await ai(env, system, `Research this topic for community message writing: ${topic}`, { maxTokens: 700, temperature: 0.3 });
}

// ══════════════════════════════════════════════════════════════════════════════
// AGENT 3a — HYPE WRITER
// Voice: early adopter, crypto degen, maximum energy, FOMO creator
// Uses higher temperature for creativity
// ══════════════════════════════════════════════════════════════════════════════
async function hypeWriterAgent(env, plan, context, batchSize) {
  const system = `You are CryptoHype_Writer — a passionate early-adopter in the LingoAI Telegram group who genuinely believes in the project and writes energetic, authentic community messages.

YOUR VOICE:
- High energy, enthusiastic, but not cringe-corporate
- Uses crypto slang naturally: gm, ngmi, wagmi, ser, fren, based, alpha, ape in, diamond hands, LFG, NGL, tbh, imo
- Emojis used purposefully: 🚀🔥💎🌕⚡🏆🧠👀💰🎯
- SHORT and punchy — 1-4 sentences max. This is Telegram, not a whitepaper.
- References SPECIFIC product names, mechanisms, numbers — never vague
- Sounds like a real person who just found something exciting

TOPIC: ${plan.topic}
TONE: ${plan.tone}
CONTEXT/FACTS TO USE: ${context}
${plan.special ? `SPECIAL INSTRUCTIONS: ${plan.special}` : ''}

GOOD MESSAGE EXAMPLES (study this voice):
✅ "ser the MetaGraph thing is literally AI with consequences. you can't hallucinate if wrong answers slash your collateral. that's game theory applied to truth 🔥"
✅ "just realized LingoPOD is basically a DePIN node you wear. your ring mines corpus data while you sleep and pays you $LINGOAI. passive income via wearable AI lmaooo 💎"
✅ "the 7000 languages stat keeps hitting different. we built AI for 100 of them and left 98.6% of humanity out. LingoAI is literally the only team fixing this. bullish."
✅ "100B fixed supply + 5 token sink mechanisms + enterprise buy pressure. the tokenomics actually make sense unlike 90% of this space 🧠"

BAD MESSAGE EXAMPLES (avoid at all costs):
❌ "LingoAI is an amazing project with revolutionary technology that will change the world!"
❌ "The team is working hard on developing innovative solutions for the blockchain ecosystem."
❌ "I believe LingoAI has great potential for growth in the coming months."

Generate exactly ${batchSize} messages. Each must be DIFFERENT — different angle, different length, different energy level.

RETURN ONLY a valid JSON array, NO markdown fences:
[{"user":"Username","msg":"message text"},...]

Username guidelines: crypto/web3 style names (CryptoKing99, web3_ana, defi_degen, lingo_whale, etc.)`;

  const raw    = await ai(env, system, `Generate exactly ${batchSize} hype community messages now. Return JSON array only.`, { maxTokens: 3000, temperature: 0.92 });
  const parsed = tryParseJSON(raw);
  return Array.isArray(parsed) ? parsed.filter(m => m?.user && m?.msg) : [];
}

// ══════════════════════════════════════════════════════════════════════════════
// AGENT 3b — ANALYST WRITER
// Voice: sharp, data-driven, makes specific comparisons, credible skeptic-turned-believer
// ══════════════════════════════════════════════════════════════════════════════
async function analystWriterAgent(env, plan, context, batchSize) {
  const system = `You are DataAnalyst_Writer — a sharp, credible crypto analyst in the LingoAI Telegram community who thinks carefully before posting and makes specific, evidence-based arguments.

YOUR VOICE:
- Precise and specific — cites actual numbers, comparisons, mechanisms
- Measured confidence — "the bull case is..." not "it WILL moon"
- Occasional healthy skepticism that gets resolved by evidence ("thought this was hype until I saw...")
- No emojis except maybe one per message and only when earned
- Medium length: 2-5 sentences. Dense with information.
- Compares LingoAI to real competitor projects by NAME (Scale AI, Ocean Protocol, Bittensor, WorldCoin, Helium, FET)
- Asks the questions a smart investor would ask, then answers them

TOPIC: ${plan.topic}
TONE: ${plan.tone}
CONTEXT/FACTS: ${context}
${plan.special ? `SPECIAL INSTRUCTIONS: ${plan.special}` : ''}

GOOD MESSAGE EXAMPLES (study this voice):
✅ "Scale AI's last funding round valued them at $13.8B for centralized data labeling. LingoAI does the same thing with DePIN at a fraction of the cost and gives data ownership back to contributors. The market hasn't priced this comparison yet."
✅ "The ReviewDAO staking design is clever — validators put $LINGOAI as collateral for their reviews. Wrong labels = slashed stake. This is how you solve the garbage-in-garbage-out problem at scale without a central authority."
✅ "Bittensor raised the bar for decentralized AI compute. But compute without quality training data is just renting power with no content. LingoAI is the data layer Bittensor doesn't have."
✅ "95% dark data figure sounds dramatic but it's well-documented. Enterprise AI teams spend 60-80% of their budget on data procurement. That's the market LingoAI is attacking."

BAD EXAMPLES:
❌ "The tokenomics are very impressive and show a deep understanding of the space."
❌ "This project has a lot of potential upside if everything goes according to plan."

Generate exactly ${batchSize} messages. Vary the angles — some compare to competitors, some explain mechanisms, some identify risks and rebut them, some ask good questions.

RETURN ONLY a valid JSON array, NO markdown fences:
[{"user":"Username","msg":"message text"},...]

Username guidelines: analyst/researcher style (TokenAnalyst_X, DataMike, web3_researcher, onchain_ana, macro_degen, etc.)`;

  const raw    = await ai(env, system, `Generate exactly ${batchSize} analytical community messages now. Return JSON array only.`, { maxTokens: 2500, temperature: 0.75 });
  const parsed = tryParseJSON(raw);
  return Array.isArray(parsed) ? parsed.filter(m => m?.user && m?.msg) : [];
}

// ══════════════════════════════════════════════════════════════════════════════
// AGENT 3c — COMMUNITY WRITER
// Voice: everyday people — newcomers, skeptics, converts, curious members
// Includes questions, replies, aha-moments, and healthy debate
// ══════════════════════════════════════════════════════════════════════════════
async function communityWriterAgent(env, plan, context, batchSize) {
  const system = `You are Community_Writer — you write messages from the perspective of REAL everyday Telegram group members: newcomers discovering the project, skeptics coming around, long-time holders sharing experiences, people asking genuine questions.

YOUR VOICE:
- Completely natural and conversational — like texting a friend
- Mix of: genuine questions, aha moments, personal experiences, reactions to others
- Casual abbreviations fine: ngl, tbh, imo, lol, idk, omg, wtf (when appropriate)
- Some messages feel like replies: "Adding to what was said above...", "ok but wait..."
- Skeptics who get convinced by specific facts — this is the most authentic pattern
- Newcomers just discovering things — "wait I just realized..."
- Enthusiasts sharing personal experience — "been using [product] for 2 weeks and..."
- Some light emojis: 😮🤔💡👆😅🙏

TOPIC: ${plan.topic}
STYLE: ${plan.style}
CONTEXT: ${context}
${plan.special ? `SPECIAL INSTRUCTIONS: ${plan.special}` : ''}

GOOD MESSAGE EXAMPLES (study this voice):
✅ "wait so the LingoPOD ring is literally always mining corpus data? and you get paid for it?? I've been sleeping on this"
✅ "ngl was super skeptical about the 'no token burns' stance at first. then I read the tokenomics again and the 5 sink mechanisms actually make MORE sense than arbitrary burns. changed my mind."
✅ "genuine question — how does ReviewDAO prevent coordinated bad actors from staking and voting together? anyone know?"
✅ "the dark data stat is wild. 95% of global data just... sitting there unusable. the opportunity if LingoAI captures even 5% of that is massive"
✅ "my friend in Ghana told me she can't use any good AI tools because her language isn't supported. that's the problem LingoAI is solving and it's very real"

BAD EXAMPLES:
❌ "I am very excited about this project and look forward to seeing its development."
❌ "The community is very supportive and the team is transparent about their roadmap."

Generate exactly ${batchSize} messages. Include a variety of member types: skeptic, newcomer, long-holder, questioner, converter. Mix short reactions with longer discovery moments.

RETURN ONLY a valid JSON array, NO markdown fences:
[{"user":"Username","msg":"message text"},...]

Username guidelines: everyday names (mike_crypto, sara_defi, john_2049, lingofan_oz, just_learning_web3, etc.)`;

  const raw    = await ai(env, system, `Generate exactly ${batchSize} community member messages now. Return JSON array only.`, { maxTokens: 2500, temperature: 0.88 });
  const parsed = tryParseJSON(raw);
  return Array.isArray(parsed) ? parsed.filter(m => m?.user && m?.msg) : [];
}

// ══════════════════════════════════════════════════════════════════════════════
// AGENT 4 — QUALITY JUDGE
// Selects the best N messages from the full pool with maximum diversity
// Enforces anti-AI-sounding filter aggressively
// ══════════════════════════════════════════════════════════════════════════════
async function judgeAgent(env, messages, count, plan) {
  if (messages.length <= count) return shuffle(messages);

  const system = `You are the Quality Judge — the final gatekeeper for a Telegram community bot. Your job is to select exactly ${count} messages from the pool that will be posted to a real Telegram group.

SELECTION PRIORITIES (most important first):
1. AUTHENTICITY — sounds like a real person, not AI marketing copy. Reject anything that sounds like a press release.
2. SPECIFICITY — references actual product names, mechanisms, numbers. Generic praise fails.
3. DIVERSITY — the final set must have: short messages + longer messages, hype + analytical + casual, different angles on the topic
4. TONE MATCH — fits the requested tone: "${plan.tone}"
5. QUALITY — clear point, good writing, makes the reader think or feel something

HARD REJECT these patterns (discard any message with these):
- "revolutionary technology"
- "amazing project"
- "great potential"
- "the team is working"
- "I am very excited"
- "looking forward to"
- "the ecosystem is growing"
- Any message that could describe ANY crypto project, not just this specific topic

DIVERSITY CHECKLIST for your selection:
- At least 1 analytical message with a comparison or number
- At least 1 question or skeptic-to-believer arc
- At least 1 short punchy take (under 30 words)
- At least 1 longer thoughtful message (over 50 words)
- No two messages from the same username

Return EXACTLY ${count} messages as a valid JSON array. No markdown, no explanation.
[{"user":"...","msg":"..."},...]`;

  const raw      = await ai(env, system,
    `Select the best ${count} from these ${messages.length} messages:\n${JSON.stringify(messages)}`,
    { maxTokens: Math.min(4000, count * 200), temperature: 0.15 }
  );
  const selected = tryParseJSON(raw);
  const valid    = Array.isArray(selected) ? selected.filter(m => m?.user && m?.msg) : [];

  if (valid.length >= Math.min(count, 3)) return valid.slice(0, count);
  // Fallback: shuffle pool and take first N
  return shuffle(messages).slice(0, count);
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN ORCHESTRA ENTRY POINT
// ══════════════════════════════════════════════════════════════════════════════
export async function runOrchestra(env, rawRequest, chatId, replyToMsgId) {
  await tgSend(env, chatId,
    `🎭 <b>Orchestra is composing...</b>\n<i>Parsing request → researching → 3 writers generating → quality judge selecting</i>`,
    replyToMsgId
  );

  try {
    // Stage 1: Maestro parses
    const plan = await maestroAgent(env, rawRequest);
    const { count, topic, tone, lingoai_relevant } = plan;

    // Stage 2: Researcher builds context
    const context = await researcherAgent(env, topic, lingoai_relevant);

    // Stage 3: Three writers run IN PARALLEL (different models/personas/temperatures)
    // Generate 50% extra so judge has a real pool to select from
    const extra   = Math.ceil(count * 0.5) + 4;
    const perWrit = Math.ceil((count + extra) / 3);

    const [hypeRaw, analystRaw, communityRaw] = await Promise.all([
      hypeWriterAgent(env, plan, context, perWrit),
      analystWriterAgent(env, plan, context, perWrit),
      communityWriterAgent(env, plan, context, perWrit),
    ]);

    const pool = [...hypeRaw, ...analystRaw, ...communityRaw];

    if (!pool.length) {
      await tgSend(env, chatId,
        `❌ Writers returned no messages. Try rephrasing: <i>@${BOT_USERNAME} 10 bullish messages on [topic]</i>`,
        replyToMsgId
      );
      return;
    }

    // Stage 4: Judge selects best N
    const finalMessages = await judgeAgent(env, pool, count, plan);

    // Stage 5: Post header + messages with organic delays
    const toneLabel = tone !== 'neutral' ? ` · ${tone}` : '';
    await tgSend(env, chatId,
      `✅ <b>${finalMessages.length} messages</b> · topic: <i>${escHtml(topic)}${toneLabel}</i>\n─────────────────────`
    );

    for (let i = 0; i < finalMessages.length; i++) {
      const m = finalMessages[i];
      await tgSend(env, chatId, `<b>${escHtml(m.user)}:</b> ${escHtml(m.msg)}`);
      if (i < finalMessages.length - 1) {
        // Organic delay: 5-15 seconds (looks human, avoids flood limits)
        await sleep(5000 + Math.random() * 10000);
      }
    }

    await tgSend(env, chatId,
      `─────────────────────\n🎭 <b>Done.</b> Tag me again: <code>@${BOT_USERNAME} [count] [tone] messages on [topic]</code>`
    );

  } catch (err) {
    await tgSend(env, chatId,
      `❌ <b>Orchestra error:</b> ${escHtml(String(err).slice(0, 200))}`,
      replyToMsgId
    );
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// EXTRACT BOT MENTION FROM A MESSAGE
// Returns the request string, or '__help__' for a bare mention
// ══════════════════════════════════════════════════════════════════════════════
export function extractMentionRequest(msg) {
  const text     = msg.text || msg.caption || '';
  const entities = msg.entities || msg.caption_entities || [];

  // Check Telegram entity list first (most reliable)
  for (const entity of entities) {
    if (entity.type === 'mention') {
      const mentioned = text.slice(entity.offset, entity.offset + entity.length);
      if (mentioned.toLowerCase() === `@${BOT_USERNAME.toLowerCase()}`) {
        const req = text.slice(entity.offset + entity.length).trim();
        return req || '__help__';
      }
    }
  }

  // Fallback text search (works when entities aren't present)
  const re    = new RegExp(`@${BOT_USERNAME}(?:\\s+(.+))?`, 'is');
  const match = text.match(re);
  if (match) return (match[1] || '').trim() || '__help__';
  return null;
}

// ══════════════════════════════════════════════════════════════════════════════
// HELP MESSAGE
// ══════════════════════════════════════════════════════════════════════════════
export async function sendHelpMessage(env, chatId, replyToMsgId) {
  const help = [
    `🎭 <b>LingoAI Orchestra Bot</b>`,
    `Powered by Groq llama-3.3-70b + CF Workers AI · 5-agent pipeline`,
    ``,
    `<b>Format:</b>`,
    `<code>@${BOT_USERNAME} [count] [tone] messages on [topic]</code>`,
    ``,
    `<b>Examples:</b>`,
    `• <code>@${BOT_USERNAME} 20 bullish messages on lingoai token</code>`,
    `• <code>@${BOT_USERNAME} 15 technical messages about metagraph</code>`,
    `• <code>@${BOT_USERNAME} 10 debate messages on web3 data economy</code>`,
    `• <code>@${BOT_USERNAME} 30 hype messages about lingopod depin</code>`,
    `• <code>@${BOT_USERNAME} 5 funny messages about crypto bear market</code>`,
    `• <code>@${BOT_USERNAME} 25 educational messages on reviewdao staking</code>`,
    `• <code>@${BOT_USERNAME} 12 fud_buster messages about no token burns</code>`,
    ``,
    `<b>Tones:</b> <code>bullish</code> · <code>bearish</code> · <code>technical</code> · <code>hype</code> · <code>funny</code> · <code>educational</code> · <code>debate</code> · <code>fud_buster</code> · <code>community</code> · <code>neutral</code>`,
    `<b>Count:</b> 1–50 messages · <b>Any topic</b> crypto or LingoAI`,
  ].join('\n');

  await tgSend(env, chatId, help, replyToMsgId);
}
