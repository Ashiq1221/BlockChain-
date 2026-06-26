// ============================================================
// Claude / Anthropic Ambassador — Typeform
// URL: https://form.typeform.com/to/OIUYgsnS
// Open the URL above in Chrome, then paste this in Console
// It will answer each question as it appears and advance
// ============================================================

const ANSWERS = {
  name: "Ashiq",
  email: "naveeddurfi@gmail.com",
  location: "Kashmir, India",
  twitter: "@Ganaie__suhail",
  linkedin: "https://linkedin.com/in/ashiq-ah-705334395",
  experience: `I have been using Claude extensively for AI content creation, prompt engineering, and workflow automation. I have hands-on experience as an AI data annotator and chatbot evaluator across multiple projects, and I use Claude as my primary AI tool for writing, research, and community content.`,
  community: `I built and manage a 6,000+ member community across Telegram, Discord, and X for an AI compute protocol (EMC Protocol). I also grew the ICPCollectible Web3 Twitter/X account to 16,000+ followers organically. I have served as community manager and content lead for 6+ AI and Web3 protocols.`,
  motivation: `I want to build a local Claude community in Kashmir and across South Asia. This region has a fast-growing developer and student population that is eager for AI education but largely absent from global AI communities. As someone who speaks English, Hindi, Urdu, and Kashmiri, I can genuinely reach and serve this audience. I want to run workshops, create educational content, and build a space where South Asian builders can collaborate around Claude.`,
  plan: `My plan: (1) Launch a weekly virtual meetup for South Asian Claude users and developers, (2) Create a bilingual (English/Hindi) educational content series explaining Claude's capabilities, (3) Partner with engineering colleges in the Kashmir/North India region for Claude workshops, (4) Build a Telegram community for local Claude builders with daily engagement.`,
  conflict: "No",
};

function fillVisible() {
  // Typeform shows one question at a time
  const input = document.querySelector('[data-qa="field-input"]:not([type="hidden"]), input[type="text"]:not([aria-hidden="true"]), input[type="email"]:not([aria-hidden="true"]), textarea:not([aria-hidden="true"])');
  if (!input) return false;

  const questionEl = document.querySelector('[data-qa="question-label"], [class*="questionTitle"], h1, h2');
  const question = (questionEl?.innerText || "").toLowerCase();
  const inputType = input.type || "";

  let answer = "";
  if (/email/.test(question) || inputType === "email") answer = ANSWERS.email;
  else if (/\bname\b/.test(question)) answer = ANSWERS.name;
  else if (/twitter|handle|social/.test(question)) answer = ANSWERS.twitter;
  else if (/linkedin/.test(question)) answer = ANSWERS.linkedin;
  else if (/location|country|where/.test(question)) answer = ANSWERS.location;
  else if (/conflict|other ambassador|competing/.test(question)) answer = ANSWERS.conflict;
  else if (/plan|intend|will you do|how will/.test(question)) answer = ANSWERS.plan;
  else if (/community|experience.*community|track record/.test(question)) answer = ANSWERS.community;
  else if (/motivat|why.*apply|why.*want|passion/.test(question)) answer = ANSWERS.motivation;
  else if (/claude|experience.*ai|background/.test(question)) answer = ANSWERS.experience;
  else answer = ANSWERS.motivation; // fallback

  // Fill using native setter for React compatibility
  const proto = input.tagName === "TEXTAREA"
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  const nativeSetter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
  if (nativeSetter) {
    nativeSetter.call(input, answer);
  } else {
    input.value = answer;
  }
  input.dispatchEvent(new Event("input", { bubbles: true }));
  input.dispatchEvent(new Event("change", { bubbles: true }));
  console.log(`Filled: "${question.slice(0, 60)}" → "${answer.slice(0, 50)}..."`);
  return true;
}

function pressEnterOrNext() {
  // Typeform advances with Enter key or OK button
  const okBtn = document.querySelector('[data-qa="ok-button"], button[aria-label*="OK"], button:has-text("OK")');
  if (okBtn) { okBtn.click(); return; }
  document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, bubbles: true }));
}

async function runTypeform() {
  console.log("🤖 Starting Typeform auto-fill...");
  for (let i = 0; i < 20; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const filled = fillVisible();
    if (!filled) {
      // Check for submit button
      const submitBtn = document.querySelector('[data-qa="submit-button"], button[type="submit"]');
      if (submitBtn) {
        submitBtn.click();
        console.log("✅ Form submitted!");
        break;
      }
      console.log(`Step ${i + 1}: No input found — may already be on next question or done.`);
    } else {
      await new Promise((r) => setTimeout(r, 800));
      pressEnterOrNext();
    }
  }
}

runTypeform();
