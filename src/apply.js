// Multi-channel application executor
// Priority: Personal TG DM (as @ashiq80) → Group post (as @ashiq80) → Email → Google Form
// Continuous learning: outcome tracked, opening line recorded for style memory

import { deliberate, agentCall } from './agents.js';
import { sendUserDM, postInGroupAsUser, replyToPost, isAuthed } from './telegram-user.js';
import { postInGroup, findJobPostInGroup, sendApplyNotification, notifyOwner } from './telegram.js';
import { webSearch, jsonObj } from './x-pipeline.js';
import { recordOutcome, recordStyle, loadLearningContext, learningPrompt } from './learning.js';

const MY_PROFILE = `NAME: Ashiq
TITLE: AI Ops Specialist | Community Builder | Content Creator
TWITTER: @Ganaie__suhail (16,000+ followers, built 100% organically)
TELEGRAM: @ashiq80
DISCORD: ashiq1581
EMAIL: naveeddurfi@gmail.com
STATS: 16k+ X followers, 6k+ community members across Telegram/Discord/X, 3+ years Web3
SKILLS: Community Management, Ambassador Programs, Content Creation, AI Data Annotation, Prompt Engineering, Agentic AI Workflows
LOCATION: Kashmir, India — fully remote
HIGHLIGHTS: Built ICPCollectible to 16k X followers organically; managed 6k+ member community for EMC Protocol; ran ambassador campaigns for LingoAI, Network3, RIDO; 40% efficiency gains via agentic AI automation`;

// ── Message crafter ───────────────────────────────────────────────────────────

export async function craftApplication(env, job, learningCtx) {
  const lCtx = learningCtx || await loadLearningContext(env);
  const lPrompt = learningPrompt(lCtx);

  const ctx = [
    `Role: ${job.title || 'Community Manager / Ambassador'}`,
    `Company: ${job.company || job.project || 'Unknown'}`,
    `Description: ${job.description || ''}`,
    `Channel: Telegram DM`,
    `Website: ${job.website || ''}`,
    '',
    `Applicant:\n${MY_PROFILE}`,
    lPrompt ? `\n${lPrompt}` : '',
  ].join('\n');

  const task = `Write a concise, compelling Telegram DM for Ashiq to apply for this Web3 role.
Rules:
- Open with ONE specific thing about the project (not generic praise)
- State 1-2 hard stats from Ashiq's profile
- End with a clear, specific ask (e.g. "Would love to jump on a quick call — what's your onboarding process?")
- Max 130 words
- No emojis unless the job post used them
- Do NOT start with "Hi", "Hello", or "Dear"
- Sound human, direct, confident
- Output only the message text`;

  const raw = await deliberate(env, 'Strategy_Alpha', 'Strategy_Beta', task, ctx, 400, lPrompt);
  return (raw || '').trim();
}

// ── QA pass ───────────────────────────────────────────────────────────────────

async function execQA(env, job, message) {
  const ctx = `Company: ${job.company || job.project}\nRole: ${job.title}\n\nMessage:\n${message}`;
  const verdict = await deliberate(
    env, 'Exec_Alpha', 'Exec_Beta',
    'Review this Telegram application DM. Return JSON: {"approved":true/false,"revised_message":"...","reason":""}. If not approved, provide revised_message under 130 words.',
    ctx, 400,
  );
  const r = jsonObj(verdict);
  if (!r) return message;
  return r.approved ? message : (r.revised_message || message).trim();
}

// ── Google Form ───────────────────────────────────────────────────────────────

async function submitGoogleForm(env, formUrl, job, message) {
  if (!formUrl?.includes('docs.google.com/forms')) return false;
  try {
    const r = await fetch(formUrl, { headers: { 'User-Agent': 'Mozilla/5.0' } });
    const html = await r.text();
    const entries = {};
    const labelPattern = /["']([^"']{3,80})["'][^}]{0,200}entry\.(\d+)/g;
    let m;
    while ((m = labelPattern.exec(html)) !== null) {
      const label = m[1].toLowerCase(), id = `entry.${m[2]}`;
      if (label.includes('name')) entries.name = id;
      else if (label.includes('email')) entries.email = id;
      else if (label.includes('telegram') || label.includes('tg')) entries.telegram = id;
      else if (label.includes('experience') || label.includes('why') || label.includes('tell')) entries.message = id;
    }
    if (Object.keys(entries).length < 2) return false;
    const submitUrl = formUrl.replace('/viewform', '/formResponse').split('?')[0];
    const body = new URLSearchParams();
    if (entries.name)     body.set(entries.name,     'Ashiq');
    if (entries.email)    body.set(entries.email,    env.MY_EMAIL || 'naveeddurfi@gmail.com');
    if (entries.telegram) body.set(entries.telegram, '@ashiq80');
    if (entries.message)  body.set(entries.message,  message);
    const res = await fetch(submitUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    return res.ok || res.status === 302;
  } catch { return false; }
}

async function findApplyForm(env, job) {
  const candidates = [job.apply_url, job.website, job.job_url].filter(Boolean);
  for (const url of candidates) {
    if (url.includes('docs.google.com/forms')) return url;
    if (url.startsWith('http')) {
      try {
        const r = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
        const html = await r.text();
        const m = html.match(/https:\/\/docs\.google\.com\/forms\/[^\s"']+/);
        if (m) return m[0].split('?')[0] + '?usp=sf_link';
      } catch { /* try next */ }
    }
  }
  if (job.company) {
    const results = await webSearch(env, `"${job.company}" apply google form community manager ambassador`, 3);
    for (const r of results) {
      if (r.url.includes('docs.google.com/forms')) return r.url;
    }
  }
  return null;
}

// ── Email ─────────────────────────────────────────────────────────────────────

async function sendEmail(env, toEmail, subject, body) {
  if (!toEmail) return false;
  try {
    const r = await fetch('https://api.mailchannels.net/tx/v1/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: toEmail }] }],
        from: { email: env.MY_EMAIL || 'naveeddurfi@gmail.com', name: 'Ashiq' },
        subject,
        content: [{ type: 'text/plain', value: body }],
      }),
    });
    return r.status === 202;
  } catch { return false; }
}

// ── Main apply orchestrator ───────────────────────────────────────────────────

export async function applyToJob(env, job, applied, learningCtx) {
  const key = `${(job.company || job.project || '').toLowerCase()}_${(job.title || '').toLowerCase()}`
    .replace(/\s+/g, '_').slice(0, 80);
  if (applied[key]) return { status: 'already_applied', key };

  const lCtx = learningCtx || await loadLearningContext(env);

  // Craft + QA message
  let message = await craftApplication(env, job, lCtx);
  if (!message) return { status: 'no_message', key };
  message = await execQA(env, job, message);

  const opening = message.split(/[.!?]/)[0] || '';
  let status = 'failed', channel = 'none';
  const authed = await isAuthed(env);

  // ── Channel 0: Direct reply to the group post (highest priority — scanned leads) ──
  if (status !== 'sent' && job.tg_chat_id && job.tg_msg_id) {
    const res = await replyToPost(env, job.tg_chat_id, job.tg_msg_id, message);
    if (res.ok) { status = 'sent'; channel = `tg_reply:${job.tg_chat_id}:${job.tg_msg_id}`; }
  }

  // ── Channel 1: Personal TG DM to founder ────────────────────────────────────
  const founderTg = (job.telegram_founder || job.founder_tg || '').replace('@', '').trim();
  if (authed && founderTg) {
    const res = await sendUserDM(env, founderTg, message);
    if (res.ok) { status = 'sent'; channel = `tg_personal_dm:${founderTg}`; }
  }

  // ── Channel 2: Personal TG post in group ─────────────────────────────────────
  if (status !== 'sent' && authed && job.telegram) {
    const tgHandle = (job.telegram || '').replace('t.me/', '').replace('@', '');
    // Try to find the job post to reply to it directly
    const jobPost = await findJobPostInGroup(env, tgHandle).catch(() => null);
    const replyId = jobPost?.msg_id || null;
    const grpMsg  = replyId ? message : `[Applying for ${job.title}]\n\n${message}`;
    const res = await postInGroupAsUser(env, tgHandle, grpMsg, replyId);
    if (res.ok) { status = 'sent'; channel = `tg_personal_group:${tgHandle}`; }
  }

  // ── Channel 3: Bot posts in group (fallback if personal not authed) ──────────
  if (status !== 'sent' && job.telegram) {
    const tgHandle = (job.telegram || '').replace('t.me/', '').replace('@', '');
    const jobPost = await findJobPostInGroup(env, tgHandle).catch(() => null);
    const replyId = jobPost?.msg_id || null;
    const grpMsg  = replyId ? message : `[Applying for ${job.title}]\n\n${message}`;
    const ok = await postInGroup(env, tgHandle, grpMsg, replyId);
    if (ok) { status = 'sent'; channel = `tg_bot_group:${tgHandle}`; }
  }

  // ── Channel 4: Google Form ───────────────────────────────────────────────────
  if (status !== 'sent') {
    const formUrl = await findApplyForm(env, job);
    if (formUrl) {
      const ok = await submitGoogleForm(env, formUrl, job, message);
      if (ok) { status = 'sent'; channel = 'google_form'; }
    }
  }

  // ── Channel 5: Email ─────────────────────────────────────────────────────────
  if (status !== 'sent' && job.email) {
    const subject = `Application: ${job.title || 'Community Role'} — Ashiq (@ashiq80)`;
    const ok = await sendEmail(env, job.email, subject, message);
    if (ok) { status = 'sent'; channel = `email:${job.email}`; }
  }

  // Record outcome + style for continuous learning
  if (status === 'sent') {
    applied[key] = { ts: Date.now(), channel, company: job.company || job.project, title: job.title };
    await recordOutcome(env, key, 'sent', {
      score: job.debate_score || job.score || 0,
      source: job.source,
      company: job.company || job.project,
    });
    await recordStyle(env, opening, 'sent');
  }

  // Always notify owner with the drafted DM
  await sendApplyNotification(env, job, message, `${status} via ${channel}`).catch(() => {});

  return { status, channel, key, message };
}
