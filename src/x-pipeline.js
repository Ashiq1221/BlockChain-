// X / Twitter — Primary job source — 12-agent pipeline + Debate Chamber filter
// Live sources: Apify tweet scraper + twitterapi.io + xAI Grok + general Tavily

import { deliberate, agentCall, ai, searchXWithGrok } from './agents.js';
import { judgeLeads } from './debate.js';

const HIRING_KW = ['hiring','job','role','position','apply','dm us','dm to apply',
  'looking for','join us','we need','open role','we\'re hiring','we are hiring',
  'now hiring','open position','join our team'];
const WEB3_KW = ['web3','crypto','blockchain','defi','nft','dao','token',
  'protocol','dapp','layer','chain','ai','ecosystem'];
const NAV_SKIP = ['sign in','log in','create account','trending','who to follow',
  'privacy policy','terms of service','cookie policy','explore'];

const X_SEARCH_TERMS = [
  'web3 crypto hiring community manager ambassador apply DM',
  'blockchain startup hiring community lead moderator remote',
  'AI web3 project hiring community manager content creator',
  'crypto project open role community apply now 2026',
  '"we are hiring" web3 community manager ambassador',
  '"now hiring" web3 blockchain community lead moderator',
  'web3 ambassador program open applications DM apply',
  'crypto startup hiring ecosystem lead growth manager remote',
  'blockchain AI hiring content creator social media manager',
  'web3 dao hiring community moderator contributor apply',
  '#web3jobs community manager ambassador moderator',
  '#cryptojobs hiring community lead content creator',
  'defi protocol hiring community manager 2026',
  'layer2 blockchain hiring community ambassador',
  'web3 "open role" community content creator moderator 2026',
];

// Grok live-search queries — scans real X posts via xAI API (requires XAI_API_KEY)
const GROK_X_QUERIES = [
  'web3 crypto hiring community manager ambassador apply DM 2026',
  '"ambassador program" crypto web3 open applications now hiring',
  '"now hiring" OR "we are hiring" web3 blockchain community moderator',
  '#web3jobs #cryptojobs community manager content creator apply',
  'blockchain AI startup "open role" community lead DM to apply',
];

// General Tavily queries — no site: restriction, finds job boards + company blogs
const TAVILY_JOB_QUERIES = [
  'web3 crypto hiring community manager ambassador apply DM',
  'blockchain startup hiring community lead moderator remote',
  'AI web3 project hiring community manager content creator',
  'crypto project open role community apply now 2026',
  '"we are hiring" web3 community manager ambassador',
  '"now hiring" web3 blockchain community lead moderator',
  'web3 ambassador program open applications DM apply',
  'crypto startup hiring ecosystem lead growth manager remote',
  '#web3jobs community manager ambassador moderator hiring',
  '#cryptojobs hiring community lead content creator 2026',
  'defi protocol hiring community manager ambassador 2026',
  'web3 dao hiring community contributor moderator apply',
];

// ── HTTP helpers ──────────────────────────────────────────────────────────────

// Direct URL scraper — strips HTML, no external API needed
export async function scrapeUrl(url) {
  if (!url?.startsWith('http')) return '';
  try {
    const r = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; job-research-bot/1.0)' },
      redirect: 'follow',
    });
    if (!r.ok) return '';
    const html = await r.text();
    return html
      .replace(/<script[\s\S]*?<\/script>/gi, '')
      .replace(/<style[\s\S]*?<\/style>/gi, '')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
      .replace(/\s+/g, ' ').trim().slice(0, 6000);
  } catch { return ''; }
}

// General Tavily search — used for job discovery and company research
async function tavilySearch(env, query, limit = 6, days = 2) {
  if (!env.TAVILY_API_KEY) return [];
  try {
    const r = await fetch('https://api.tavily.com/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: env.TAVILY_API_KEY,
        query,
        search_depth: 'advanced',
        max_results: limit,
        days,
      }),
    });
    if (r.ok) {
      const d = await r.json();
      return (d.results || []).slice(0, limit).map(x => ({
        title:   x.title   || '',
        url:     x.url     || '',
        snippet: (x.content || '').slice(0, 400),
      }));
    }
  } catch { /* ignore */ }
  return [];
}


// ── Apify Twitter Scraper — async fire-and-collect pattern ───────────────────
// First cycle starts runs, subsequent cycles collect their results from KV

async function apifyFetch(env, path, opts = {}) {
  return fetch(`https://api.apify.com/v2${path}`, {
    ...opts,
    headers: {
      'Authorization': `Bearer ${env.APIFY_API_KEY}`,
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    },
  });
}

async function searchXViaApify(env) {
  if (!env.APIFY_API_KEY) return [];
  const actorId = 'apidojo~tweet-scraper';
  const chunks  = [];
  const seen    = new Set();

  // Step 1: collect results from FINISHED runs stored in KV
  try {
    const storedIds = JSON.parse(await env.KV.get('apify_run_ids') || '[]');
    const stillRunning = [];

    await Promise.all(storedIds.slice(-8).map(async id => {
      try {
        // Check run status first
        const statusR = await apifyFetch(env, `/actor-runs/${id}`);
        if (!statusR.ok) return;
        const statusD = await statusR.json();
        const status  = statusD.data?.status || '';

        if (status === 'RUNNING' || status === 'READY') {
          stillRunning.push(id); // not done yet, keep for next cycle
          return;
        }
        if (status !== 'SUCCEEDED') return; // FAILED / ABORTED — drop it

        // Run succeeded — fetch dataset items
        const dataR = await apifyFetch(env, `/actor-runs/${id}/dataset/items?limit=30&clean=true`);
        if (!dataR.ok) return;
        const tweets = await dataR.json();

        for (const t of (Array.isArray(tweets) ? tweets : [])) {
          const text = (t.text || t.full_text || '').trim();
          if (text.length < 25) continue;
          const key = text.slice(0, 60);
          if (seen.has(key)) continue;
          seen.add(key);
          chunks.push({
            text,
            author:    t.author?.userName || t.user?.screen_name || '',
            urls:      (t.entities?.urls || []).map(u => u.expanded_url || '').filter(Boolean),
            tweet_url: t.url || t.tweetUrl || '',
            source:    'apify',
          });
        }
      } catch { /* skip this run */ }
    }));

    // Keep only still-running IDs in KV (finished ones were consumed)
    await env.KV.put('apify_run_ids', JSON.stringify(stillRunning.slice(-8)));
  } catch { /* skip on KV failure */ }

  // Step 2: fire new async runs — results collected next cycle
  const apifyQueries = [
    'web3 crypto hiring community manager ambassador apply DM',
    '"now hiring" web3 blockchain community moderator apply',
    '#web3jobs #cryptojobs community manager ambassador hiring',
    'blockchain AI startup community lead open role DM to apply',
  ];
  const newIds = [];
  await Promise.all(apifyQueries.map(async query => {
    try {
      const r = await apifyFetch(env, `/acts/${actorId}/runs?memory=256`, {
        method: 'POST',
        body: JSON.stringify({ searchTerms: [query], maxTweets: 25, queryType: 'Latest', lang: 'en' }),
      });
      if (r.ok) {
        const d = await r.json();
        const runId = d.data?.id;
        if (runId) newIds.push(runId);
      }
    } catch { /* skip */ }
  }));

  if (newIds.length) {
    try {
      const prev = JSON.parse(await env.KV.get('apify_run_ids') || '[]');
      await env.KV.put('apify_run_ids', JSON.stringify([...prev, ...newIds].slice(-12)));
    } catch { /* skip */ }
  }

  return chunks;
}

// ── twitterapi.io — direct X search (uses X_GET_API_KEY) ─────────────────────

async function searchXViaGetXApi(env, query, limit = 20) {
  if (!env.X_GET_API_KEY) return [];
  try {
    const r = await fetch(
      `https://api.twitterapi.io/twitter/tweet/search?query=${encodeURIComponent(query)}&queryType=Latest`,
      { headers: { 'X-API-Key': env.X_GET_API_KEY, 'Accept': 'application/json' } }
    );
    if (!r.ok) return [];
    const d = await r.json();
    const tweets = d.tweets || d.data || [];
    return tweets.slice(0, limit).map(t => ({
      text:      (t.text || t.full_text || '').trim(),
      author:    t.author?.userName || t.user?.screen_name || '',
      urls:      (t.entities?.urls || []).map(u => u.expanded_url || '').filter(Boolean),
      tweet_url: t.url || `https://x.com/i/web/status/${t.id || t.id_str || ''}`,
      source:    'twitterapi_io',
    })).filter(t => t.text.length > 20);
  } catch { return []; }
}

// ── Live X + web job discovery ────────────────────────────────────────────────

async function searchTavilyXDirect(env) {
  const seen   = new Set();
  const chunks = [];

  function addTweets(tweets, src) {
    for (const t of tweets) {
      const key = (t.text || '').slice(0, 60);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      chunks.push({ ...t, source: t.source || src });
    }
  }

  function addTavily(results) {
    for (const r of results) {
      const key = (r.url || '').slice(0, 80) || (r.snippet || '').slice(0, 60);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      const authorM = r.url.match(/(?:twitter\.com|x\.com)\/(\w+)\//);
      chunks.push({ text: `${r.snippet} ${r.title}`.trim(), author: authorM?.[1] || '', urls: [], tweet_url: r.url, source: 'tavily_web' });
    }
  }

  // Source 1: Apify async accumulator — real X tweets (builds up from 2nd cycle on)
  const apifyChunks = await searchXViaApify(env);
  addTweets(apifyChunks, 'apify');

  // Source 2: twitterapi.io direct search
  if (env.X_GET_API_KEY) {
    const getXBatches = await Promise.all([
      searchXViaGetXApi(env, 'web3 crypto hiring community manager ambassador apply DM 2026'),
      searchXViaGetXApi(env, '#web3jobs #cryptojobs community manager ambassador moderator hiring'),
      searchXViaGetXApi(env, '"now hiring" OR "we are hiring" web3 blockchain community lead'),
    ]);
    for (const batch of getXBatches) addTweets(batch, 'twitterapi_io');
  }

  // Source 3: xAI Grok live X search
  if (env.XAI_API_KEY) {
    const grokBatches = await Promise.all(
      GROK_X_QUERIES.map(q => searchXWithGrok(env, q, 10))
    );
    for (const batch of grokBatches) addTweets(batch, 'grok_live_x');
  }

  // Source 4: general Tavily web search — job boards, company blogs, LinkedIn
  const tavilyBatches = await Promise.all(
    TAVILY_JOB_QUERIES.map(q => tavilySearch(env, q, 6, 2))
  );
  for (const results of tavilyBatches) addTavily(results);

  return chunks;
}

async function webSearch(env, query, limit = 6) {
  return tavilySearch(env, query, limit, 30); // research: broader window, not job-fresh filter
}

// ── Parsers ───────────────────────────────────────────────────────────────────

function extractHandles(text) {
  return [...(text.matchAll(/t\.me\/(\w{3,32})/g))].map(m => m[1])
    .filter(h => !['joinchat','share','s','iv','addstickers','telegram','tme','durov'].includes(h.toLowerCase()));
}

function extractEmails(text) {
  const skip = ['example.com','youremail.com','email.com','domain.com','sentry.io'];
  return [...(text.matchAll(/[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}/g))].map(m => m[0])
    .filter(e => !skip.some(s => e.includes(s)));
}

function extractWebsite(text) {
  const skip = ['twitter.com','x.com','t.co','bit.ly','buff.ly','ow.ly','linktr.ee'];
  const urls = [...(text.matchAll(/https?:\/\/[^\s\)\"\']+/g))].map(m => m[0]);
  return urls.find(u => !skip.some(s => u.includes(s))) || '';
}

function parseXBlocks(markdown, sourceUrl) {
  const authorM = sourceUrl.match(/(?:twitter\.com|x\.com)\/(\w{3,30})\//);
  const author = authorM?.[1] || '';
  return markdown.split(/\n{2,}/).map(b => b.trim()).filter(b => {
    if (b.length < 30 || b.length > 800) return false;
    const low = b.toLowerCase();
    return !NAV_SKIP.some(s => low.includes(s));
  }).map(text => ({
    text,
    author,
    urls: [...(text.matchAll(/https?:\/\/[^\s\)\"\']+/g))].map(m => m[0])
      .filter(u => !['twitter.com','x.com','t.co'].some(d => u.includes(d))),
    tweet_url: sourceUrl,
  }));
}

function jsonObj(text) {
  if (!text) return null;
  const s = text.indexOf('{'), e = text.lastIndexOf('}') + 1;
  if (s < 0 || e <= s) return null;
  try { return JSON.parse(text.slice(s, e)); } catch { return null; }
}

function jsonArr(text) {
  if (!text) return [];
  const s = text.indexOf('['), e = text.lastIndexOf(']') + 1;
  if (s < 0 || e <= s) return [];
  try { return JSON.parse(text.slice(s, e)); } catch { return []; }
}

// ── Pair 1: HUNTERS — collect + filter raw X posts ───────────────────────────

async function collectRawLeads(env) {
  const all  = [];
  const seen = new Set();

  function add(chunks) {
    for (const c of chunks) {
      const key = (c.text || '').slice(0, 50);
      if (key && !seen.has(key)) { seen.add(key); all.push(c); }
    }
  }

  // Single source — Grok live X (if key set) + general Tavily web search
  const xChunks = await searchTavilyXDirect(env);
  add(xChunks);

  return all;
}

async function hunterFilter(env, raw) {
  // Fast keyword pre-filter
  const candidates = raw.filter(c => {
    const low = (c.text || '').toLowerCase();
    return c.text?.length >= 30
      && (HIRING_KW.some(kw => low.includes(kw)) || WEB3_KW.some(kw => low.includes(kw)));
  }).slice(0, 50);

  const approved = [];
  const batchSize = 8;
  for (let i = 0; i < candidates.length; i += batchSize) {
    const batch = candidates.slice(i, i + batchSize);
    const batchText = batch.map((c, j) => `[${j}] @${c.author || '?'}: ${(c.text || '').slice(0, 200)}`).join('\n---\n');
    const verdict = await deliberate(
      env, 'Hunter_Alpha', 'Hunter_Beta',
      'Review these X/Twitter posts. Return a JSON array of indices (0-based) for REAL hiring opportunities in Web3/AI community roles. Example: [0, 3]. Return [] if none qualify.',
      batchText, 200,
    );
    const keep = jsonArr(verdict);
    for (const idx of keep) {
      if (Number.isInteger(idx) && idx >= 0 && idx < batch.length) approved.push(batch[idx]);
    }
  }
  return approved;
}

// ── Pair 2: PROFILERS — research company from X profile ──────────────────────

async function profilerResearch(env, chunk, profile) {
  const ctx = [
    `Poster X handle: @${chunk.author || '?'}`,
    `Tweet: ${(chunk.text || '').slice(0, 400)}`,
    `X profile bio: ${(profile.raw || '').slice(0, 600)}`,
    `TG from profile: ${profile.telegram || 'none'}`,
    `Website from profile: ${profile.website || 'none'}`,
    `Email from profile: ${profile.email || 'none'}`,
    `URLs in tweet: ${(chunk.urls || []).slice(0, 3).join(', ')}`,
  ].join('\n');

  const MY_PROFILE_SHORT = `NAME: Ashiq | TITLE: AI Ops Specialist | Community Builder | Content Creator
TWITTER: @Ganaie__suhail (16k+ followers, organic) | TELEGRAM: @ashiq80 | DISCORD: ashiq1581
STATS: 16k X followers, 6k+ community members (Telegram/Discord/X), 3+ yrs Web3
ROLES: Community Manager, Ambassador, Content Creator, AI Data Annotator, Prompt Engineer
LOCATION: Kashmir, India — fully remote`;

  const raw = await deliberate(
    env, 'Profiler_Alpha', 'Profiler_Beta',
    `Extract structured job lead data. Return ONLY valid JSON:
{"title":"","company":"","description":"","website":"","email":"","telegram":"","apply_url":"","score":0,"proceed":true}
- title: role being hired
- company: project/startup name
- description: what they need (1-2 sentences)
- score: relevance 0-100 for Ashiq
- proceed: false if score < 45 or project looks dead
Return null if not a real job.`,
    `${ctx}\n\nApplicant: ${MY_PROFILE_SHORT}`,
    400,
  );

  if (!raw || raw.trim().toLowerCase() === 'null') return null;
  const result = jsonObj(raw);
  if (!result?.company) return null;
  if (!result.proceed) return null;

  // Merge profile data
  if (!result.telegram) result.telegram = profile.telegram || '';
  if (!result.website)  result.website  = profile.website  || '';
  if (!result.email)    result.email    = profile.email    || '';
  result.poster_handle = chunk.author || '';
  result.job_url       = chunk.tweet_url || '';
  result.source        = 'x_twitter';
  result.title         = result.title || 'Web3 Role';
  return result;
}

// ── Pair 3: CONTACT MAPPERS — find founder + TG group ────────────────────────

async function contactMapper(env, job) {
  let tg = (job.telegram || '').replace('t.me/', '').replace('@', '').trim();

  // Scrape company website for TG link if missing
  if (!tg && job.website?.startsWith('http')) {
    const page = await scrapeUrl(job.website);
    const hits = extractHandles(page);
    if (hits.length) tg = hits[0];
  }

  // Web search for founder handle
  let founderHandle = '';
  if (job.company) {
    const searches = await Promise.all([
      webSearch(env, `"${job.company}" founder CEO site:x.com OR site:twitter.com`, 4),
      webSearch(env, `${job.company} web3 founder twitter handle`, 3),
    ]);
    for (const results of searches) {
      for (const r of results) {
        const blob = `${r.url} ${r.snippet} ${r.title}`;
        const handles = [...(blob.matchAll(/(?:twitter\.com|x\.com)\/(\w{3,30})(?:\/|$|\s)/g))].map(m => m[1]);
        const skip = new Set(['search','hashtag','intent','share','home','explore','notifications', job.poster_handle?.toLowerCase()]);
        founderHandle = handles.find(h => !skip.has(h.toLowerCase())) || '';
        if (founderHandle) break;
      }
      if (founderHandle) break;
    }
  }

  const ctx = [
    `Company: ${job.company}`,
    `Poster X: @${job.poster_handle || '?'}`,
    `Found founder X: @${founderHandle || 'unknown'}`,
    `Known TG group: ${tg || 'none'}`,
    `Website: ${job.website || 'none'}`,
    `Job: ${job.description?.slice(0, 200) || ''}`,
  ].join('\n');

  const verdict = await deliberate(
    env, 'Contact_Alpha', 'Contact_Beta',
    'Determine the best contact strategy. Return ONLY valid JSON:\n{"founder_x":"","tg_group":"","best_channel":"tg|form|email","reason":""}',
    ctx, 200,
  );
  const contacts = jsonObj(verdict) || {};

  job.founder_x    = contacts.founder_x    || founderHandle || job.poster_handle || '';
  job.telegram      = contacts.tg_group     || tg || '';
  job.best_channel  = contacts.best_channel || 'telegram';
  return job;
}

// ── Public API ────────────────────────────────────────────────────────────────

export async function scrapeXProfile(env, handle) {
  handle = handle.replace('@', '').trim();
  // Tavily search for the profile — X blocks direct scraping
  const results = await tavilySearch(env, `site:x.com/${handle} OR site:twitter.com/${handle} bio`, 3, 30);
  const blob = results.map(r => `${r.title} ${r.snippet}`).join('\n');
  return {
    handle,
    raw:      blob.slice(0, 3000),
    telegram: extractHandles(blob)[0] || '',
    email:    extractEmails(blob)[0]  || '',
    website:  extractWebsite(blob),
  };
}

export async function runXPipeline(env) {
  // Stage 1: collect raw X posts (Tavily site: queries)
  const raw = await collectRawLeads(env);

  // Stage 2: fast keyword pre-filter → initial agent filter
  const prefiltered = await hunterFilter(env, raw);
  if (!prefiltered.length) return [];

  // Stage 3: Profiler + Contact research per lead
  const researched = [];
  const seenCompanies = new Set();

  for (const chunk of prefiltered.slice(0, 20)) {
    const profile = chunk.author ? await scrapeXProfile(env, chunk.author) : {};
    let job = await profilerResearch(env, chunk, profile);
    if (!job) continue;

    const key = job.company.toLowerCase();
    if (seenCompanies.has(key)) continue;
    seenCompanies.add(key);

    job = await contactMapper(env, job);
    researched.push(job);
  }

  if (!researched.length) return [];

  // Stage 4: Debate Chamber — Advocate vs Skeptic → Judge (CF Workers AI)
  const debateLeads = researched.map(job => ({
    lead_id:     `${job.company}_${job.title}`.toLowerCase().replace(/\s+/g, '_'),
    title:       job.title,
    project:     job.company,
    source:      job.source || 'x.com',
    description: job.description || '',
    dossier:     [
      job.website   ? `Website: ${job.website}`           : '',
      job.telegram  ? `TG group: @${job.telegram}`        : '',
      job.email     ? `Email: ${job.email}`               : '',
      job.founder_x ? `Founder on X: @${job.founder_x}`  : '',
      `Source tweet: ${job.job_url || ''}`,
    ].filter(Boolean).join('\n'),
    _job: job,
  }));

  const { apply, watch } = await judgeLeads(env, debateLeads);
  return [...apply, ...watch].map(v => {
    const original = debateLeads.find(l => l.lead_id === v.lead_id)?._job || {};
    return { ...original, debate_score: v.score, debate_verdict: v.verdict, debate_angle: v.angle };
  });
}

export { webSearch, extractHandles, extractEmails, jsonObj, jsonArr };
