// ============================================================
// Qwen Ambassador Program 2026
// URL: https://qwen.ai/ambassador
// Open the URL above in Chrome, then paste this in Console
// ============================================================

(function () {
  const PROFILE = {
    name: "Ashiq",
    email: "naveeddurfi@gmail.com",
    phone: "+919541246728",
    location: "Kashmir, India",
    twitter: "@Ganaie__suhail",
    linkedin: "https://linkedin.com/in/ashiq-ah-705334395",
    telegram: "@ashiq80",
    discord: "ashiq1581",
    github: "https://github.com/ashiq1221",
    motivation: `I want to build and lead a local Qwen AI community in Kashmir and across South Asia. My region has a fast-growing developer population that is eager for open-source AI education but largely absent from global AI communities. I speak English, Hindi, Urdu, and Kashmiri — giving me unique reach across 500M+ people. I have grown a Web3 Twitter/X account to 16,000+ organic followers and built a 6,000+ member community, and I will bring the same energy to growing the Qwen ecosystem in South Asia.`,
    experience: `AI Operations Specialist and Community Builder with 2+ years of experience. Built 16,000+ follower X account (100% organic), managed 6,000+ member Telegram/Discord community for EMC Protocol. Freelance AI data annotator, prompt engineer, and chatbot evaluator. Community and content manager for Network3, LingoAI, JarvisBot_AI, RIDO. B.Tech, Kashmir University.`,
  };

  function fill(el, value) {
    el.focus();
    const nativeSetter =
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set ||
      Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
    if (nativeSetter) nativeSetter.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="checkbox"]), textarea').forEach((el) => {
    const ctx = (
      el.placeholder + " " +
      el.name + " " +
      (el.getAttribute("aria-label") || "") + " " +
      (el.closest("label, .field, [class*='form']")?.innerText || "")
    ).toLowerCase();

    if (/email/.test(ctx)) fill(el, PROFILE.email);
    else if (/first.*name/.test(ctx)) fill(el, "Ashiq");
    else if (/last.*name/.test(ctx)) fill(el, "Ganaie");
    else if (/\bname\b/.test(ctx)) fill(el, PROFILE.name);
    else if (/phone|tel/.test(ctx) || el.type === "tel") fill(el, PROFILE.phone);
    else if (/twitter|x\b|handle/.test(ctx)) fill(el, PROFILE.twitter);
    else if (/linkedin/.test(ctx)) fill(el, PROFILE.linkedin);
    else if (/location|country|city|region/.test(ctx)) fill(el, PROFILE.location);
    else if (/telegram/.test(ctx)) fill(el, PROFILE.telegram);
    else if (/discord/.test(ctx)) fill(el, PROFILE.discord);
    else if (/github/.test(ctx)) fill(el, PROFILE.github);
    else if (/motivat|why|goal|plan|interest/.test(ctx)) fill(el, PROFILE.motivation);
    else if (/experience|background|about|skill|bio/.test(ctx)) fill(el, PROFILE.experience);
    else if (el.tagName === "TEXTAREA") fill(el, PROFILE.motivation);
  });

  // Dropdowns
  document.querySelectorAll("select").forEach((sel) => {
    for (let i = 0; i < sel.options.length; i++) {
      if (/india|asia|south asia|remote|yes|community/i.test(sel.options[i].text)) {
        sel.selectedIndex = i;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
        break;
      }
    }
  });

  document.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    if (!cb.checked) cb.click();
  });

  console.log("✅ Form filled! Review the content, then click Submit.");
})();
