// ============================================================
// Fetch.ai Ambassador Innovator Club
// URL: https://innovationlab.fetch.ai/ambassador-innovator-club
// Open the URL above in Chrome, scroll to the contact form,
// then paste this in Console
// ============================================================

(function () {
  const MESSAGE = `Hi Fetch.ai Team,

I am applying to join the Fetch.ai Ambassador Innovator Club. I am an AI Operations Specialist and Community Builder from Kashmir, India with real experience growing AI and Web3 communities.

Key highlights:
- 16,000+ organic Twitter/X followers (Web3 account, ICPCollectible)
- 6,000+ member community across Telegram, Discord, and X (built for EMC Protocol)
- Community & content manager for EMC Protocol, Network3, LingoAI, JarvisBot_AI
- AI Data Annotator with hands-on prompt engineering and chatbot evaluation experience
- Multilingual: English, Hindi, Urdu, Kashmiri

I have followed Fetch.ai's autonomous agent work closely and believe it represents the most important near-term application of AI. I would actively grow the Fetch.ai community across South Asia and create educational content in multiple languages.

Ashiq | naveeddurfi@gmail.com | @Ganaie__suhail | Kashmir, India`;

  function fill(el, value) {
    el.focus();
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  const inputs = document.querySelectorAll('input[type="text"], input[type="email"], input[name]');
  inputs.forEach((inp) => {
    const ctx = (inp.placeholder + " " + inp.name + " " + (inp.getAttribute("aria-label") || "")).toLowerCase();
    if (/name/.test(ctx)) fill(inp, "Ashiq");
    else if (/email/.test(ctx)) fill(inp, "naveeddurfi@gmail.com");
    else if (/linkedin/.test(ctx)) fill(inp, "https://linkedin.com/in/ashiq-ah-705334395");
  });

  const textarea = document.querySelector("textarea");
  if (textarea) fill(textarea, MESSAGE);

  // Check privacy/agreement checkboxes
  document.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    if (!cb.checked) cb.click();
  });

  console.log("✅ Form filled! Review it, then click the submit button.");
  console.log("   (Auto-submit skipped for this form — verify content first)");
})();
