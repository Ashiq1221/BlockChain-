// Cloudflare Workers entry point — full pipeline orchestrator
// Scheduled: Cron Trigger every 3 hours
// Fetch: REST endpoints for status, manual trigger, outcome logging, draft review

import { runXPipeline }                        from './x-pipeline.js';
import { discoverLeads, importPastedLead }     from './discovery.js';
import { enrichLeads }                          from './research.js';
import { judgeLeads, logOutcome }              from './debate.js';
import { draftBatch, logDraftOutcome, learningReport, getQueue } from './writer.js';
import { applyToJob, craftApplication }         from './apply.js';
import { loadApplied, saveApplied, loadTargetGroups } from './state.js';
import { notifyOwner, sendMessage }            from './telegram.js';
import { startAuth, verifyCode, verify2FA, isAuthed, checkReplies } from './telegram-user.js';
import { loadLearningContext, recordOutcome }  from './learning.js';
import { scanGroups }                          from './group-scanner.js';
import { TG_BOTS_DB, SCAN_TARGETS, dbStats }  from './tg-bots-db.js';
import { runLingoPoster, setupLingoGroup, lingoStatus, updateRLScores, setHotTopic } from './lingo-poster.js';
import { runOrchestra, sendHelpMessage }               from './lingo-orchestra.js';

// ── Telegram helpers ──────────────────────────────────────────────────────────
const WORKER_URL = 'https://job-agent.ashiqjobagent.workers.dev';

async function tgCall(env, method, body) {
  if (!env.TELEGRAM_BOT_TOKEN) return null;
  try {
    const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/${method}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    return await r.json();
  } catch { return null; }
}

async function ensureWebhook(env) {
  if (!env.TELEGRAM_BOT_TOKEN) return;
  try {
    // Delete first so we get a clean registration every time
    await tgCall(env, 'deleteWebhook', { drop_pending_updates: false });
    const d = await tgCall(env, 'setWebhook', {
      url:             `${WORKER_URL}/webhook`,
      allowed_updates: ['message', 'channel_post', 'my_chat_member', 'message_reaction'],
    });
    await notifyOwner(env,
      d?.ok
        ? `✅ Webhook active: ${WORKER_URL}/webhook`
        : `⚠️ Webhook failed: ${d?.description || JSON.stringify(d)}`
    ).catch(() => {});
  } catch {}
}

// ── Minute-cron fallback: processes @mentions via getUpdates when webhook is down
const MENTION_OFFSET_KEY = 'tg_mention_offset';
const MENTION_SEEN_KEY   = 'tg_mention_seen';

async function fastMentionPoll(env) {
  if (!env.TELEGRAM_BOT_TOKEN) return;

  // If webhook is active, Telegram won't deliver to getUpdates — skip
  const whi = await tgCall(env, 'getWebhookInfo', {});
  if (whi?.ok && whi.result?.url) return;

  const offsetRaw = await env.KV.get(MENTION_OFFSET_KEY);
  const offset    = offsetRaw ? parseInt(offsetRaw, 10) : undefined;
  const body      = { limit: 100, allowed_updates: ['message', 'channel_post'] };
  if (offset) body.offset = offset;

  const d = await tgCall(env, 'getUpdates', body);
  if (!d?.ok || !d.result?.length) return;

  await env.KV.put(MENTION_OFFSET_KEY, String(d.result[d.result.length - 1].update_id + 1));

  const seenArr = JSON.parse(await env.KV.get(MENTION_SEEN_KEY) || '[]');
  const seen    = new Set(seenArr);
  const newSeen = [];

  for (const u of d.result) {
    const msg = u.message || u.channel_post;
    if (!msg) continue;

    const key = `${msg.chat.id}:${msg.message_id}`;
    if (seen.has(key)) continue;

    const text     = msg.text || msg.caption || '';
    const entities = msg.entities || msg.caption_entities || [];

    let mentionReq = null;
    for (const e of entities) {
      if (e.type === 'mention') {
        const m = text.slice(e.offset, e.offset + e.length);
        if (m.toLowerCase() === '@ashiqaibot') {
          mentionReq = text.slice(e.offset + e.length).trim() || '__help__';
          break;
        }
      }
    }
    if (!mentionReq) {
      const m = text.match(/@AshiqAibot(?:\s+(.+))?/is);
      if (m) mentionReq = (m[1] || '').trim() || '__help__';
    }

    if (mentionReq) {
      newSeen.push(key);
      const chatId  = String(msg.chat.id);
      const replyId = msg.message_id;
      if (mentionReq === '__help__') {
        await sendHelpMessage(env, chatId, replyId).catch(() => {});
      } else {
        await runOrchestra(env, mentionReq, chatId, replyId).catch(() => {});
      }
    }
  }

  if (newSeen.length) {
    await env.KV.put(MENTION_SEEN_KEY, JSON.stringify([...seenArr, ...newSeen].slice(-500)));
  }
}

// ── Webhook update processor ──────────────────────────────────────────────────
async function handleTelegramUpdate(env, update) {

  // ── message_reaction: someone reacted to a bot message ─────────────────────
  if (update.message_reaction) {
    const reaction = update.message_reaction;
    // Only count new reactions (not removed ones) and only non-empty reaction lists
    if (reaction.new_reaction?.length > 0) {
      await updateRLScores(env, reaction.message_id, 'reaction').catch(() => {});
    }
    return;
  }

  const msg = update.message || update.channel_post;

  if (msg) {
    const chatType = msg.chat?.type;
    const chatId   = String(msg.chat.id);
    const replyId  = msg.message_id;
    const text     = msg.text || msg.caption || '';

    // ── Human replies to bot messages: RL signal ────────────────────────────
    // If this is a reply to another message AND the reply target was likely posted
    // by the bot (i.e. we have it in our RL tracking), credit it as engagement.
    if (msg.reply_to_message && !msg.from?.is_bot) {
      const repliedToId = msg.reply_to_message.message_id;
      await updateRLScores(env, repliedToId, 'reply').catch(() => {});
    }

    // /lingosetup command
    if (text.match(/^\/lingosetup(@\w+)?(\s|$)/i)) {
      await env.KV.put('lingo_group_chat_id', chatId);
      await tgCall(env, 'sendMessage', {
        chat_id: chatId, parse_mode: 'HTML',
        text: '✅ <b>LingoAI poster activated!</b>\nThis group will receive AI-generated community discussions every few hours.',
      });
      return;
    }

    // @AshiqAibot mention in group/channel
    if (['group', 'supergroup', 'channel'].includes(chatType)) {
      const entities = msg.entities || msg.caption_entities || [];
      let mentionReq = null;

      for (const e of entities) {
        if (e.type === 'mention') {
          const m = text.slice(e.offset, e.offset + e.length);
          if (m.toLowerCase() === '@ashiqaibot') {
            mentionReq = text.slice(e.offset + e.length).trim() || '__help__';
            break;
          }
        }
      }
      if (!mentionReq) {
        const m = text.match(/@AshiqAibot(?:\s+(.+))?/is);
        if (m) mentionReq = (m[1] || '').trim() || '__help__';
      }

      if (mentionReq) {
        // Debug: notify owner so we know the mention was detected
        await notifyOwner(env,
          `🔔 <b>@mention detected</b>\nChat: ${chatId}\nRequest: <i>${mentionReq.slice(0, 100)}</i>`
        ).catch(() => {});

        // Instant ack to the group
        const ackResult = await tgCall(env, 'sendMessage', {
          chat_id: chatId, reply_to_message_id: replyId, parse_mode: 'HTML',
          text: mentionReq === '__help__'
            ? '📖 Loading commands...'
            : `⚡ <b>Got it!</b> Generating: <i>${mentionReq.slice(0, 80)}</i>\nFirst messages in ~15 seconds...`,
        });

        // If ack failed, tell owner why (bot may have been removed or lacks permission)
        if (!ackResult?.ok) {
          await notifyOwner(env,
            `❌ <b>Bot can't post to group ${chatId}</b>\nError: ${ackResult?.description || 'null response'}\n\nFix: re-add @AshiqAibot to the group as admin`
          ).catch(() => {});
          return;
        }

        if (mentionReq === '__help__') {
          await sendHelpMessage(env, chatId, replyId).catch(async err => {
            await tgCall(env, 'sendMessage', { chat_id: chatId, text: `❌ Error: ${String(err).slice(0, 200)}` });
          });
        } else {
          await runOrchestra(env, mentionReq, chatId, replyId).catch(async err => {
            await tgCall(env, 'sendMessage', { chat_id: chatId, text: `❌ Orchestra error: ${String(err).slice(0, 200)}` });
          });
        }
      }
    }
  }

  // Bot added to a group
  if (update.my_chat_member) {
    const mcm = update.my_chat_member;
    if (['member', 'administrator'].includes(mcm.new_chat_member?.status)) {
      const chat = mcm.chat;
      if (['group', 'supergroup', 'channel'].includes(chat?.type)) {
        await env.KV.put('lingo_group_chat_id', String(chat.id));
      }
    }
  }
}

// ── Pipeline ──────────────────────────────────────────────────────────────────

async function runCycle(env, ctx) {
  const start = Date.now();
  await notifyOwner(env, '🤖 <b>Job Agent scanning…</b>');

  try {
    // ── Stage 0: Check replies ────────────────────────────────────────────────
    const replies = await checkReplies(env).catch(() => []);
    for (const r of replies) {
      await recordOutcome(env, `dm:${r.peer}`, 'replied', { company: r.peer });
      await notifyOwner(env, `💬 <b>Reply from @${r.peer}:</b>\n"${r.their_reply}"`);
    }

    // ── Stage 1: Discovery — board leads first (fast), X pipeline second ────────
    const boardLeads  = await discoverLeads(env);
    const scanResult  = await scanGroups(env).catch(() => ({ leads: [], lingoSetup: null }));
    const groupLeads  = scanResult.leads || [];

    // If /lingosetup command or bot-join event detected, save the group ID
    if (scanResult.lingoSetup?.chatId) {
      await env.KV.put('lingo_group_chat_id', scanResult.lingoSetup.chatId);
      await notifyOwner(env,
        `✅ <b>LingoAI poster configured</b>\nGroup: <b>${scanResult.lingoSetup.title || scanResult.lingoSetup.chatId}</b>\nSource: ${scanResult.lingoSetup.source}\nPosting starts this cycle.`
      ).catch(() => {});
    }

    // Handle @AshiqAibot mentions — run orchestra for each (fire-and-forget)
    for (const mention of (scanResult.botMentions || [])) {
      if (mention.request === '__help__') {
        ctx.waitUntil(sendHelpMessage(env, mention.chatId, mention.replyToMsgId).catch(() => {}));
      } else {
        ctx.waitUntil(runOrchestra(env, mention.request, mention.chatId, mention.replyToMsgId).catch(() => {}));
      }
    }

    // ── Notify immediately after discovery — before any slow research ─────────
    for (const job of groupLeads)  await notifyOwner(env, fmtGroupLead(job)).catch(() => {});
    for (const lead of boardLeads) await notifyOwner(env, fmtAnyLead(lead, 'Board')).catch(() => {});

    if (!boardLeads.length && !groupLeads.length) {
      await notifyOwner(env, '🔍 No new board/group leads this cycle — running X pipeline…');
    }

    // X pipeline runs after board notifications are already sent
    const xJobs = await runXPipeline(env).catch(() => []);
    for (const job of xJobs) await notifyOwner(env, fmtAnyLead(job, 'X / Twitter')).catch(() => {});

    if (!boardLeads.length && !xJobs.length && !groupLeads.length) {
      await notifyOwner(env, '⚠️ All sources returned 0 new leads. Cache may be full — use /reset-cache if this persists.');
    }

    // ── Stage 2: Research ─────────────────────────────────────────────────────
    const enriched = boardLeads.length ? await enrichLeads(env, boardLeads) : [];

    // ── Stage 3: Debate ───────────────────────────────────────────────────────
    let boardVerdicts = { apply: [], watch: [], skip: [] };
    if (enriched.length) boardVerdicts = await judgeLeads(env, enriched);

    if (boardVerdicts.apply.length || boardVerdicts.watch.length) {
      await notifyOwner(env, fmtVerdicts(boardVerdicts));
    }

    // ── Stage 4: Drafts ───────────────────────────────────────────────────────
    const allVerdicts = [...boardVerdicts.apply, ...boardVerdicts.watch];
    const drafts = allVerdicts.length ? await draftBatch(env, allVerdicts) : [];

    // ── Stage 5: Apply + notify ───────────────────────────────────────────────
    const applied = await loadApplied(env);
    const lCtx    = await loadLearningContext(env);
    let appliedCount = 0, draftCount = 0;

    // Group leads: craft reply → notify what will be sent → send it
    for (const job of groupLeads) {
      const msg = await craftApplication(env, job, lCtx).catch(() => null);
      if (msg) await notifyOwner(env, fmtReplyPreview(job, msg));
      const res = await applyToJob(env, job, applied, lCtx);
      if (res.status === 'sent') {
        appliedCount++;
        await notifyOwner(env, `✅ <b>Reply sent</b> → ${job.telegram ? '@' + job.telegram : 'group ' + job.tg_chat_id}`);
      }
    }

    // X leads: auto-apply if score ≥ 7 (already notified at discovery above)
    for (const job of xJobs) {
      const score = job.debate_score || job.score || 0;
      if (score >= 7) {
        const res = await applyToJob(env, job, applied, lCtx);
        if (res.status === 'sent') {
          appliedCount++;
          await notifyOwner(env, `✅ <b>Applied</b> → ${job.company || job.project} via ${job.telegram ? '@' + job.telegram : 'DM'}`);
        }
      }
    }

    // Board drafts: full draft → auto-apply if score ≥ 8
    for (const draft of drafts) {
      await sendDraftNotification(env, draft);
      if (draft.score >= 8) {
        const job = { ...draft, telegram: draft.telegram_group, company: draft.project };
        const res = await applyToJob(env, job, applied, lCtx);
        if (res.status === 'sent') {
          appliedCount++;
          await notifyOwner(env, `✅ <b>Applied</b> → ${draft.project} [${draft.score}/10]`);
        }
      }
      draftCount++;
    }

    await saveApplied(env, applied);

    const summary = [
      `📊 <b>Cycle done</b> (${Math.round((Date.now() - start) / 1000)}s)`,
      `• Group posts found: ${groupLeads.length}`,
      `• Board leads: ${boardLeads.length} → researched: ${enriched.length}`,
      `• Verdicts: ✅ ${boardVerdicts.apply.length} apply  👀 ${boardVerdicts.watch.length} watch  ❌ ${boardVerdicts.skip?.length || 0} skip`,
      `• X leads: ${xJobs.length}`,
      `• Auto-sent: ${appliedCount}  |  Drafts: ${draftCount}`,
      `• Replies received: ${replies.length}`,
      `• Total sent ever: ${lCtx.total_applied || 0}  reply rate: ${lCtx.reply_rate_pct || '?'}%`,
    ].join('\n');

    await notifyOwner(env, summary);
    return { ok: true, board_leads: boardLeads.length, applied: appliedCount, replies: replies.length };

  } catch (err) {
    await notifyOwner(env, `❌ <b>Agent error:</b> ${String(err).slice(0, 300)}`).catch(() => {});
    return { ok: false, error: String(err) };
  }
}

// ── Notification formatters ───────────────────────────────────────────────────

function fmtGroupLead(job) {
  const group = job.telegram ? `@${job.telegram}` : `Group ${job.tg_chat_id}`;
  const handles = job.founder_handles?.length ? job.founder_handles.join(' ') : '';
  return [
    `🔔 <b>Hiring post in ${group}</b>`,
    `Role: <b>${job.title}</b>`,
    `Project: ${job.company}`,
    handles ? `👤 Founders/contacts: ${handles}` : '',
    ``,
    `<i>${job.description.slice(0, 500)}</i>`,
  ].filter(Boolean).join('\n');
}

function fmtReplyPreview(job, msg) {
  const group = job.telegram ? `@${job.telegram}` : `Group ${job.tg_chat_id}`;
  return [
    `📤 <b>Sending reply to ${group}:</b>`,
    `<i>${msg.slice(0, 600)}</i>`,
  ].join('\n');
}

// One message per lead — fires immediately when the lead is found
function fmtAnyLead(lead, source) {
  const score = lead.debate_score || lead.score;
  // Extract URL from description if job_url not set explicitly
  const urlFromDesc = (lead.description || '').match(/https?:\/\/[^\s]+/)?.[0] || '';
  const applyUrl = lead.job_url || lead.apply_url || urlFromDesc;
  return [
    `📌 <b>Job Found · ${source}</b>`,
    `Role: <b>${lead.title || 'Community / Web3 Role'}</b>`,
    `Company: ${lead.company || lead.project || '?'}`,
    score != null ? `Score: ${score}/10` : '',
    lead.debate_angle ? `Angle: ${lead.debate_angle}` : '',
    ``,
    lead.description ? `<i>${(lead.description || '').replace(/https?:\/\/\S+/g, '').trim().slice(0, 400)}</i>` : '',
    ``,
    applyUrl              ? `🔗 Apply: ${applyUrl}` : '',
    lead.telegram         ? `💬 Group: @${lead.telegram}` : '',
    lead.founder_x        ? `👤 Founder X: @${lead.founder_x}` : '',
    lead.founder_handles?.length ? `👤 TG contacts: ${lead.founder_handles.join(' ')}` : '',
    lead.source           ? `Source: ${lead.source}` : '',
  ].filter(Boolean).join('\n');
}

function fmtVerdicts(verdicts) {
  const lines = [`⚖️ <b>Debate Results</b>\n`];
  for (const v of verdicts.apply) {
    lines.push(`✅ <b>APPLY [${v.score}/10]</b> ${v.title} @ ${v.company || v.project}`);
    if (v.angle)    lines.push(`   Angle: ${v.angle}`);
    if (v.job_url)  lines.push(`   🔗 ${v.job_url}`);
    if (v.telegram) lines.push(`   💬 @${v.telegram}`);
    if (v.founder_handles?.length) lines.push(`   👤 ${v.founder_handles.join(' ')}`);
  }
  if (verdicts.apply.length && verdicts.watch.length) lines.push('');
  for (const v of verdicts.watch) {
    lines.push(`👀 <b>WATCH [${v.score}/10]</b> ${v.title} @ ${v.company || v.project}`);
    if (v.job_url)  lines.push(`   🔗 ${v.job_url}`);
    if (v.telegram) lines.push(`   💬 @${v.telegram}`);
  }
  return lines.join('\n');
}

async function sendDraftNotification(env, draft) {
  const lines = [
    `📝 <b>Draft [${draft.score}/10]:</b> ${draft.title} @ ${draft.project}`,
    draft.angle ? `Angle: ${draft.angle}` : '',
    draft.risks?.length ? `⚠️ Risks: ${draft.risks.join(', ')}` : '',
    draft.job_url ? `🔗 Apply: ${draft.job_url}` : '',
    draft.founder_handles?.length ? `👤 ${draft.founder_handles.join('  ')}` : '',
    '',
    `<b>── YOUR APPLICATION ──</b>`,
    `<i>${(draft.application || '').slice(0, 900)}</i>`,
    '',
    `<b>── FOUNDER DM ──</b>`,
    `<i>${(draft.dm || '').slice(0, 350)}</i>`,
    '',
    `📌 <code>${draft.lead_id}</code>  |  POST /draft-outcome?lead_id=${draft.lead_id}&outcome=replied|ignored|interview`,
  ].filter(l => l !== undefined).join('\n');

  await notifyOwner(env, lines);
}

// ── /setup HTML page (removed — MTProto blocked by CF Workers WASM restriction) ──

const SETUP_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Telegram Account Setup</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f1117;color:#e2e8f0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}
  .card{background:#1a1f2e;border:1px solid #2d3748;border-radius:16px;padding:28px 24px;width:100%;max-width:400px}
  h1{font-size:20px;font-weight:700;color:#fff;margin-bottom:4px}
  .sub{font-size:13px;color:#718096;margin-bottom:24px}
  .step{display:none}
  .step.active{display:block}
  label{display:block;font-size:13px;color:#a0aec0;margin-bottom:6px;font-weight:500}
  input{width:100%;padding:13px 14px;background:#111827;border:1px solid #2d3748;border-radius:10px;color:#fff;font-size:16px;outline:none;transition:border .2s}
  input:focus{border-color:#4299e1}
  button{width:100%;padding:14px;margin-top:14px;background:#3182ce;color:#fff;border:none;border-radius:10px;font-size:16px;font-weight:600;cursor:pointer;transition:background .2s}
  button:hover{background:#2b6cb0}
  button:disabled{background:#2d3748;color:#4a5568;cursor:not-allowed}
  .msg{margin-top:14px;padding:12px 14px;border-radius:10px;font-size:14px;line-height:1.5;display:none}
  .msg.ok{background:#1a3a2a;border:1px solid #2f855a;color:#68d391;display:block}
  .msg.err{background:#2d1b1b;border:1px solid #c53030;color:#fc8181;display:block}
  .msg.info{background:#1a2744;border:1px solid #2b6cb0;color:#63b3ed;display:block}
.steps-row{display:flex;gap:8px;margin-bottom:22px}
  .dot{flex:1;height:4px;border-radius:2px;background:#2d3748;transition:background .3s}
  .dot.done{background:#3182ce}
  .checkmark{font-size:48px;text-align:center;margin:10px 0 16px}
</style>
</head>
<body>
<div class="card">
  <h1>🔐 Account Setup</h1>
  <p class="sub">Connect your personal Telegram account</p>

  <div class="steps-row">
    <div class="dot" id="d1"></div>
    <div class="dot" id="d2"></div>
    <div class="dot" id="d3"></div>
  </div>

  <!-- Step 1: Phone -->
  <div class="step active" id="s1">
    <label>Your phone number</label>
    <input id="phone" type="tel" placeholder="+91XXXXXXXXXX" autocomplete="tel">
    <button id="btn1" onclick="sendPhone()">Send Code</button>
    <div class="msg" id="m1"></div>
  </div>

  <!-- Step 2: OTP -->
  <div class="step" id="s2">
    <label>Code from Telegram</label>
    <input id="code" type="number" placeholder="12345" inputmode="numeric">
    <button id="btn2" onclick="sendCode()">Verify Code</button>
    <div class="msg" id="m2"></div>
  </div>

  <!-- Step 3: 2FA password (shown only if needed) -->
  <div class="step" id="s3">
    <label>2FA cloud password</label>
    <input id="pass" type="password" placeholder="Your Telegram password">
    <button id="btn3" onclick="sendPass()">Verify Password</button>
    <div class="msg" id="m3"></div>
  </div>

  <!-- Done -->
  <div class="step" id="s4">
    <div class="checkmark">✅</div>
    <div class="msg ok" id="m4" style="display:block"></div>
  </div>
</div>

<script>
function show(id){document.querySelectorAll('.step').forEach(s=>s.classList.remove('active'));document.getElementById(id).classList.add('active')}
function dot(n){for(let i=1;i<=n;i++)document.getElementById('d'+i).classList.add('done')}
function msg(id,text,type){const el=document.getElementById(id);el.className='msg '+type;el.textContent=text}
function setBtn(id,disabled,text){const b=document.getElementById(id);b.disabled=disabled;b.textContent=text}

async function sendPhone(){
  const phone=document.getElementById('phone').value.trim();
  if(!phone){msg('m1','Enter your phone number','err');return}
  setBtn('btn1',true,'Sending…');
  try{
    const r=await fetch('/tg-auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone})});
    const d=await r.json();
    if(d.ok){dot(1);show('s2');setTimeout(()=>document.getElementById('code').focus(),100)}
    else{msg('m1',d.reason||'Error','err');setBtn('btn1',false,'Send Code')}
  }catch(e){msg('m1','Network error: '+e,'err');setBtn('btn1',false,'Send Code')}
}

async function sendCode(){
  const code=document.getElementById('code').value.trim();
  if(!code){msg('m2','Enter the code','err');return}
  setBtn('btn2',true,'Verifying…');
  try{
    const r=await fetch('/tg-auth-code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});
    const d=await r.json();
    if(d.ok){dot(2);dot(3);showDone(d)}
    else if(d.needs_2fa){dot(2);show('s3');setTimeout(()=>document.getElementById('pass').focus(),100)}
    else{msg('m2',d.reason||'Wrong code','err');setBtn('btn2',false,'Verify Code')}
  }catch(e){msg('m2','Network error: '+e,'err');setBtn('btn2',false,'Verify Code')}
}

async function sendPass(){
  const password=document.getElementById('pass').value;
  if(!password){msg('m3','Enter your 2FA password','err');return}
  setBtn('btn3',true,'Verifying…');
  try{
    const r=await fetch('/tg-auth-2fa',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password})});
    const d=await r.json();
    if(d.ok){dot(3);showDone(d)}
    else{msg('m3',d.reason||'Wrong password','err');setBtn('btn3',false,'Verify Password')}
  }catch(e){msg('m3','Network error: '+e,'err');setBtn('btn3',false,'Verify Password')}
}

function showDone(d){
  show('s4');
  document.getElementById('m4').innerHTML=d.message||'✅ Done! Your personal account is now active.';
}

document.addEventListener('keydown',e=>{
  if(e.key!=='Enter')return;
  if(document.getElementById('s1').classList.contains('active'))sendPhone();
  else if(document.getElementById('s2').classList.contains('active'))sendCode();
  else if(document.getElementById('s3').classList.contains('active'))sendPass();
});
</script>
</body>
</html>`;

// ── CF Worker handlers ────────────────────────────────────────────────────────

export default {
  async scheduled(event, env, ctx) {
    if (event.cron === '*/1 * * * *') {
      // Fast path: only process @AshiqAibot mentions (webhook fallback)
      ctx.waitUntil(fastMentionPoll(env).catch(() => {}));
    } else if (event.cron === '*/10 * * * *') {
      // Lingo poster: ~1000 messages/day (144 runs × 7 msgs)
      ctx.waitUntil(runLingoPoster(env).catch(() => {}));
    } else {
      // Slow path: full job-agent cycle + webhook health (every 3h)
      ctx.waitUntil(ensureWebhook(env).catch(() => {}));
      ctx.waitUntil(runCycle(env, ctx));
    }
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const { pathname, searchParams } = url;

    // GET /status
    if (pathname === '/status' && request.method === 'GET') {
      const applied = await loadApplied(env).catch(() => ({}));
      const targets = await loadTargetGroups(env).catch(() => []);
      return Response.json({
        status: 'running',
        total_applied: Object.keys(applied).length,
        target_groups: targets,
        last_5: Object.entries(applied).slice(-5).map(([k, v]) => ({
          key: k, company: v.company, title: v.title, channel: v.channel,
          applied_at: new Date(v.ts).toISOString(),
        })),
      });
    }

    // POST /run — manual cycle trigger
    if (pathname === '/run' && request.method === 'POST') {
      ctx.waitUntil(runCycle(env, ctx));
      return Response.json({ ok: true, message: 'Cycle started — check Telegram for results in ~60s' });
    }

    // GET /queue — apply queue with draft status
    if (pathname === '/queue' && request.method === 'GET') {
      const queue = await getQueue(env);
      return Response.json({ apply_queue: queue, count: queue.length });
    }

    // GET /report — learning report (reply rate by score band)
    if (pathname === '/report' && request.method === 'GET') {
      const report = await learningReport(env);
      return Response.json(report);
    }

    // GET /draft/:lead_id — read a specific draft
    if (pathname.startsWith('/draft/') && request.method === 'GET') {
      const leadId = pathname.slice('/draft/'.length);
      const drafts = JSON.parse(await env.KV.get('drafts') || '{}');
      if (!drafts[leadId]) return Response.json({ error: 'Draft not found' }, { status: 404 });
      return new Response(drafts[leadId], { headers: { 'Content-Type': 'text/markdown' } });
    }

    // POST /draft-outcome?lead_id=xxx&outcome=replied|ignored|interview
    if (pathname === '/draft-outcome' && request.method === 'POST') {
      const leadId  = searchParams.get('lead_id');
      const outcome = searchParams.get('outcome');
      if (!leadId || !['replied','ignored','interview'].includes(outcome)) {
        return Response.json({ error: 'outcome must be: replied|ignored|interview' }, { status: 400 });
      }
      await logDraftOutcome(env, leadId, outcome);
      return Response.json({ ok: true, lead_id: leadId, outcome });
    }

    // POST /outcome?lead_id=xxx&outcome=replied|ignored|interview|hired|scam
    if (pathname === '/outcome' && request.method === 'POST') {
      const leadId  = searchParams.get('lead_id');
      const outcome = searchParams.get('outcome');
      if (!leadId || !['replied','ignored','interview','hired','scam'].includes(outcome)) {
        return Response.json({ error: 'outcome must be: replied|ignored|interview|hired|scam' }, { status: 400 });
      }
      await logOutcome(env, leadId, outcome);
      return Response.json({ ok: true, lead_id: leadId, outcome });
    }

    // POST /import — paste any job post text, get a structured lead added to the queue
    if (pathname === '/import' && request.method === 'POST') {
      try {
        const { text } = await request.json();
        const lead = await importPastedLead(env, text);
        if (!lead) return Response.json({ error: 'Could not structure lead' }, { status: 400 });
        // Research + debate the pasted lead immediately
        const enriched = await enrichLeads(env, [lead]);
        const { apply, watch } = await judgeLeads(env, enriched);
        const verdict = [...apply, ...watch][0];
        if (verdict) {
          const draft = await draftBatch(env, [verdict]);
          if (draft[0]) await sendDraftNotification(env, draft[0]);
        }
        return Response.json({ ok: true, lead });
      } catch (e) {
        return Response.json({ error: String(e) }, { status: 400 });
      }
    }

    // POST /craft — quick message crafter
    if (pathname === '/craft' && request.method === 'POST') {
      try {
        const job = await request.json();
        const message = await craftApplication(env, job);
        return Response.json({ message });
      } catch (e) {
        return Response.json({ error: String(e) }, { status: 400 });
      }
    }

    // ── Telegram personal account auth (one-time setup) ───────────────────────

    // POST /tg-auth   body: {"phone":"+91XXXXXXXXXX"}
    if (pathname === '/tg-auth' && request.method === 'POST') {
      try {
        const { phone } = await request.json();
        if (!phone) return Response.json({ error: 'phone required' }, { status: 400 });
        const r = await startAuth(env, phone);
        return Response.json(r);
      } catch (e) { return Response.json({ error: String(e) }, { status: 500 }); }
    }

    // POST /tg-auth-code   body: {"code":"12345"}
    if (pathname === '/tg-auth-code' && request.method === 'POST') {
      try {
        const { code } = await request.json();
        if (!code) return Response.json({ error: 'code required' }, { status: 400 });
        const r = await verifyCode(env, code);
        return Response.json(r);
      } catch (e) { return Response.json({ error: String(e) }, { status: 500 }); }
    }

    // POST /tg-auth-2fa   body: {"password":"your2fapassword"}
    if (pathname === '/tg-auth-2fa' && request.method === 'POST') {
      try {
        const { password } = await request.json();
        if (!password) return Response.json({ error: 'password required' }, { status: 400 });
        const r = await verify2FA(env, password);
        return Response.json(r);
      } catch (e) { return Response.json({ error: String(e) }, { status: 500 }); }
    }

    // GET /tg-status — check if personal account is authenticated
    if (pathname === '/tg-status' && request.method === 'GET') {
      const authed = await isAuthed(env);
      return Response.json({ authed, message: authed ? 'Personal TG account active' : 'Not authenticated — POST /tg-auth to set up' });
    }

    // GET /learning — view learning stats
    if (pathname === '/learning' && request.method === 'GET') {
      const ctx = await loadLearningContext(env);
      return Response.json(ctx);
    }

    // GET /tg-db — full Telegram bot/channel database
    if (pathname === '/tg-db' && request.method === 'GET') {
      const region = url.searchParams.get('region'); // optional filter
      const type   = url.searchParams.get('type');   // channel | group | bot
      let entries  = TG_BOTS_DB;
      if (region) entries = entries.filter(e => e.region === region || e.region === 'global');
      if (type)   entries = entries.filter(e => e.type === type);
      return Response.json({ stats: dbStats(), scan_targets: SCAN_TARGETS, entries });
    }

    // GET /export-db — full KV database export for @AshiqAibot
    if (pathname === '/export-db' && request.method === 'GET') {
      const KV_KEYS = [
        'applied_jobs',
        'drafts',
        'draft_outcomes',
        'debate_verdicts',
        'debate_outcomes',
        'seen_leads',
        'apify_run_ids',
        'target_groups',
        'posted_groups',
        'tg_update_offset',
        'tg_seen_posts',
        'learning_context',
      ];

      const db = { bot: '@AshiqAibot', exported_at: new Date().toISOString(), data: {} };

      await Promise.all(KV_KEYS.map(async key => {
        try {
          const raw = await env.KV.get(key);
          if (raw === null) { db.data[key] = null; return; }
          try { db.data[key] = JSON.parse(raw); }
          catch { db.data[key] = raw; }
        } catch { db.data[key] = null; }
      }));

      // Summary counts
      db.summary = {
        applied_jobs:    Object.keys(db.data.applied_jobs  || {}).length,
        drafts:          Object.keys(db.data.drafts        || {}).length,
        draft_outcomes:  (db.data.draft_outcomes  || []).length,
        debate_verdicts: (db.data.debate_verdicts || []).length,
        debate_outcomes: (db.data.debate_outcomes || []).length,
        seen_leads:      (db.data.seen_leads      || []).length,
        tg_seen_posts:   (db.data.tg_seen_posts   || []).length,
      };

      const fmt = url.searchParams.get('format');
      if (fmt === 'json') {
        return new Response(JSON.stringify(db, null, 2), {
          headers: {
            'Content-Type': 'application/json',
            'Content-Disposition': `attachment; filename="ashiqaibot-db-${new Date().toISOString().slice(0,10)}.json"`,
          },
        });
      }
      return Response.json(db);
    }

    // GET /groups — Telegram group scan stats
    if (pathname === '/groups' && request.method === 'GET') {
      const offset = await env.KV.get('tg_update_offset');
      const seen   = JSON.parse(await env.KV.get('tg_seen_posts') || '[]');
      return Response.json({
        update_offset: offset ? parseInt(offset) : null,
        scanned_posts: seen.length,
        note: 'Bot auto-scans all groups it is added to. Add bot to crypto job groups to enable auto-reply.',
      });
    }

    // POST /group-reset — clear update offset (re-scan from current point)
    if (pathname === '/group-reset' && request.method === 'POST') {
      await env.KV.delete('tg_update_offset');
      await env.KV.delete('tg_seen_posts');
      return Response.json({ ok: true, message: 'Group scan state reset — next cycle starts fresh' });
    }

    // ── LingoAI Community Poster ─────────────────────────────────────────────

    // GET /lingo-status — show poster queue state and config
    if (pathname === '/lingo-status' && request.method === 'GET') {
      return Response.json(await lingoStatus(env));
    }

    // GET /lingo-setup?chat_id=XXXX — save group chat ID (or auto-detect)
    if (pathname === '/lingo-setup' && request.method === 'GET') {
      const chatId = url.searchParams.get('chat_id');
      return Response.json(await setupLingoGroup(env, chatId));
    }

    // POST /lingo-post — manually trigger a posting run right now
    if (pathname === '/lingo-post' && request.method === 'POST') {
      const result = await runLingoPoster(env);
      return Response.json(result);
    }

    // GET /lingo-rl-scores — show RL engagement scores (top topics + agents)
    if (pathname === '/lingo-rl-scores' && request.method === 'GET') {
      return Response.json(await lingoStatus(env).then(s => ({
        reinforcement_learning: s.reinforcement_learning,
        note: 'POST /lingo-rl-reset to wipe scores and start fresh',
      })));
    }

    // POST /lingo-hot-topic — inject a live event topic override for next N runs
    // body: {topic, context, hours?}  (hours defaults to 12)
    if (pathname === '/lingo-hot-topic' && request.method === 'POST') {
      try {
        const { topic, context, hours } = await request.json();
        if (!topic) return Response.json({ error: 'topic required' }, { status: 400 });
        // Also clear current session so Director starts fresh on this topic immediately
        await env.KV.delete('lingo_conv_topic');
        await env.KV.delete('lingo_conv_agents');
        const result = await setHotTopic(env, topic, context || '', hours || 12);
        return Response.json({ ok: true, message: 'Hot topic set — next poster run will discuss this event', hot_topic: result });
      } catch (e) {
        return Response.json({ error: String(e) }, { status: 400 });
      }
    }

    // DELETE /lingo-hot-topic — clear the override early
    if (pathname === '/lingo-hot-topic' && request.method === 'DELETE') {
      await env.KV.delete('lingo_hot_topic');
      return Response.json({ ok: true, message: 'Hot topic cleared' });
    }

    // POST /lingo-rl-reset — wipe RL scores and message tracking
    if (pathname === '/lingo-rl-reset' && request.method === 'POST') {
      await Promise.all([
        env.KV.delete('lingo_rl_scores'),
        env.KV.delete('lingo_msg_track'),
      ]);
      return Response.json({ ok: true, message: 'RL scores and message tracking cleared.' });
    }

    // POST /lingo-reset — full conversation reset: clears session, history, topic, errors
    if (pathname === '/lingo-reset' && request.method === 'POST') {
      await Promise.all([
        env.KV.delete('lingo_session_num'),
        env.KV.delete('lingo_conv_topic'),
        env.KV.delete('lingo_conv_agents'),
        env.KV.delete('lingo_recent_runs'),
        env.KV.delete('lingo_posted_msgs'),
        env.KV.delete('lingo_prev_msg_ids'),
        env.KV.delete('lingo_groq_err'),
        env.KV.delete('lingo_openai_err'),
        env.KV.delete('lingo_xai_err'),
        env.KV.delete('lingo_cfai_err'),
      ]);
      return Response.json({ ok: true, message: 'Full lingo reset — session, history, errors cleared. Next run starts a fresh conversation on a new topic.' });
    }

    // GET /debug — test each AI + discovery component, return diagnostics
    if (pathname === '/debug' && request.method === 'GET') {
      const diag = { ai_binding: !!env.AI, groq_key: !!env.GROQ_API_KEY, openai_key: !!env.OPENAI_API_KEY,
        tavily_key: !!env.TAVILY_API_KEY, xai_key: !!env.XAI_API_KEY, apify_key: !!env.APIFY_API_KEY,
        tg_token: !!env.TELEGRAM_BOT_TOKEN, tg_owner: !!env.TELEGRAM_OWNER_ID,
        cf_key: !!env.CF_GLOBAL_KEY, cf_account: env.CF_ACCOUNT_ID || 'missing' };

      // Test AI binding
      if (env.AI) {
        try {
          const r = await env.AI.run('@cf/meta/llama-3.3-70b-instruct-fp8-fast', {
            messages: [{ role: 'user', content: 'Say "ok" in 1 word.' }], max_tokens: 5 });
          diag.ai_binding_test = r?.response?.trim() || 'empty';
        } catch(e) { diag.ai_binding_test = 'ERROR: ' + String(e).slice(0,100); }
      }

      // Test Groq
      if (env.GROQ_API_KEY) {
        try {
          const r = await fetch(`${env.CF_GW_BASE}/groq/openai/v1/chat/completions`, {
            method: 'POST', headers: { 'Authorization': `Bearer ${env.GROQ_API_KEY}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: 'llama-3.3-70b-versatile', max_tokens: 5, messages: [{ role: 'user', content: 'Say ok' }] }) });
          diag.groq_test = r.ok ? 'ok' : `HTTP ${r.status}`;
        } catch(e) { diag.groq_test = 'ERROR: ' + String(e).slice(0,80); }
      }

      // Test Tavily
      if (env.TAVILY_API_KEY) {
        try {
          const r = await fetch('https://api.tavily.com/search', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: env.TAVILY_API_KEY, query: 'web3 jobs', max_results: 2 }) });
          const d = r.ok ? await r.json() : null;
          diag.tavily_test = r.ok ? `ok (${d?.results?.length || 0} results)` : `HTTP ${r.status}`;
        } catch(e) { diag.tavily_test = 'ERROR: ' + String(e).slice(0,80); }
      }

      // Test web3.career RSS
      try {
        const r = await fetch('https://web3.career/web3-jobs.rss', { headers: { 'User-Agent': 'Mozilla/5.0' } });
        const xml = r.ok ? await r.text() : '';
        const items = (xml.match(/<item>/g) || []).length;
        diag.web3career_rss = r.ok ? `ok (${items} items)` : `HTTP ${r.status}`;
      } catch(e) { diag.web3career_rss = 'ERROR: ' + String(e).slice(0,80); }

      // Test Telegram
      if (env.TELEGRAM_BOT_TOKEN) {
        try {
          const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getMe`);
          const d = r.ok ? await r.json() : null;
          diag.telegram_bot = d?.ok ? `@${d.result.username}` : `HTTP ${r.status}`;
        } catch(e) { diag.telegram_bot = 'ERROR: ' + String(e).slice(0,80); }
      }

      return Response.json(diag, { headers: { 'Content-Type': 'application/json' } });
    }

    // POST /reset-cache — clear dedup + discovery caches so next /run finds fresh leads
    if (pathname === '/reset-cache' && request.method === 'POST') {
      await Promise.all([
        env.KV.delete('seen_leads'),
        env.KV.delete('apify_run_ids'),
        env.KV.delete('tg_update_offset'),
        env.KV.delete('tg_seen_posts'),
      ]);
      return Response.json({ ok: true, message: 'Cache cleared — POST /run to start fresh cycle' });
    }

    // GET /debug-apify — show stored run IDs and their Apify status
    if (pathname === '/debug-apify' && request.method === 'GET') {
      if (!env.APIFY_API_KEY) return Response.json({ error: 'APIFY_API_KEY not set' }, { status: 400 });
      const storedIds = JSON.parse(await env.KV.get('apify_run_ids') || '[]');
      if (!storedIds.length) return Response.json({ run_ids: [], message: 'No Apify run IDs stored yet — POST /run to start first cycle' });

      const statuses = await Promise.all(storedIds.map(async id => {
        try {
          const r = await fetch(`https://api.apify.com/v2/actor-runs/${id}`, {
            headers: { 'Authorization': `Bearer ${env.APIFY_API_KEY}` },
          });
          if (!r.ok) return { id, error: `HTTP ${r.status}` };
          const d = await r.json();
          return {
            id,
            status:       d.data?.status,
            startedAt:    d.data?.startedAt,
            finishedAt:   d.data?.finishedAt,
            datasetItems: d.data?.stats?.outputDatasetItems ?? '?',
          };
        } catch (e) { return { id, error: String(e).slice(0, 80) }; }
      }));

      return Response.json({ run_count: storedIds.length, runs: statuses });
    }

    // GET /find-jobs — run full discovery synchronously, return leads as JSON (for testing)
    if (pathname === '/find-jobs' && request.method === 'GET') {
      try {
        const leads = await discoverLeads(env);
        return Response.json({
          ok: true,
          count: leads.length,
          leads: leads.map(l => ({ lead_id: l.lead_id, title: l.title, project: l.project, source: l.source, job_url: l.job_url || '', preview: (l.description || '').slice(0, 200) })),
        });
      } catch (e) {
        return Response.json({ ok: false, error: String(e) }, { status: 500 });
      }
    }

    // ── Telegram Webhook (real-time bot responses) ───────────────────────────

    // POST /webhook — Telegram real-time updates
    if (pathname === '/webhook' && request.method === 'POST') {
      // CRITICAL: read body BEFORE ctx.waitUntil — body stream must be consumed
      // before the response is returned, otherwise it may be GC'd by the runtime
      let update;
      try { update = await request.json(); } catch { return Response.json({ ok: true }); }

      ctx.waitUntil(handleTelegramUpdate(env, update));
      return Response.json({ ok: true });
    }

    // GET /webhook-info — show Telegram's view of our webhook (open on phone to debug)
    if (pathname === '/webhook-info' && request.method === 'GET') {
      if (!env.TELEGRAM_BOT_TOKEN) return Response.json({ error: 'TELEGRAM_BOT_TOKEN not set' });
      const d = await tgCall(env, 'getWebhookInfo', {});
      return Response.json(d);
    }

    // GET /test-group — sends a test message to the stored group; shows Telegram's response
    // Open on phone: https://job-agent.ashiqjobagent.workers.dev/test-group
    if (pathname === '/test-group' && request.method === 'GET') {
      const chatId = await env.KV.get('lingo_group_chat_id');
      if (!chatId) return Response.json({ error: 'No group configured — use /lingosetup in the group first' });
      const botInfo = await tgCall(env, 'getMe', {});
      const sendResult = await tgCall(env, 'sendMessage', {
        chat_id: chatId,
        text: '🤖 Bot connectivity test — if you see this, the bot can post to this group.',
        parse_mode: 'HTML',
      });
      return Response.json({
        group_chat_id: chatId,
        bot_username:  botInfo?.result?.username,
        send_result:   sendResult,
        can_post:      sendResult?.ok === true,
      });
    }

    // GET /set-webhook — register this Worker as the Telegram webhook
    if (pathname === '/set-webhook' && request.method === 'GET') {
      if (!env.TELEGRAM_BOT_TOKEN) return Response.json({ error: 'TELEGRAM_BOT_TOKEN not set' }, { status: 400 });
      const webhookUrl = `${url.origin}/webhook`;
      const r = await fetch(
        `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/setWebhook`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: webhookUrl, allowed_updates: ['message', 'channel_post', 'my_chat_member', 'message_reaction'] }) }
      );
      const d = await r.json();
      return Response.json({ ok: d.ok, webhook_url: webhookUrl, telegram_response: d });
    }

    // GET /del-webhook — remove webhook (switch back to getUpdates polling)
    if (pathname === '/del-webhook' && request.method === 'GET') {
      if (!env.TELEGRAM_BOT_TOKEN) return Response.json({ error: 'TELEGRAM_BOT_TOKEN not set' }, { status: 400 });
      const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/deleteWebhook`);
      const d = await r.json();
      return Response.json({ ok: d.ok, telegram_response: d });
    }

    // GET /debug-discovery — run 2 Tavily queries and show raw + filtered results
    if (pathname === '/debug-discovery' && request.method === 'GET') {
      const ROLE_KEYWORDS = ['community','moderator','social','content','growth','marketing',
        'ambassador','kol','annotation','ai train','data label','localization','prompt','operations'];
      const matchesProfile = t => ROLE_KEYWORDS.some(k => t.toLowerCase().includes(k));

      const testQueries = [
        'web3 blockchain "community manager" hiring apply now remote 2026',
        '"ambassador program" web3 crypto blockchain apply 2026',
        'web3 crypto "moderator" OR "community lead" job apply 2026',
      ];

      const results = [];
      for (const q of testQueries) {
        try {
          const r = await fetch('https://api.tavily.com/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: env.TAVILY_API_KEY, query: q, search_depth: 'advanced', max_results: 5 }),
          });
          if (!r.ok) { results.push({ query: q, error: `HTTP ${r.status}` }); continue; }
          const d = await r.json();
          const raw = d.results || [];
          const passed = raw.filter(item => {
            const txt = (item.title || '') + ' ' + (item.content || item.description || '');
            return matchesProfile(txt);
          });
          results.push({
            query: q,
            raw_count: raw.length,
            passed_filter: passed.length,
            sample_titles: raw.slice(0,3).map(x => x.title),
            passed_titles: passed.slice(0,3).map(x => x.title),
          });
        } catch (e) { results.push({ query: q, error: String(e).slice(0,100) }); }
      }

      const seenLeads = JSON.parse(await env.KV.get('seen_leads') || '[]');
      return Response.json({ tavily_key: !!env.TAVILY_API_KEY, seen_leads_count: seenLeads.length, results });
    }

    return new Response([
      'Job Agent — endpoints:',
      '  GET  /status',
      '  GET  /queue',
      '  GET  /report',
      '  GET  /learning',
      '  GET  /tg-status',
      '  GET  /groups',
      '  GET  /tg-db             ?region=australia_nz|global  ?type=channel|group|bot',
      '  GET  /export-db         full KV data export  ?format=json for download',
      '  GET  /draft/:lead_id',
      '  GET  /lingo-status',
      '  GET  /lingo-rl-scores   RL engagement scores (top topics + agents)',
      '  GET  /lingo-setup       ?chat_id=XXXX',
      '  GET  /set-webhook       register Telegram webhook (enables real-time @mention responses)',
      '  GET  /del-webhook       remove webhook (switch back to getUpdates polling)',
      '  POST /run',
      '  POST /group-reset',
      '  POST /lingo-post',
      '  POST /lingo-hot-topic    inject live event topic override  body: {topic, context, hours?}',
      '  DELETE /lingo-hot-topic  clear hot topic early',
      '  POST /lingo-reset',
      '  POST /lingo-rl-reset    wipe RL scores and message tracking',
      '  POST /webhook           Telegram webhook receiver',
      '  POST /tg-auth         body: {"phone":"+91XXXXXXXXXX"}',
      '  POST /tg-auth-code    body: {"code":"12345"}',
      '  POST /tg-auth-2fa     body: {"password":"..."}',
      '  POST /import          body: {"text":"<job post>"}',
      '  POST /craft           body: {"title":"...","company":"...","description":"..."}',
      '  POST /outcome         ?lead_id=&outcome=replied|ignored|interview|hired|scam',
      '  POST /draft-outcome   ?lead_id=&outcome=replied|ignored|interview',
    ].join('\n'), { headers: { 'Content-Type': 'text/plain' } });
  },
};
