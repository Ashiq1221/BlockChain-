// ============================================================
// Adaption Labs Ambassador Application
// URL: https://adaptionlabs.ai/ambassadors-application
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
    summary: `AI Operations Specialist and Community Builder from Kashmir, India. Grew a Web3 Twitter/X account to 16,000+ organic followers and built a 6,000+ member community. Hands-on AI data annotation, prompt engineering, chatbot testing experience. Managed communities for EMC Protocol, Network3, LingoAI, JarvisBot_AI. Multilingual: English, Hindi, Urdu, Kashmiri.`,
    motivation: `I want to help grow the Adaption community in South Asia. Kashmir and the broader region have a rapidly growing developer base that needs dedicated local AI community leadership. I bring 2+ years of community building experience, 16K+ Twitter followers, and multilingual communication skills to make a real impact. I am committed to the full 6-month program.`,
  };

  function fillField(el) {
    const label =
      el.closest("label, .field, .form-group, [class*='field'], [class*='input']")
        ?.innerText?.toLowerCase() ||
      el.getAttribute("placeholder")?.toLowerCase() ||
      el.getAttribute("name")?.toLowerCase() || "";

    let val = "";
    if (/email/.test(label)) val = PROFILE.email;
    else if (/first.*name|^name/.test(label)) val = PROFILE.name;
    else if (/last.*name/.test(label)) val = "Ganaie";
    else if (/phone|tel/.test(label) || el.type === "tel") val = PROFILE.phone;
    else if (/twitter|x handle|@/.test(label)) val = PROFILE.twitter;
    else if (/linkedin/.test(label)) val = PROFILE.linkedin;
    else if (/location|country|city|where/.test(label)) val = PROFILE.location;
    else if (/telegram/.test(label)) val = PROFILE.telegram;
    else if (/discord/.test(label)) val = PROFILE.discord;
    else if (/motivat|why|goal|interest|tell us|message/.test(label)) val = PROFILE.motivation;
    else if (/experience|background|about|skill|bio/.test(label)) val = PROFILE.summary;
    else if (el.tagName === "TEXTAREA") val = PROFILE.motivation;
    else if (/url|website|social|link/.test(label)) val = PROFILE.linkedin;

    if (val) {
      el.focus();
      el.value = val;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));
    }
  }

  document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="checkbox"]):not([type="radio"]), textarea, select').forEach(fillField);

  // Handle dropdowns
  document.querySelectorAll("select").forEach((sel) => {
    for (let i = 0; i < sel.options.length; i++) {
      if (/india|asia|remote|yes/i.test(sel.options[i].text)) {
        sel.selectedIndex = i;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
        break;
      }
    }
  });

  // Check any agreement checkboxes
  document.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    if (!cb.checked) cb.click();
  });

  console.log("✅ Form filled! Submitting in 3 seconds — review the form now if needed...");
  setTimeout(() => {
    const btn =
      document.querySelector('button[type="submit"]') ||
      document.querySelector('input[type="submit"]') ||
      [...document.querySelectorAll("button")].find((b) => /submit|apply|send/i.test(b.innerText));
    if (btn) { btn.click(); console.log("✅ Submitted!"); }
    else console.log("⚠️ Submit button not found — click it manually.");
  }, 3000);
})();
