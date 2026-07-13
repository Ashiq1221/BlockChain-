// Telegram outreach via Bot API
// Personal account (MTProto) support is blocked by CF Workers' WASM restriction —
// @mtkruto/browser bundles WebAssembly which Cloudflare rejects at upload time.
// All sends use the bot. The bot can DM any user who has started it, and can
// post/reply in any group it has been added to.

const SENT_KEY = 'tg_sent_msgs';

// ── Bot API helper ────────────────────────────────────────────────────────────

async function botPost(env, method, body) {
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

async function trackSent(env, type, peer, msgId) {
  const sent = JSON.parse(await env.KV.get(SENT_KEY) || '{}');
  sent[`${type}:${peer}:${msgId}`] = { type, peer, msgId, ts: Date.now() };
  const keys = Object.keys(sent);
  if (keys.length > 200) delete sent[keys[0]];
  await env.KV.put(SENT_KEY, JSON.stringify(sent));
}

// ── Auth stubs (MTProto not available) ───────────────────────────────────────

export async function isAuthed() { return false; }

export async function startAuth() {
  return { ok: false, reason: 'MTProto requires WASM which CF Workers blocks. Bot API is used instead.' };
}

export async function verifyCode() {
  return { ok: false, reason: 'MTProto not available — see POST /tg-auth.' };
}

export async function verify2FA() {
  return { ok: false, reason: 'MTProto not available — see POST /tg-auth.' };
}

// ── DM a user via bot ─────────────────────────────────────────────────────────
// Works if the target user has started a chat with the bot.

export async function sendUserDM(env, username, message) {
  const handle = username.replace('@', '').trim();
  const result = await botPost(env, 'sendMessage', {
    chat_id:    `@${handle}`,
    text:       message.slice(0, 4096),
    parse_mode: 'HTML',
  });
  if (result?.message_id) {
    await trackSent(env, 'dm_bot', handle, result.message_id);
    return { ok: true, msg_id: result.message_id, via: 'bot' };
  }
  return { ok: false, reason: 'Bot cannot DM this user (they must start the bot first)' };
}

// ── Post in a group via bot ───────────────────────────────────────────────────

export async function postInGroupAsUser(env, groupUsername, message, replyToMsgId = null) {
  const handle = groupUsername.replace('@', '').replace('t.me/', '').trim();
  const body = {
    chat_id:    `@${handle}`,
    text:       message.slice(0, 4096),
    parse_mode: 'HTML',
  };
  if (replyToMsgId) body.reply_to_message_id = replyToMsgId;
  const result = await botPost(env, 'sendMessage', body);
  if (result?.message_id) {
    await trackSent(env, 'group_bot', handle, result.message_id);
    return { ok: true, msg_id: result.message_id, via: 'bot' };
  }
  return { ok: false, reason: 'Bot not in group or group not found' };
}

// ── Reply to a scanned group post ─────────────────────────────────────────────

export async function replyToPost(env, chatId, msgId, message) {
  const result = await botPost(env, 'sendMessage', {
    chat_id:             chatId,
    text:                message.slice(0, 4096),
    parse_mode:          'HTML',
    reply_to_message_id: msgId,
  });
  if (result?.message_id) {
    await trackSent(env, 'group_reply', String(chatId), result.message_id);
    return { ok: true, msg_id: result.message_id, via: 'bot' };
  }
  return { ok: false, reason: 'send_failed', chat_id: chatId };
}

// ── Reply check (not available via Bot API) ───────────────────────────────────

export async function checkReplies() { return []; }
