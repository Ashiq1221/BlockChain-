// Discovery Squad — Tavily-powered multi-query job discovery
// Deduplication via CF KV

const CF_MODEL = '@cf/meta/llama-3.3-70b-instruct-fp8-fast';

const ROLE_KEYWORDS = ['community','moderator','social','content','growth','marketing',
  'ambassador','kol','annotation','ai train','data label','localization','prompt','operations'];

function leadId(title, project) {
  const str = `${project}|${title}`.toLowerCase();
  let h = 0;
  for (let i = 0; i < str.length; i++) { h = Math.imul(31, h) + str.charCodeAt(i) | 0; }
  return Math.abs(h).toString(16).padStart(12, '0').slice(0, 12);
}

function matchesProfile(text) {
  const t = text.toLowerCase();
  return ROLE_KEYWORDS.some(k => t.includes(k));
}

// ── CF AI helper (used only for paste import) ─────────────────────────────────

async function callCF(env, system, userContent, maxTokens = 800) {
  if (env.AI) {
    try {
      const result = await env.AI.run(CF_MODEL, {
        messages: [{ role: 'system', content: system }, { role: 'user', content: userContent }],
        max_tokens: maxTokens,
      });
      return result?.response?.trim() ?? '';
    } catch { return ''; }
  }
  if (!env.CF_GLOBAL_KEY) return '';
  try {
    const r = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/ai/run/${CF_MODEL}`,
      {
        method: 'POST',
        headers: { 'X-Auth-Email': env.CF_EMAIL, 'X-Auth-Key': env.CF_GLOBAL_KEY, 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: [{ role: 'system', content: system }, { role: 'user', content: userContent }], max_tokens: maxTokens }),
      }
    );
    if (!r.ok) return '';
    const d = await r.json();
    return d.result?.choices?.[0]?.message?.content?.trim() ?? d.result?.response?.trim() ?? '';
  } catch { return ''; }
}

function parseJsonObj(raw) {
  const clean = (raw || '').replace(/```(?:json)?/g, '').trim();
  const s = clean.indexOf('{'), e = clean.lastIndexOf('}') + 1;
  if (s < 0 || e <= s) return null;
  try { return JSON.parse(clean.slice(s, e)); } catch { return null; }
}

// ── CF KV dedupe ──────────────────────────────────────────────────────────────

async function loadSeen(env) {
  try { return new Set(JSON.parse(await env.KV.get('seen_leads') || '[]')); } catch { return new Set(); }
}

async function saveSeen(env, seen) {
  await env.KV.put('seen_leads', JSON.stringify([...seen].slice(-3000)));
}

// ── Paste importer (POST /import) ─────────────────────────────────────────────

export async function importPastedLead(env, text) {
  const raw = await callCF(env,
    'Structure this job post into ONLY a JSON object (no fences): {"title":str,"project":str,"description":str} — keep contact handles and links verbatim.',
    text, 800,
  );
  const item = parseJsonObj(raw);
  if (!item?.title || !item?.project) return null;
  return { lead_id: leadId(item.title, item.project), title: item.title, project: item.project, source: 'manual', description: item.description };
}

// ── Tavily-powered job discovery ──────────────────────────────────────────────

const EXTRACT_SYSTEM = `Extract RECENT individual job listings (posted in last 2 days) from this page. Return ONLY a JSON array (no fences):
[{"title":"role title","project":"company name","description":"what they need and how to apply","url":"direct job link if present or empty","posted":"date string if visible or empty"}]
Only include: community manager, ambassador, moderator, content creator, social media, growth, AI data/annotation roles.
Skip engineering/dev roles. Skip jobs older than 2 days if dates are visible. Max 10 items. Return [] if nothing relevant.`;

async function extractJobsFromPage(env, pageTitle, pageUrl, content) {
  const raw = await callCF(env, EXTRACT_SYSTEM,
    `Page: ${pageTitle}\nURL: ${pageUrl}\n\nContent:\n${content.slice(0, 3500)}`, 1000);
  const clean = (raw || '').replace(/```(?:json)?/g, '').trim();
  const s = clean.indexOf('['), e = clean.lastIndexOf(']') + 1;
  if (s < 0 || e <= s) return [];
  try { return JSON.parse(clean.slice(s, e)); } catch { return []; }
}

function isListingPage(title) {
  return /\b(jobs|positions|openings|listings|opportunities|hiring now)\b/i.test(title)
    && !/\s+at\s+\w/i.test(title); // "Role at Company" = individual job, not a listing page
}

async function tavilySearch(env, query, maxResults = 8, days = 2) {
  if (!env.TAVILY_API_KEY) return [];
  try {
    const r = await fetch('https://api.tavily.com/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: env.TAVILY_API_KEY, query, search_depth: 'advanced', max_results: maxResults, days }),
    });
    if (!r.ok) return [];
    const d = await r.json();
    return d.results || [];
  } catch { return []; }
}

async function fetchTavilyJobs(env) {
  if (!env.TAVILY_API_KEY) return [];

  // 5 focused queries with recency signals — Tavily days:2 enforces the 48h window
  const queries = [
    'web3 blockchain "community manager" OR "ambassador" new job opening apply now',
    'crypto web3 "community lead" OR "moderator" OR "content creator" hiring apply new role',
    'web3 "growth manager" OR "social media manager" OR "ecosystem lead" new job apply',
    'web3 AI "data annotation" OR "data labeling" new job opening apply',
    'crypto blockchain ambassador program open applications apply now',
  ];

  const batches = await Promise.all(queries.map(q => tavilySearch(env, q, 8)));
  const allResults = batches.flat();

  // Deduplicate by URL
  const urlSeen = new Set();
  const unique = allResults.filter(r => {
    if (!r.url || urlSeen.has(r.url)) return false;
    urlSeen.add(r.url);
    return true;
  });

  // Separate: listing pages vs individual job posts
  const listingPages = unique.filter(r => isListingPage(r.title || ''));
  const directJobs   = unique.filter(r => !isListingPage(r.title || '') && matchesProfile((r.title || '') + ' ' + (r.content || '')));

  // AI-extract individual jobs from listing pages — cap at 5 to stay fast
  const extractedArrays = await Promise.all(
    listingPages.slice(0, 5).map(r =>
      extractJobsFromPage(env, r.title, r.url, r.content || r.description || '').catch(() => [])
    )
  );

  const leads = [];
  const seen  = new Set();

  // Skip URLs that are clearly articles/lists, not job postings
  const SKIP_URL_PATTERNS = /\b(list|top-\d+|best-\d+|guide|tutorial|how-to|what-is|roundup|blog|news|article|events?|programs?-list)\b/i;
  const SKIP_TITLE_PATTERNS = /^(top \d+|best \d+|\d+ best|\d+ top|the \d+|#\d+|list of|what is|how to|guide to|about |why |when )/i;

  function addLead(title, project, description, source, jobUrl) {
    if (!title || !project) return;
    // Filter out articles/lists masquerading as jobs
    if (SKIP_TITLE_PATTERNS.test(title.trim())) return;
    if (jobUrl && SKIP_URL_PATTERNS.test(jobUrl)) return;
    // Require the title to mention a role, not just be a listing page name
    if (!matchesProfile(title)) return;
    const id = leadId(title, project);
    if (seen.has(id)) return;
    seen.add(id);
    leads.push({ lead_id: id, title, project, source, description: description.slice(0, 1500), job_url: jobUrl || '' });
  }

  for (const jobs of extractedArrays) {
    for (const job of (jobs || [])) {
      if (!job?.title || !job?.project) continue;
      if (!matchesProfile(job.title + ' ' + (job.description || ''))) continue;
      addLead(job.title, job.project, job.description || '', 'tavily_extracted', job.url || '');
    }
  }

  // Direct job posts: parse "Role at Company" titles
  for (const item of directJobs) {
    const rawTitle = item.title || '';
    // Strip site name suffixes: "Role at Company | SiteName" or "Role at Company - SiteName"
    const cleanTitle = rawTitle.replace(/\s*[|–—].*$/, '').trim();
    const atMatch = cleanTitle.match(/^(.+?)\s+at\s+(.+?)(?:\s*[-|].*)?$/i);
    const roleTitle = atMatch ? atMatch[1].trim() : cleanTitle;
    const project   = atMatch ? atMatch[2].trim() : cleanTitle.replace(/\s*[-|:@].*$/, '').trim() || 'Unknown';
    const snippet   = (item.content || item.description || '').slice(0, 1200);
    addLead(roleTitle, project, snippet, 'tavily_direct', item.url || '');
  }

  return leads;
}

// ── Main ──────────────────────────────────────────────────────────────────────

export async function discoverLeads(env) {
  const tavilyJobs = await fetchTavilyJobs(env);

  const seen = await loadSeen(env);
  const fresh = tavilyJobs.filter(l => !seen.has(l.lead_id));
  fresh.forEach(l => seen.add(l.lead_id));
  if (fresh.length) await saveSeen(env, seen);
  return fresh;
}
