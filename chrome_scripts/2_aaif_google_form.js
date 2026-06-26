// ============================================================
// AAIF Ambassador — Google Form (4 pages)
// URL: https://forms.gle/UPjnopVhACiTa8my7
// Open the URL above in Chrome, then paste this in Console
// It will auto-advance through all 4 pages
// ============================================================

const PROFILE = {
  name: "Ashiq",
  email: "naveeddurfi@gmail.com",
  location: "Kashmir, India",
  twitter: "@Ganaie__suhail",
  linkedin: "https://linkedin.com/in/ashiq-ah-705334395",
  telegram: "@ashiq80",
  discord: "ashiq1581",
  summary: `AI Operations Specialist and Community Builder from Kashmir, India. I have grown a Web3 Twitter/X account to 16,000+ organic followers and built a 6,000+ member community across Telegram, Discord, and X. Hands-on experience in AI data annotation, prompt engineering, chatbot testing, and community management for AI and Web3 protocols. Multilingual: English, Hindi, Urdu, Kashmiri. B.Tech, Kashmir University.`,
  motivation: `I want to build and lead a local AI community in Kashmir and across South Asia. My region has a fast-growing developer and student population eager for AI education but underrepresented in global AI communities. As a multilingual communicator with a proven track record in community building, I am uniquely positioned to extend AAIF's message to South Asian audiences who rarely get direct access to these ecosystems.`,
};

function fillInputs() {
  document.querySelectorAll("input, textarea").forEach((el) => {
    const label =
      el.closest('[class*="question"], [class*="Question"]')
        ?.querySelector("span, label, div[role='heading']")
        ?.innerText?.toLowerCase() || "";
    const ph = (el.placeholder || "").toLowerCase();
    const ctx = label + " " + ph;
    let val = "";

    if (/email/.test(ctx)) val = PROFILE.email;
    else if (/\bname\b/.test(ctx)) val = PROFILE.name;
    else if (/twitter|x\s|handle/.test(ctx)) val = PROFILE.twitter;
    else if (/linkedin/.test(ctx)) val = PROFILE.linkedin;
    else if (/location|country|city|region/.test(ctx)) val = PROFILE.location;
    else if (/telegram/.test(ctx)) val = PROFILE.telegram;
    else if (/discord/.test(ctx)) val = PROFILE.discord;
    else if (/motivat|why|goal|plan/.test(ctx)) val = PROFILE.motivation;
    else if (/experience|background|about|skill/.test(ctx)) val = PROFILE.summary;
    else if (el.tagName === "TEXTAREA") val = PROFILE.summary;

    if (val && el.value === "") {
      el.focus();
      // React/Vue-aware fill
      const nativeInput = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value") ||
                          Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value");
      if (nativeInput) {
        nativeInput.set.call(el, val);
      } else {
        el.value = val;
      }
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
  });
}

function clickNext() {
  const btns = [...document.querySelectorAll('[role="button"], button')];
  const next = btns.find((b) => /next|continue|forward/i.test(b.innerText));
  const submit = btns.find((b) => /submit/i.test(b.innerText));
  if (submit) { submit.click(); return "submitted"; }
  if (next) { next.click(); return "next"; }
  return "none";
}

async function run() {
  for (let page = 0; page < 5; page++) {
    await new Promise((r) => setTimeout(r, 1500));
    fillInputs();
    await new Promise((r) => setTimeout(r, 800));
    const result = clickNext();
    console.log(`Page ${page + 1}: ${result}`);
    if (result === "submitted") { console.log("✅ AAIF Form submitted!"); break; }
    if (result === "none" && page > 0) { console.log("⚠️ No button found — check the page."); break; }
  }
}

run();
