// Research Squad — Site Scraper + Intel Digger + Red-Flag Checker
// All AI via CF Workers AI; direct fetch + HTML stripping for scraping

import { scrapeUrl } from './x-pipeline.js';

const CF_MODEL = '@cf/meta/llama-3.3-70b-instruct-fp8-fast';

const INTEL_SYSTEM = `You are an intel analyst. From the provided site/posting text, extract ONLY a JSON object (no fences):
{"team":"<doxxed founders? names/roles? anonymous?>","funding":"<raises, backers, treasury, revenue signals, or unknown>","founder_handles":["<@handle found verbatim in text>"],"contact_route":"<best way to reach a decision-maker>","traction":"<community size, activity, product status>"}
Never invent handles or facts. If not in the text, say unknown or empty list.`;

const REDFLAG_SYSTEM = `You are a scam and dead-project detector for web3 job seekers. Return ONLY a JSON object (no fences):
{"flags":["<specific flag>"],"severity":"none"|"low"|"medium"|"high","notes":"<1-2 sentences>"}
Watch for: pay-to-work schemes, buy-token-first, unpaid ambassador funnels, anonymous team + big promises, guaranteed returns, urgency pressure, seed phrase/deposit requests, recycled whitepaper, dead links.`;

async function callCF(env, system, content, maxTokens = 700) {
  let raw = '';
  if (env.AI) {
    try {
      const result = await env.AI.run(CF_MODEL, {
        messages: [{ role: 'system', content: system }, { role: 'user', content }],
        max_tokens: maxTokens,
      });
      raw = result?.response?.trim() ?? '';
    } catch { return null; }
  } else if (env.CF_GLOBAL_KEY) {
    try {
      const r = await fetch(
        `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/ai/run/${CF_MODEL}`,
        {
          method: 'POST',
          headers: { 'X-Auth-Email': env.CF_EMAIL, 'X-Auth-Key': env.CF_GLOBAL_KEY, 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: [{ role: 'system', content: system }, { role: 'user', content }], max_tokens: maxTokens }),
        }
      );
      if (!r.ok) return null;
      const d = await r.json();
      raw = (d.result?.choices?.[0]?.message?.content ?? d.result?.response ?? '').trim();
    } catch { return null; }
  } else { return null; }
  raw = raw.replace(/```(?:json)?/g, '').trim();
  const s = raw.indexOf('{'), e = raw.lastIndexOf('}') + 1;
  if (s < 0 || e <= s) return null;
  try { return JSON.parse(raw.slice(s, e)); } catch { return null; }
}

export async function buildDossier(env, lead) {
  const urls = [...(lead.description.matchAll(/https?:\/\/[^\s)\]"']+/g))].map(m => m[0]);
  const sorted = urls.sort((a, b) => {
    const isBoard = u => /career|remote3|cryptojob|lever|greenhouse|ashby|workable/.test(u);
    return isBoard(a) - isBoard(b);
  });

  let siteText = '';
  for (const url of sorted.slice(0, 2)) {
    try {
      const text = await scrapeUrl(url);
      if (text?.length > 300) { siteText = `[Scraped ${new URL(url).hostname}]\n${text.slice(0, 8000)}`; break; }
    } catch { /* try next */ }
  }

  const evidence = `JOB POSTING:\n${lead.description}\n\nSITE CONTENT:\n${siteText || '(no site content retrieved — argue from posting alone)'}`;

  const [intel, flags] = await Promise.all([
    callCF(env, INTEL_SYSTEM, evidence),
    callCF(env, REDFLAG_SYSTEM, evidence),
  ]);

  const dossier = [
    `TEAM: ${intel?.team || 'unknown'}`,
    `FUNDING: ${intel?.funding || 'unknown'}`,
    `FOUNDER/ADMIN CONTACTS: ${(intel?.founder_handles || []).join(', ') || 'none found'}`,
    `BEST CONTACT ROUTE: ${intel?.contact_route || 'unknown'}`,
    `TRACTION: ${intel?.traction || 'unknown'}`,
    `RED FLAGS (${flags?.severity || 'unknown'}): ${(flags?.flags || []).join('; ') || 'none detected'}`,
    `CHECKER NOTES: ${flags?.notes || ''}`,
  ].join('\n');

  return { ...lead, dossier, founder_handles: intel?.founder_handles || [], red_flag_severity: flags?.severity || 'unknown' };
}

export async function enrichLeads(env, leads) {
  const results = await Promise.all(leads.map(async lead => {
    try { return await buildDossier(env, lead); }
    catch { return { ...lead, dossier: '[Research failed. Debate from posting alone.]', founder_handles: [] }; }
  }));
  return results;
}
