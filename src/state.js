// CF KV state management — applied_jobs + posted_groups

export async function loadApplied(env) {
  try {
    const raw = await env.KV.get('applied_jobs');
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

export async function saveApplied(env, data) {
  await env.KV.put('applied_jobs', JSON.stringify(data));
}

export async function loadPostedGroups(env) {
  try {
    const raw = await env.KV.get('posted_groups');
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch { return new Set(); }
}

export async function savePostedGroups(env, groups) {
  await env.KV.put('posted_groups', JSON.stringify([...groups]));
}

export async function loadTargetGroups(env) {
  try {
    const raw = await env.KV.get('target_groups');
    return raw ? JSON.parse(raw) : ['Alturax'];
  } catch { return ['Alturax']; }
}
