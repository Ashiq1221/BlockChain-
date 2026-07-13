// Telegram Group Scanner — monitors all groups the bot is in
// Detects job posts via keywords, structures them as leads for immediate reply
// Uses Bot API getUpdates with KV-persisted offset so each cron picks up where it left off
// Also handles /lingosetup@BotName commands + bot-join events in the SAME update batch
// (only one getUpdates call per cycle — prevents offset conflicts)

const OFFSET_KEY   = 'tg_update_offset';
const SEEN_KEY     = 'tg_seen_posts';
const BOT_USERNAME = 'AshiqAibot';

const JOB_KEYWORDS = [
  'hiring', 'we are hiring', 'now hiring', 'looking for a', 'open position',
  'open role', 'join our team', 'apply now', 'apply here', 'dm to apply',
  'dm me', 'dm us', 'send cv', 'send resume',
  'community manager', 'community lead', 'community mod', 'moderator',
  'ambassador', 'brand ambassador',
  'content creator', 'content writer', 'copywriter',
  'social media manager', 'growth manager', 'growth hacker',
  'ai trainer', 'data annotator', 'prompt engineer',
  '#hiring', '#jobs', '#web3jobs', '#cryptojobs', '#jobopening',
];

const ROLE_PATTERNS = /\b(community manager|community lead|ambassador|moderator|content creator|social media manager|growth manager|ai trainer|data annotator|prompt engineer|copywriter|community mod)\b/i;

async function tgPost(env, method, body) {
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

// Extract @AshiqAibot mention request from a message; returns '__help__' for bare mentions
function extractBotMention(msg) {
  const text     = msg.text || msg.caption || '';
  const entities = msg.entities || msg.caption_entities || [];

  for (const entity of entities) {
    if (entity.type === 'mention') {
      const mentioned = text.slice(entity.offset, entity.offset + entity.length);
      if (mentioned.toLowerCase() === `@${BOT_USERNAME.toLowerCase()}`) {
        const req = text.slice(entity.offset + entity.length).trim();
        return req || '__help__';
      }
    }
  }

  const re = new RegExp(`@${BOT_USERNAME}(?:\\s+(.+))?`, 'is');
  const m  = text.match(re);
  if (m) return (m[1] || '').trim() || '__help__';
  return null;
}

function isJobPost(text) {
  if (!text || text.length < 30) return false;
  const lower = text.toLowerCase();
  return JOB_KEYWORDS.some(kw => lower.includes(kw));
}

function structureLead(msg) {
  const text  = msg.text || msg.caption || '';
  const chat  = msg.chat || {};
  const title = (text.match(ROLE_PATTERNS) || [])[0] || 'Community / Content Role';
  const lines = text.split('\n').filter(Boolean);

  const company = chat.title || lines[0]?.slice(0, 60) || 'Unknown Project';
  const handles = (text.match(/@\w{3,}/g) || []).filter(h => h !== `@${chat.username}`);

  return {
    lead_id:         `tg_${chat.id}_${msg.message_id}`,
    title,
    project:         company,
    company,
    source:          'telegram_group',
    description:     text.slice(0, 600),
    telegram:        chat.username || null,
    tg_chat_id:      chat.id,
    tg_msg_id:       msg.message_id,
    founder_handles: handles.slice(0, 3),
    score:           null,
    job_url:         null,
  };
}

// Returns { leads, lingoSetup }
// lingoSetup is non-null when /lingosetup command or bot-join event is detected
export async function scanGroups(env) {
  if (!env.TELEGRAM_BOT_TOKEN) return { leads: [], lingoSetup: null };

  const offsetRaw = await env.KV.get(OFFSET_KEY);
  const offset    = offsetRaw ? parseInt(offsetRaw, 10) : undefined;

  // Include my_chat_member so we catch bot-join events (no privacy mode needed)
  const body = {
    limit: 100,
    allowed_updates: ['message', 'channel_post', 'my_chat_member'],
  };
  if (offset) body.offset = offset;

  let updates;
  try {
    const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getUpdates`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    updates = d.ok ? d.result : null;
  } catch { updates = null; }

  if (!Array.isArray(updates) || !updates.length) return { leads: [], lingoSetup: null };

  // Advance offset so next run starts after these updates
  await env.KV.put(OFFSET_KEY, String(updates[updates.length - 1].update_id + 1));

  const seenArr = JSON.parse(await env.KV.get(SEEN_KEY) || '[]');
  const seen    = new Set(seenArr);
  const newSeen = [];
  const leads   = [];
  const botMentions = [];
  let lingoSetup = null;

  for (const u of updates) {
    // ── Bot join event (my_chat_member) — works even with privacy mode ON ──
    if (u.my_chat_member) {
      const mcm       = u.my_chat_member;
      const newStatus = mcm.new_chat_member?.status;
      if (['member', 'administrator'].includes(newStatus)) {
        const chat = mcm.chat;
        const t    = chat?.type;
        if (['group', 'supergroup', 'channel'].includes(t)) {
          // Bot was just added to this group — candidate for LingoAI poster
          lingoSetup = lingoSetup || { chatId: String(chat.id), title: chat.title || '', source: 'join_event' };
        }
      }
      continue;
    }

    const msg = u.message || u.channel_post;
    if (!msg) continue;

    const type = msg.chat?.type;
    if (!['group', 'supergroup', 'channel'].includes(type)) continue;

    const text = msg.text || msg.caption || '';

    // ── /lingosetup command — works with @BotName form even when privacy is ON ──
    if (text.match(/^\/lingosetup(@\w+)?(\s|$)/i)) {
      lingoSetup = { chatId: String(msg.chat.id), title: msg.chat.title || '', source: 'command', replyTo: msg };
      continue; // don't also treat it as a job post
    }

    // ── Bot @mention detection ────────────────────────────────────────────────
    const mentionReq = extractBotMention(msg);
    if (mentionReq) {
      botMentions.push({ chatId: String(msg.chat.id), request: mentionReq, replyToMsgId: msg.message_id });
      continue; // don't also treat as a job post
    }

    // ── Job post detection ────────────────────────────────────────────────────
    const postKey = `${msg.chat.id}:${msg.message_id}`;
    if (seen.has(postKey)) continue;
    if (!isJobPost(text)) continue;

    leads.push(structureLead(msg));
    newSeen.push(postKey);
  }

  if (newSeen.length) {
    const merged = [...seenArr, ...newSeen].slice(-1000);
    await env.KV.put(SEEN_KEY, JSON.stringify(merged));
  }

  // If /lingosetup came from a command, reply immediately
  if (lingoSetup?.source === 'command' && lingoSetup.replyTo) {
    await tgPost(env, 'sendMessage', {
      chat_id:    lingoSetup.chatId,
      text:       '✅ <b>LingoAI poster activated!</b>\nThis group will receive AI-generated community discussions every few hours, starting next cycle.',
      parse_mode: 'HTML',
    });
  }

  return { leads, lingoSetup, botMentions };
}
