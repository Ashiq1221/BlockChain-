// Telegram Bot & Channel Database
// Web3 / Crypto job channels and bots the agent monitors for hiring signals
// Each entry: { handle, type, focus, region, active, scan_for_jobs }

export const TG_BOTS_DB = [

  // ── Dedicated Job Channels (highest signal — only post job listings) ──────────
  {
    handle: 'cryptojobslist',
    type: 'channel',
    focus: 'web3_jobs',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: 'Largest Web3 job channel, 57k+ subs. Posts community, dev, marketing roles daily.',
    bot: '@CryptoJobsListBot',
  },
  {
    handle: 'web3hiring',
    type: 'channel',
    focus: 'web3_jobs',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: 'Daily feed of global web3 jobs. Contact @web3jobs_rep to post.',
  },
  {
    handle: 'remoteweb3jobs',
    type: 'channel',
    focus: 'web3_jobs_remote',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: 'Hand-picked remote jobs from DeFi, NFT, blockchain startups.',
  },
  {
    handle: 'stablegram',
    type: 'channel',
    focus: 'web3_jobs',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: '#1 TG channel for web3 jobs, connects talent with promising Web3 companies.',
  },
  {
    handle: 'web30job',
    type: 'channel',
    focus: 'blockchain_jobs',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: 'Blockchain and Web3 job vacancies including manager and community roles.',
  },
  {
    handle: 'CryptoJobs',
    type: 'channel',
    focus: 'crypto_jobs',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: 'Dev, marketing, community manager, and ambassador postings.',
  },
  {
    handle: 'laborx',
    type: 'channel',
    focus: 'web3_gigs',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: 'LaborX remote blockchain gigs. AI bot @laborx_ai_jobs_bot.',
    bot: '@laborx_ai_jobs_bot',
  },
  {
    handle: 'SearchForTalents',
    type: 'channel',
    focus: 'web3_talent',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: 'Web3 career channel connecting global talent with crypto/blockchain employers.',
  },
  {
    handle: 'web3engagement',
    type: 'channel',
    focus: 'community_jobs',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: 'Community manager, moderator, and engagement role postings.',
  },
  {
    handle: 'remotejobss',
    type: 'channel',
    focus: 'remote_jobs',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: 'Remote jobs including Web3 and crypto positions.',
  },

  // ── Regional Channels ─────────────────────────────────────────────────────────
  {
    handle: 'Cryptocom_AUNZ',
    type: 'group',
    focus: 'crypto_community',
    region: 'australia_nz',
    active: true,
    scan_for_jobs: true,
    note: 'Official Crypto.com AU/NZ community. Watch for ambassador/community roles.',
  },
  {
    handle: 'cryptonewsau',
    type: 'channel',
    focus: 'crypto_news',
    region: 'australia',
    active: true,
    scan_for_jobs: false,
    note: 'Australia crypto news — occasional job announcements.',
  },
  {
    handle: 'NZBitcoinersGroup',
    type: 'group',
    focus: 'bitcoin_community',
    region: 'new_zealand',
    active: true,
    scan_for_jobs: true,
    note: 'NZ Bitcoin community — local meetups and occasional hiring signals.',
  },

  // ── Bots (automated job alert bots) ──────────────────────────────────────────
  {
    handle: 'CryptoJobsListBot',
    type: 'bot',
    focus: 'web3_jobs',
    region: 'global',
    active: true,
    scan_for_jobs: false,
    note: 'AI bot for CryptoJobsList — search jobs by skill or role.',
  },
  {
    handle: 'laborx_ai_jobs_bot',
    type: 'bot',
    focus: 'web3_gigs',
    region: 'global',
    active: true,
    scan_for_jobs: false,
    note: 'LaborX AI bot — matches profiles to Web3 gigs in 30 seconds.',
  },
  {
    handle: 'jobsearchbot',
    type: 'bot',
    focus: 'general_jobs',
    region: 'global',
    active: true,
    scan_for_jobs: false,
    note: 'General job search bot, supports keyword filters including crypto.',
  },

  // ── Community Groups (mix of discussion + hiring posts) ───────────────────────
  {
    handle: 'web3community',
    type: 'group',
    focus: 'web3_community',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: 'General Web3 builders and contributors. Founders often post openings here.',
  },
  {
    handle: 'cryptodevs',
    type: 'group',
    focus: 'blockchain_dev',
    region: 'global',
    active: true,
    scan_for_jobs: true,
    note: 'Crypto dev community. Startups post community + ops roles alongside dev jobs.',
  },
  {
    handle: 'aussiecrypto',
    type: 'group',
    focus: 'crypto_community',
    region: 'australia',
    active: true,
    scan_for_jobs: true,
    note: 'Australia Web3/metaverse community — local project hiring signals.',
  },
];

// Channels the bot actively scans for job posts each cycle
export const SCAN_TARGETS = TG_BOTS_DB
  .filter(e => e.scan_for_jobs && e.type !== 'bot')
  .map(e => e.handle);

// Channels filtered by region
export function getByRegion(region) {
  return TG_BOTS_DB.filter(e => e.region === region || e.region === 'global');
}

// Summary stats
export function dbStats() {
  const total    = TG_BOTS_DB.length;
  const channels = TG_BOTS_DB.filter(e => e.type === 'channel').length;
  const groups   = TG_BOTS_DB.filter(e => e.type === 'group').length;
  const bots     = TG_BOTS_DB.filter(e => e.type === 'bot').length;
  const scannable = SCAN_TARGETS.length;
  return { total, channels, groups, bots, scannable };
}
