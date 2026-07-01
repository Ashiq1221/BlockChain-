/**
 * SMM Sentinel v2 — Cloudflare Intelligence Platform
 *
 * Full stack:
 *  • Cron Triggers      — autonomous cycle every 15 min (no GitHub Actions needed)
 *  • Browser Rendering  — auto-detect new X.com posts + verify actual delivery
 *  • Workers AI         — Llama 3.3 70B (fast scout) + DeepSeek R1 llama-70b (deep reason)
 *  • AI Gateway         — semantic caching, analytics, multi-provider fallback
 *  • CF Queues          — fault-tolerant order placement with auto-retry + DLQ
 *  • D1 SQL             — persistent order state, analytics, cycle history
 *  • KV                 — sub-ms response caching
 *  • R2                 — immutable audit log (daily snapshots)
 *  • Vectorize          — episodic memory — agent learns from past cycles
 *  • HTTP endpoints     — /trigger  /status  /queue?link=…
 */

import puppeteer from "@cloudflare/puppeteer";

// ── Models ────────────────────────────────────────────────────────────────────
const FAST_MODEL   = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";
const REASON_MODEL = "@cf/deepseek-ai/deepseek-r1-distill-llama-70b";
const EMBED_MODEL  = "@cf/baai/bge-large-en-v1.5";

// ── SMM Panels (priority order) ───────────────────────────────────────────────
const PANELS = [
  {
    name: "smmfollows", urlVar: "SMM_URL", keyVar: "SMM_API_KEY",
    defaultUrl: "https://smmfollows.com/api/v2",
    svc:  { likes: 16465, retweets: 9018, comments: 7338, views: 17682 },
    min:  { likes: 10,    retweets: 100,  comments: 5,    views: 100   },
    rate: { likes: 2.10,  retweets: 2.10 },
  },
  {
    name: "smmwiz", urlVar: null, keyVar: "SMMWIZ_API_KEY",
    defaultUrl: "https://smmwiz.com/api/v2",
    svc:  { likes: 17712, retweets: 18535 },
    min:  { likes: 20,    retweets: 100   },
    rate: { likes: 0.94,  retweets: 2.16  },
  },
  {
    name: "astrasmm", urlVar: null, keyVar: "ASTRA_API_KEY",
    defaultUrl: "https://astrasmm.com/api/v2",
    svc:  { likes: 18718, retweets: 12109 },
    min:  { likes: 10,    retweets: 100   },
    rate: { likes: 2.40,  retweets: 1.33  },
  },
];

// ── New-post engagement package (sent every 8 h per new post) ────────────────
const ENGAGEMENT_INTERVAL_MS = 8 * 60 * 60 * 1000;
const NEW_POST_PACKAGE = [
  { kind: "likes",    quantity: 100   },
  { kind: "retweets", quantity: 50    },
  { kind: "comments", quantity: 20    },
  { kind: "views",    quantity: 30000 },
];

// ── System Prompt ─────────────────────────────────────────────────────────────
const SYSTEM_PROMPT = `You are SMM Sentinel — an elite autonomous social media marketing agent.
You manage SMM orders across multiple panels (smmfollows, smmwiz, astrasmm).
You think strategically: maximize engagement, minimize cost, detect delivery failures early.
Always respond with valid JSON only. No markdown fences. No explanation outside the JSON.`;

// ── Worker Entry Points ───────────────────────────────────────────────────────
export default {
  // Cron: every 15 minutes
  async scheduled(event, env, ctx) {
    ctx.waitUntil(runSentinelCycle(env));
  },

  // HTTP: manual control + status
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/trigger") {
      ctx.waitUntil(runSentinelCycle(env));
      return Response.json({ ok: true, triggered: new Date().toISOString() });
    }

    if (url.pathname === "/status") {
      return Response.json(await getStatus(env));
    }

    if (url.pathname === "/queue") {
      const link = url.searchParams.get("link");
      if (!link) return Response.json({ error: "Missing ?link=" }, { status: 400 });
      await env.ORDER_QUEUE.send({ type: "queue_post", link });
      return Response.json({ ok: true, queued: link });
    }

    return new Response(
      "SMM Sentinel v2 | /trigger  /status  /queue?link=URL",
      { status: 200 }
    );
  },

  // Queue consumer: process orders with auto-retry
  async queue(batch, env) {
    for (const msg of batch.messages) {
      try {
        await processQueueMsg(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error("[Queue] Failed, will retry:", err.message);
        msg.retry();
      }
    }
  },
};

// ── 8-hour engagement gate ────────────────────────────────────────────────────
async function engagementDue(env) {
  if (!env.KV) return true;
  const last = await env.KV.get("engagement:last-run");
  return !last || Date.now() - parseInt(last) >= ENGAGEMENT_INTERVAL_MS;
}

async function markEngagementRun(env) {
  if (env.KV) await env.KV.put("engagement:last-run", String(Date.now()), { expirationTtl: 86400 });
}

// ── Main Sentinel Cycle ───────────────────────────────────────────────────────
async function runSentinelCycle(env) {
  const cycleId = `cycle-${Date.now()}`;
  console.log(`[Sentinel] ${cycleId} start`);

  await initDb(env);

  // Phase 1 — Always: balance + order state
  const [state, balance] = await Promise.all([loadState(env), getSmmBalance(env)]);

  // Phase 2 — Always: order status sync + delivery verification
  const orderUpdates = await syncOrderStatus(state, env);
  const deliveryIssues = await verifyDelivery(env, orderUpdates);

  // Phase 3 — Every 8 h: discover new posts and send engagement package
  let newPosts = [];
  const runEngagement = await engagementDue(env);
  if (runEngagement) {
    newPosts = await discoverNewPosts(env);
    if (newPosts.length) {
      console.log(`[Sentinel] Engagement window — ${newPosts.length} new post(s) found`);
    }
  } else {
    console.log("[Sentinel] Engagement window not due yet — skipping post discovery");
  }

  // Phase 4 — Episodic memory recall
  const memories = await recallMemories(env, { newPosts, orderUpdates, deliveryIssues });

  // Phase 5 — AI Decision
  state.newPosts = newPosts; // make post text available to executeDecision
  const context = {
    balance,
    newPosts,
    orderUpdates,
    deliveryIssues,
    memories,
    pendingPosts: state.pendingPosts,
    engagementPackage: NEW_POST_PACKAGE,
  };
  const decision = await aiDecide(env, context);

  // Phase 6 — Execute
  const results = await executeDecision(env, state, decision);

  // Mark engagement run after successful execution
  if (runEngagement && newPosts.length) await markEngagementRun(env);

  // Phase 7 — Persist + backup
  const summary = `[${cycleId}] ${decision.summary || "cycle complete"} | placed:${results.ordersPlaced} refills:${results.refills} issues:${deliveryIssues.length}`;
  await Promise.all([
    logCycle(env, summary, balance),
    storeMemory(env, { cycle: cycleId, decision: decision.summary, balance, results }),
    backupToR2(env, state, cycleId),
  ]);

  console.log(`[Sentinel] ${summary}`);
}

// ── X.com Post Discovery (Browser Rendering) ──────────────────────────────────
async function discoverNewPosts(env) {
  const handle = env.X_ACCOUNT_HANDLE;
  if (!handle || !env.BROWSER) return [];

  let browser;
  try {
    browser = await puppeteer.launch(env.BROWSER);
    const page = await browser.newPage();
    await page.setUserAgent(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    );
    await page.goto(`https://x.com/${handle}`, {
      waitUntil: "domcontentloaded",
      timeout: 20000,
    });
    await page.waitForSelector('[data-testid="tweet"]', { timeout: 12000 }).catch(() => {});

    const posts = await page.evaluate(() => {
      function parseStat(s = "0") {
        const n = (s || "").trim();
        if (n.endsWith("K")) return Math.round(parseFloat(n) * 1000);
        if (n.endsWith("M")) return Math.round(parseFloat(n) * 1_000_000);
        return parseInt(n.replace(/,/g, ""), 10) || 0;
      }
      return Array.from(document.querySelectorAll('[data-testid="tweet"]'))
        .slice(0, 8)
        .map((t) => {
          const anchor = t.querySelector('a[href*="/status/"]');
          if (!anchor) return null;
          const href = anchor.getAttribute("href");
          const link = href.startsWith("http") ? href : `https://x.com${href}`;
          return {
            link,
            text: (t.querySelector('[data-testid="tweetText"]')?.textContent || "").slice(0, 200),
            likes:    parseStat(t.querySelector('[data-testid="like"] span')?.textContent),
            retweets: parseStat(t.querySelector('[data-testid="retweet"] span')?.textContent),
            views:    parseStat(t.querySelector('[aria-label*="view"]')?.textContent),
          };
        })
        .filter(Boolean);
    });

    // Pull known links from D1 to filter
    const known = await env.DB.prepare("SELECT link FROM orders GROUP BY link").all();
    const knownSet = new Set((known.results || []).map((r) => r.link));
    const newPosts = posts.filter((p) => !knownSet.has(p.link));

    console.log(`[Browser] ${handle}: ${posts.length} posts scraped, ${newPosts.length} new`);
    return newPosts;
  } catch (err) {
    console.warn("[Browser] Discovery failed:", err.message);
    return [];
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

// ── Delivery Verification ─────────────────────────────────────────────────────
async function verifyDelivery(env, orders) {
  if (!env.BROWSER) return [];
  const issues = [];

  // Only verify recently-completed orders (last 48h)
  const cutoff = Date.now() - 48 * 60 * 60 * 1000;
  const toVerify = orders.filter(
    (o) =>
      (o.status === "Completed" || o.status === "Partial") &&
      o.kind !== "views" &&
      new Date(o.updated_at || o.added_at).getTime() > cutoff
  );

  if (!toVerify.length) return [];

  let browser;
  try {
    browser = await puppeteer.launch(env.BROWSER);

    for (const order of toVerify.slice(0, 3)) { // cap at 3 verifications per cycle
      try {
        const page = await browser.newPage();
        await page.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36");
        await page.goto(order.link, { waitUntil: "domcontentloaded", timeout: 15000 });
        await page.waitForSelector('[data-testid="tweet"]', { timeout: 10000 }).catch(() => {});

        const stats = await page.evaluate(() => {
          function parseStat(s = "0") {
            const n = (s || "").trim();
            if (n.endsWith("K")) return Math.round(parseFloat(n) * 1000);
            if (n.endsWith("M")) return Math.round(parseFloat(n) * 1_000_000);
            return parseInt(n.replace(/,/g, ""), 10) || 0;
          }
          const t = document.querySelector('[data-testid="tweet"]');
          if (!t) return null;
          return {
            likes:    parseStat(t.querySelector('[data-testid="like"] span')?.textContent),
            retweets: parseStat(t.querySelector('[data-testid="retweet"] span')?.textContent),
          };
        });

        await page.close();

        if (!stats) continue;

        const startCount = parseInt(order.start_count || "0", 10);
        const actualDelivered = (stats[order.kind] || 0) - startCount;
        const expectedDelivered = order.quantity - parseInt(order.remains || "0", 10);

        if (actualDelivered < expectedDelivered * 0.5) {
          issues.push({
            orderId: order.id,
            link: order.link,
            kind: order.kind,
            expected: expectedDelivered,
            actual: actualDelivered,
            deficit: expectedDelivered - actualDelivered,
          });
          console.warn(`[Verify] #${order.id} deficit: expected ${expectedDelivered}, got ${actualDelivered}`);
        }
      } catch (err) {
        console.warn(`[Verify] #${order.id} failed:`, err.message);
      }
    }
  } catch (err) {
    console.warn("[Browser] Verification init failed:", err.message);
  } finally {
    if (browser) await browser.close().catch(() => {});
  }

  return issues;
}

// ── AI Decision Engine ────────────────────────────────────────────────────────
async function aiDecide(env, context) {
  const userPrompt = `
BALANCE: $${(context.balance || 0).toFixed(2)}
NEW POSTS DETECTED (engagement window open: ${(context.newPosts || []).length > 0}): ${JSON.stringify(context.newPosts || [], null, 2)}
ENGAGEMENT PACKAGE FOR EACH NEW POST: ${JSON.stringify(context.engagementPackage)}
PENDING QUEUE: ${JSON.stringify(context.pendingPosts || [])}
ORDER ISSUES: ${JSON.stringify(
    (context.orderUpdates || []).filter((o) => o.status === "Partial" || o.status === "Canceled"),
    null, 2
  )}
DELIVERY ISSUES: ${JSON.stringify(context.deliveryIssues || [], null, 2)}
PAST MEMORY: ${context.memories || "none"}

RULES:
- For every new post detected, place ALL items in ENGAGEMENT PACKAGE (likes=100, retweets=50, comments=20, views=30000).
- Engagement runs every 8 hours — only new posts appear here; do not skip any.
- For order issues / delivery deficits, reorder the missing quantity.

Respond ONLY with JSON:
{
  "summary": "one sentence of what you decided",
  "place_orders": [{"link":"…","kind":"likes|retweets|comments|views","quantity":N}],
  "trigger_refills": ["order_id"],
  "reorder_deficits": [{"link":"…","kind":"…","quantity":N}],
  "strategy_note": "any market observation"
}`;

  const gateway = { id: env.CF_GATEWAY_ID || "smm-sentinel", skipCache: false, cacheTtl: 300 };

  // Scout pass: Llama 3.3 70B — fast, cheap, cached via AI Gateway
  let scoutHint = "";
  try {
    const scout = await env.AI.run(FAST_MODEL, {
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: `Quick scan — top 2 actions needed? JSON only.\n${userPrompt}` },
      ],
      max_tokens: 400,
    }, { gateway });
    scoutHint = scout.response || "";
    console.log("[AI Scout]", scoutHint.slice(0, 100));
  } catch (err) {
    console.warn("[AI Scout] Failed:", err.message);
  }

  // Deep pass: DeepSeek R1 llama-70b — full reasoning, cached via AI Gateway
  try {
    const deep = await env.AI.run(REASON_MODEL, {
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        {
          role: "user",
          content: `${userPrompt}\n\nFast scout hint: ${scoutHint}\n\nFull decision JSON:`,
        },
      ],
      max_tokens: 1024,
    }, { gateway });

    let text = (deep.response || "")
      .replace(/<think>[\s\S]*?<\/think>/g, "") // strip DeepSeek think blocks
      .trim();

    const match = text.match(/\{[\s\S]*\}/);
    if (match) {
      const parsed = JSON.parse(match[0]);
      console.log("[AI Deep] Decision:", parsed.summary);
      return parsed;
    }
  } catch (err) {
    console.warn("[AI Deep] Failed:", err.message);
  }

  // Rule-based fallback
  console.log("[AI] Falling back to rule-based");
  return buildRuleBasedDecision(context);
}

function buildRuleBasedDecision(ctx) {
  const orders = [];
  const refills = [];

  for (const p of [...(ctx.newPosts || []), ...(ctx.pendingPosts || []).map((l) => ({ link: l }))]) {
    if (!p.link) continue;
    for (const item of (ctx.engagementPackage || NEW_POST_PACKAGE)) {
      orders.push({ link: p.link, kind: item.kind, quantity: item.quantity });
    }
  }

  for (const o of ctx.orderUpdates || []) {
    if (o.status === "Completed" && o.refillable && !o.activeRefill) {
      refills.push(o.id);
    }
  }

  return {
    summary: `[Rule-based] ${orders.length} orders, ${refills.length} refills`,
    place_orders: orders,
    trigger_refills: refills,
    reorder_deficits: (ctx.deliveryIssues || [])
      .filter((i) => i.deficit > 20)
      .map((i) => ({ link: i.link, kind: i.kind, quantity: i.deficit })),
  };
}

// ── Execute Decision ──────────────────────────────────────────────────────────
async function executeDecision(env, state, decision) {
  let ordersPlaced = 0, refills = 0;

  // Build link → post text lookup for comment generation
  const postTextMap = Object.fromEntries(
    (state.newPosts || []).map(p => [p.link, p.text || ""])
  );

  // Queue orders (auto-retry via CF Queues)
  for (const order of decision.place_orders || []) {
    try {
      await env.ORDER_QUEUE.send({
        type: "place_order",
        ...order,
        postText: postTextMap[order.link] || "",
        requestedAt: new Date().toISOString(),
      });
      ordersPlaced++;
    } catch (err) {
      console.error("[Execute] Queue send failed:", err.message);
    }
  }

  // Queue reorder deficits too
  for (const order of decision.reorder_deficits || []) {
    try {
      await env.ORDER_QUEUE.send({
        type: "place_order",
        ...order,
        requestedAt: new Date().toISOString(),
        isReorder: true,
      });
      ordersPlaced++;
    } catch (err) {
      console.error("[Execute] Reorder queue failed:", err.message);
    }
  }

  // Trigger refills directly
  for (const orderId of decision.trigger_refills || []) {
    try {
      const res = await smmApiCall(env, PANELS[0], { action: "refill", order: orderId });
      if (res.refill) {
        await env.DB.prepare(
          "INSERT OR REPLACE INTO refills (order_id, refill_id, status, requested_at) VALUES (?,?,?,?)"
        ).bind(orderId, String(res.refill), "Pending", new Date().toISOString()).run();
        refills++;
      }
    } catch (err) {
      console.warn(`[Refill] #${orderId} failed:`, err.message);
    }
  }

  return { ordersPlaced, refills };
}

// ── AI Comment Generator ──────────────────────────────────────────────────────
async function generateComments(env, postText, count = 20) {
  const prompt = `Generate ${count} unique, authentic Twitter comments for this post.
Rules:
- Each comment must be relevant to the post topic
- Vary the style: some enthusiastic, some thoughtful, some short, some with emojis
- Sound like real users — no bots, no generic praise
- No hashtags, no @mentions
- Return ONLY a JSON array of strings, nothing else

Post: "${(postText || "").slice(0, 300)}"`;

  try {
    const res = await env.AI.run(FAST_MODEL, {
      messages: [{ role: "user", content: prompt }],
      max_tokens: 1200,
    });
    const text = (res.response || "").replace(/<think>[\s\S]*?<\/think>/g, "").trim();
    const match = text.match(/\[[\s\S]*\]/);
    if (match) {
      const arr = JSON.parse(match[0]);
      if (Array.isArray(arr) && arr.length) {
        console.log(`[Comments] Generated ${arr.length} custom comments for post`);
        return arr.slice(0, count).join("\n");
      }
    }
  } catch (err) {
    console.warn("[Comments] AI generation failed, using fallback:", err.message);
  }

  // Fallback: generic but still varied comments
  const fallback = [
    "This is amazing! 🔥", "Love this content!", "Great post!", "So true 💯",
    "This resonates with me", "Absolutely spot on", "Keep it up! 👏",
    "Brilliant take", "Couldn't agree more", "This needs more attention",
    "Well said!", "Pure gold 🙌", "This is the content I needed today",
    "Facts 💪", "Sharing this immediately", "You always deliver 🎯",
    "This is exactly right", "Underrated post", "More people need to see this",
    "Excellent point!",
  ];
  return fallback.slice(0, count).join("\n");
}

// ── Queue Consumer ────────────────────────────────────────────────────────────
async function processQueueMsg(msg, env) {
  if (msg.type === "queue_post") {
    await env.DB.prepare(
      "INSERT OR IGNORE INTO pending_posts (link, added_at) VALUES (?,?)"
    ).bind(msg.link, new Date().toISOString()).run();
    return;
  }

  if (msg.type === "place_order") {
    // For comment orders: generate AI comments from post text first
    let extraPayload = {};
    if (msg.kind === "comments") {
      const commentText = await generateComments(env, msg.postText || "", msg.quantity || 20);
      extraPayload.comments = commentText;
    }

    const result = await aiOrderAgent(env, msg.link, msg.kind, msg.quantity || 100, extraPayload);
    if (!result.success) throw new Error(`All panels failed: ${result.error}`);

    await env.DB.prepare(
      `INSERT OR REPLACE INTO orders
         (id, kind, link, quantity, panel, status, added_at, updated_at)
       VALUES (?,?,?,?,?,'Pending',?,?)`
    )
      .bind(result.orderId, msg.kind, msg.link, result.quantity, result.panel,
            msg.requestedAt || new Date().toISOString(), new Date().toISOString())
      .run();

    await env.DB.prepare("DELETE FROM pending_posts WHERE link = ?").bind(msg.link).run();
    console.log(`[Queue] Placed #${result.orderId} ${msg.kind}×${result.quantity} via ${result.panel}`);
  }
}

// ── Live Rate Fetch (KV-cached 5 min) ────────────────────────────────────────
async function fetchLiveRate(env, panel, kind) {
  const cacheKey = `live-rate:${panel.name}:${kind}`;

  if (env.KV) {
    const hit = await env.KV.get(cacheKey);
    if (hit !== null) return parseFloat(hit);
  }

  const key = env[panel.keyVar];
  if (!key) return panel.rate[kind] ?? 999;

  try {
    const services = await smmPost(panel.defaultUrl, key, { action: "services" });
    const svcId = String(panel.svc[kind]);
    const svc = Array.isArray(services) && services.find(s => String(s.service) === svcId);
    const rate = svc ? parseFloat(svc.rate) : (panel.rate[kind] ?? 999);

    if (env.KV) await env.KV.put(cacheKey, String(rate), { expirationTtl: 300 });
    return rate;
  } catch (err) {
    console.warn(`[Rates] ${panel.name} live fetch failed, using fallback:`, err.message);
    return panel.rate[kind] ?? 999;
  }
}

// ── Full Service Catalog Fetch (KV-cached 5 min) ──────────────────────────────
async function fetchAllPanelServices(env, panel) {
  const cacheKey = `svc-catalog:${panel.name}`;
  if (env.KV) {
    const hit = await env.KV.get(cacheKey);
    if (hit) return JSON.parse(hit);
  }
  const key = env[panel.keyVar];
  if (!key) return [];
  try {
    const services = await smmPost(panel.defaultUrl, key, { action: "services" });
    if (Array.isArray(services)) {
      if (env.KV) await env.KV.put(cacheKey, JSON.stringify(services), { expirationTtl: 300 });
      return services;
    }
  } catch (err) {
    console.warn(`[Agent] ${panel.name} catalog fetch failed:`, err.message);
  }
  return [];
}

// ── AI Order Agent ────────────────────────────────────────────────────────────
async function aiOrderAgent(env, link, kind, quantity, extraPayload = {}) {
  const PLATFORM_KW = ["twitter", "x.com", "tweet", "x "];
  const KIND_KW = {
    likes:    ["like", "heart"],
    retweets: ["retweet", " rt"],
    comments: ["comment", "reply"],
    views:    ["view", "impression"],
  };
  const kindKws = KIND_KW[kind] || [kind];

  function matchesSvc(svc) {
    const name = ((svc.name || "") + " " + (svc.category || "")).toLowerCase();
    return kindKws.some(kw => name.includes(kw)) && PLATFORM_KW.some(kw => name.includes(kw));
  }

  // Fetch all panel catalogs in parallel
  const activePanels = PANELS.filter(p => env[p.keyVar]);
  const catalogs = await Promise.all(
    activePanels.map(p => fetchAllPanelServices(env, p).then(svcs => ({ panel: p, svcs })))
  );

  const viable = [];
  const alternatives = [];
  for (const { panel, svcs } of catalogs) {
    for (const svc of svcs) {
      if (!matchesSvc(svc)) continue;
      const svcMin  = parseInt(svc.min  || "0", 10);
      const svcMax  = parseInt(svc.max  || "0", 10);
      const svcRate = parseFloat(svc.rate || "999");
      const svcId   = String(svc.service || "");
      if (!svcId || svcMax <= 0) continue;
      const entry = { panel, svcId, name: (svc.name || "").slice(0, 80), min: svcMin, max: svcMax, rate: svcRate };
      if (svcMin <= quantity && quantity <= svcMax) viable.push(entry);
      else alternatives.push(entry);
    }
  }

  if (!viable.length) {
    if (alternatives.length) {
      const opts = alternatives.sort((a, b) => a.min - b.min || a.rate - b.rate).slice(0, 5);
      const desc = opts.map(o => `${o.panel.name} svc#${o.svcId} min=${o.min} max=${o.max} $${o.rate}/k`).join(" | ");
      return { success: false, error: `No service can fulfill exactly ${quantity}× ${kind}. Options: ${desc}` };
    }
    return { success: false, error: `No ${kind} services found for quantity ${quantity}` };
  }

  viable.sort((a, b) => a.rate - b.rate);
  const topOptions = viable.slice(0, 12);

  console.log(`[Agent] ${viable.length} viable services for ${quantity}× ${kind}; cheapest: ${topOptions[0].panel.name} svc#${topOptions[0].svcId} @ $${topOptions[0].rate}/k`);

  // Ask AI to pick the best option
  let chosen = null;
  if (env.AI) {
    const optsStr = topOptions.map((o, i) =>
      `${i+1}. Panel=${o.panel.name} ServiceID=${o.svcId} Name="${o.name}" Min=${o.min} Max=${o.max} Rate=$${o.rate}/k`
    ).join("\n");
    const prompt = `User needs exactly ${quantity}× ${kind} for a Twitter/X post.\nThese services can all fulfill the exact quantity:\n${optsStr}\n\nChoose the best option (cheapest reputable service). Return ONLY valid JSON:\n{"panel":"name","service_id":"12345","rate":0.94,"reason":"one line"}`;
    try {
      const res = await env.AI.run(FAST_MODEL, {
        messages: [{ role: "user", content: prompt }],
        max_tokens: 200,
      });
      const text = (res.response || "").replace(/<think>[\s\S]*?<\/think>/g, "").trim();
      const m = text.match(/\{[^{}]*\}/s);
      if (m) {
        const dec   = JSON.parse(m[0]);
        const pName = (dec.panel || "").trim();
        const svcId = String(dec.service_id || "").trim();
        const pick  = viable.find(v => v.panel.name === pName && v.svcId === svcId);
        if (pick) {
          chosen = pick;
          console.log(`[Agent] AI chose: ${pName} svc#${svcId} @ $${pick.rate}/k — ${dec.reason || ""}`);
        }
      }
    } catch (err) {
      console.warn("[Agent] AI decision failed, using cheapest:", err.message);
    }
  }

  if (!chosen) chosen = topOptions[0];

  // Try AI choice first, then remaining viable options
  const orderedViable = [chosen, ...viable.filter(v => v !== chosen)];
  for (const option of orderedViable) {
    try {
      const res = await smmPost(option.panel.defaultUrl, env[option.panel.keyVar], {
        action: "add", service: option.svcId, link, quantity, ...extraPayload,
      });
      if (res.order) {
        console.log(`[Agent] ✓ ${option.panel.name} svc#${option.svcId} → order #${res.order} @ $${option.rate}/k`);
        return { success: true, orderId: String(res.order), panel: option.panel.name, quantity, rate: option.rate };
      }
      console.warn(`[Agent] ${option.panel.name} svc#${option.svcId} rejected:`, JSON.stringify(res));
    } catch (err) {
      console.warn(`[Agent] ${option.panel.name} error:`, err.message);
    }
  }
  return { success: false, error: `All ${viable.length} viable services rejected the order for ${quantity}× ${kind}` };
}

// ── Multi-Panel SMM (kept as utility; aiOrderAgent is used for new orders) ────
async function placeOrderMultiPanel(env, link, kind, quantity, extraPayload = {}) {
  const candidates = PANELS.filter(p => env[p.keyVar] && p.svc[kind]);

  // Fetch all live rates in parallel
  const rates = await Promise.all(candidates.map(p => fetchLiveRate(env, p, kind)));

  // Sort cheapest first
  const ranked = candidates
    .map((p, i) => ({ panel: p, rate: rates[i] }))
    .sort((a, b) => a.rate - b.rate);

  console.log(`[SMM] Live rates for ${kind}: `
    + ranked.map(r => `${r.panel.name}=$${r.rate}/k`).join(" | ")
    + ` → placing with ${ranked[0]?.panel.name}`);

  for (const { panel, rate } of ranked) {
    const key = env[panel.keyVar];
    const svcId = panel.svc[kind];
    const minQty = panel.min[kind] || 1;

    if (quantity < minQty) {
      console.warn(`[SMM] ${panel.name} skipped — ${quantity} below minimum ${minQty} for ${kind}`);
      continue;
    }

    try {
      const res = await smmPost(panel.defaultUrl, key, {
        action: "add", service: svcId, link, quantity,
        ...extraPayload,
      });

      if (res.order) {
        console.log(`[SMM] ✓ ${panel.name} @ $${rate}/k — order #${res.order}`);
        return { success: true, orderId: String(res.order), panel: panel.name, quantity, rate };
      }
      console.warn(`[SMM] ${panel.name} rejected (trying next cheapest):`, res);
    } catch (err) {
      console.warn(`[SMM] ${panel.name} error (trying next cheapest):`, err.message);
    }
  }
  return { success: false, error: `No panel can fulfill ${quantity}× ${kind} (check minimums)` };
}

async function smmApiCall(env, panel, payload) {
  return smmPost(panel.defaultUrl, env[panel.keyVar], payload);
}

async function smmPost(url, key, payload) {
  const body = new URLSearchParams({ key, ...Object.fromEntries(
    Object.entries(payload).map(([k, v]) => [k, String(v)])
  )});
  const r = await fetch(url, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  return r.json();
}

async function getSmmBalance(env) {
  try {
    const res = await smmPost(PANELS[0].defaultUrl, env.SMM_API_KEY, { action: "balance" });
    return parseFloat(res.balance || "0");
  } catch {
    return 0;
  }
}

// ── Order Status Sync ─────────────────────────────────────────────────────────
async function syncOrderStatus(state, env) {
  const active = (state.orders || []).filter(
    (o) => !["Completed", "Canceled"].includes(o.status)
  );

  if (active.length) {
    const ids = active.map((o) => o.id).join(",");
    try {
      const res = await smmPost(PANELS[0].defaultUrl, env.SMM_API_KEY, {
        action: "status", orders: ids,
      });
      const stmts = Object.entries(res).map(([id, info]) =>
        env.DB.prepare(
          "UPDATE orders SET status=?, remains=?, start_count=?, updated_at=? WHERE id=?"
        ).bind(info.status, info.remains, info.start_count, new Date().toISOString(), id)
      );
      if (stmts.length) await env.DB.batch(stmts);
    } catch (err) {
      console.warn("[Orders] Status sync failed:", err.message);
    }
  }

  const all = await env.DB.prepare("SELECT * FROM orders ORDER BY added_at DESC LIMIT 50").all();
  return all.results || [];
}

// ── Vectorize Episodic Memory ─────────────────────────────────────────────────
async function recallMemories(env, context) {
  if (!env.VECTORIZE) return "";
  try {
    const text = `orders:${context.orderUpdates?.length} new:${context.newPosts?.length} issues:${context.deliveryIssues?.length}`;
    const emb = await env.AI.run(EMBED_MODEL, { text }, { gateway: { id: env.CF_GATEWAY_ID || "smm-sentinel", skipCache: false, cacheTtl: 3600 } });
    const results = await env.VECTORIZE.query(emb.data[0], { topK: 3, returnMetadata: true });
    return (results.matches || [])
      .map((m) => m.metadata?.summary || "")
      .filter(Boolean)
      .join(" | ");
  } catch {
    return "";
  }
}

async function storeMemory(env, data) {
  if (!env.VECTORIZE) return;
  try {
    const text = `${data.decision || ""} balance:${data.balance} placed:${data.results?.ordersPlaced}`;
    const emb = await env.AI.run(EMBED_MODEL, { text }, { gateway: { id: env.CF_GATEWAY_ID || "smm-sentinel", skipCache: false, cacheTtl: 3600 } });
    await env.VECTORIZE.upsert([{
      id: data.cycle,
      values: emb.data[0],
      metadata: {
        summary: (data.decision || "").slice(0, 300),
        balance: data.balance,
        at: new Date().toISOString(),
      },
    }]);
  } catch (err) {
    console.warn("[Vectorize] Store failed:", err.message);
  }
}

// ── D1 State ──────────────────────────────────────────────────────────────────
async function initDb(env) {
  await env.DB.batch([
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS orders (
      id TEXT PRIMARY KEY, kind TEXT, link TEXT, quantity INTEGER,
      panel TEXT, status TEXT, start_count TEXT, remains TEXT,
      added_at TEXT, updated_at TEXT
    )`),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS pending_posts (
      link TEXT PRIMARY KEY, added_at TEXT
    )`),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS refills (
      order_id TEXT PRIMARY KEY, refill_id TEXT, status TEXT, requested_at TEXT
    )`),
    env.DB.prepare(`CREATE TABLE IF NOT EXISTS agent_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, msg TEXT, balance REAL
    )`),
  ]);
}

async function loadState(env) {
  const [orders, pending] = await Promise.all([
    env.DB.prepare("SELECT * FROM orders ORDER BY added_at DESC LIMIT 100").all(),
    env.DB.prepare("SELECT link FROM pending_posts").all(),
  ]);
  return {
    orders: orders.results || [],
    pendingPosts: (pending.results || []).map((r) => r.link),
  };
}

async function logCycle(env, msg, balance) {
  await env.DB.prepare("INSERT INTO agent_log (at, msg, balance) VALUES (?,?,?)")
    .bind(new Date().toISOString(), msg.slice(0, 500), balance || null)
    .run();
}

// ── R2 Audit Log ─────────────────────────────────────────────────────────────
async function backupToR2(env, state, cycleId) {
  if (!env.R2) return;
  try {
    const key = `logs/${new Date().toISOString().slice(0, 10)}/${cycleId}.json`;
    await env.R2.put(key, JSON.stringify({ cycle: cycleId, state, at: new Date().toISOString() }), {
      httpMetadata: { contentType: "application/json" },
    });
  } catch (err) {
    console.warn("[R2] Backup failed:", err.message);
  }
}

// ── Status Endpoint ───────────────────────────────────────────────────────────
async function getStatus(env) {
  try {
    await initDb(env);
    const [summary, recent, pending, balance, refills] = await Promise.all([
      env.DB.prepare("SELECT status, COUNT(*) as n FROM orders GROUP BY status").all(),
      env.DB.prepare("SELECT at, msg, balance FROM agent_log ORDER BY id DESC LIMIT 5").all(),
      env.DB.prepare("SELECT COUNT(*) as n FROM pending_posts").first(),
      getSmmBalance(env),
      env.DB.prepare("SELECT * FROM refills ORDER BY requested_at DESC LIMIT 5").all(),
    ]);
    return {
      balance: `$${balance.toFixed(2)}`,
      orders_by_status: summary.results,
      pending_posts: pending?.n || 0,
      recent_refills: refills.results,
      last_5_cycles: recent.results,
      timestamp: new Date().toISOString(),
    };
  } catch (err) {
    return { error: err.message };
  }
}
