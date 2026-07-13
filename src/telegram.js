// Telegram Bot API integration
// Replaces Pyrogram — uses HTTP Bot API (no persistent connection needed)
// Bot must be added to groups as admin to post there.

const TG_API = 'https://api.telegram.org';

async function tgPost(env, method, body) {
  if (!env.TELEGRAM_BOT_TOKEN) return null;
  try {
    const r = await fetch(`${TG_API}/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (r.ok) return (await r.json()).result;
  } catch { /* ignore */ }
  return null;
}

// Send a message to any chat (group username or user ID)
export async function sendMessage(env, chatId, text, replyToId = null) {
  const body = { chat_id: chatId, text: text.slice(0, 4096), parse_mode: 'HTML' };
  if (replyToId) body.reply_to_message_id = replyToId;
  return tgPost(env, 'sendMessage', body);
}

// Notify the owner (you) with a rich update
export async function notifyOwner(env, text) {
  if (!env.TELEGRAM_OWNER_ID) return;
  await sendMessage(env, env.TELEGRAM_OWNER_ID, text);
}

// Try to post in a group where the bot is already a member
// Returns true on success, false if bot is not in the group
export async function postInGroup(env, groupHandle, message, replyToId = null) {
  const chatId = groupHandle.startsWith('@') ? groupHandle : `@${groupHandle}`;
  const result = await sendMessage(env, chatId, message, replyToId);
  return !!result;
}

// Search recent messages in a group for hiring keywords
export async function findJobPostInGroup(env, groupHandle) {
  const chatId = groupHandle.startsWith('@') ? groupHandle : `@${groupHandle}`;
  const JOB_KW = ['hiring','we are hiring','now hiring','looking for','open position',
    'community manager','ambassador','moderator','content creator','social media manager',
    'apply','join our team','open role','community lead','growth manager'];

  try {
    // Get recent updates — in a bot context we get updates via getUpdates
    // For groups, we can use getChatHistory via Bot API messages
    // Note: bots can only access messages they're mentioned in or all messages if privacy mode is off
    const r = await tgPost(env, 'getUpdates', { limit: 100, allowed_updates: ['message'] });
    if (!Array.isArray(r)) return null;

    for (const update of r.reverse()) {
      const msg = update.message;
      if (!msg?.text) continue;
      const chat = msg.chat;
      if (!chat) continue;
      // Match by username or title
      const matches = (chat.username && `@${chat.username}` === chatId)
                   || chat.title?.toLowerCase().includes(groupHandle.toLowerCase().replace('@',''));
      if (!matches) continue;
      const low = msg.text.toLowerCase();
      if (JOB_KW.some(kw => low.includes(kw))) {
        return { msg_id: msg.message_id, text: msg.text.slice(0, 200) };
      }
    }
  } catch { /* ignore */ }
  return null;
}

// Send the owner a formatted "ready to apply" notification
// with the pre-written DM they can forward to the founder
export async function sendApplyNotification(env, job, message, status) {
  const title   = job.title    || 'Web3 Role';
  const company = job.company  || 'Unknown';
  const jobUrl  = job.job_url  || '';
  const founder = job.founder_x || '';
  const tgGroup = job.telegram  || '';

  const lines = [
    `<b>🎯 Application: ${title} @ ${company}</b>`,
    '',
    `<b>Status:</b> ${status}`,
    '',
    `<b>📩 Message sent:</b>`,
    `<i>${message.slice(0, 600)}</i>`,
    '',
  ];
  if (founder)  lines.push(`<b>👤 Founder on X:</b> @${founder} — send them this DM too`);
  if (tgGroup)  lines.push(`<b>💬 TG Group:</b> @${tgGroup}`);
  if (jobUrl)   lines.push(`<b>🔗 Source:</b> ${jobUrl}`);

  await notifyOwner(env, lines.join('\n'));
}
