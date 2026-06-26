// ============================================================
// Microsoft Student Ambassadors
// URL: https://studentambassadors.microsoft.com/
// Click "Apply" on that page, then paste this in Console
// ============================================================

(function () {
  const PROFILE = {
    firstName: "Ashiq",
    lastName: "Ganaie",
    email: "naveeddurfi@gmail.com",
    phone: "+919541246728",
    location: "Kashmir, India",
    country: "India",
    university: "Kashmir University",
    degree: "Bachelor of Technology (B.Tech)",
    graduation: "2023",
    linkedin: "https://linkedin.com/in/ashiq-ah-705334395",
    twitter: "@Ganaie__suhail",
    bio: `AI Operations Specialist and Community Builder. Grew a 16,000+ follower Web3 Twitter/X account and a 6,000+ member Telegram/Discord community from scratch. Freelance AI data annotator, prompt engineer, and chatbot evaluator. Community manager for 6+ AI and Web3 protocols. Passionate about making AI accessible to students in South Asia. Multilingual: English, Hindi, Urdu, Kashmiri.`,
    whyAmbassador: `I want to bring Microsoft's AI and developer tools to the student community in Kashmir and across North India. There are thousands of engineering students here who lack local mentors and community leaders in tech. As a Microsoft Student Ambassador, I would run workshops, organize hackathons, and build a student developer community that helps young people here learn Azure, GitHub, and AI tools. I have the community-building track record to make this real.`,
  };

  function fill(el, value) {
    el.focus();
    const nativeSetter = Object.getOwnPropertyDescriptor(
      el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype,
      "value"
    )?.set;
    if (nativeSetter) nativeSetter.call(el, value);
    else el.value = value;
    ["input", "change", "blur"].forEach((ev) =>
      el.dispatchEvent(new Event(ev, { bubbles: true }))
    );
  }

  document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="checkbox"]):not([type="radio"]), textarea').forEach((el) => {
    const ctx = (
      (el.placeholder || "") + " " +
      (el.name || "") + " " +
      (el.getAttribute("aria-label") || "") + " " +
      (el.id || "") + " " +
      (el.closest("label, .ms-TextField, [class*='field']")?.innerText || "")
    ).toLowerCase();

    if (/email/.test(ctx)) fill(el, PROFILE.email);
    else if (/first.*name/.test(ctx)) fill(el, PROFILE.firstName);
    else if (/last.*name/.test(ctx)) fill(el, PROFILE.lastName);
    else if (/\bname\b/.test(ctx) && !/last|sur/.test(ctx)) fill(el, PROFILE.firstName + " " + PROFILE.lastName);
    else if (/phone|tel|mobile/.test(ctx) || el.type === "tel") fill(el, PROFILE.phone);
    else if (/university|school|institution|college/.test(ctx)) fill(el, PROFILE.university);
    else if (/degree|major|program|study/.test(ctx)) fill(el, PROFILE.degree);
    else if (/graduat|year|class of/.test(ctx)) fill(el, PROFILE.graduation);
    else if (/linkedin/.test(ctx)) fill(el, PROFILE.linkedin);
    else if (/twitter|github|social/.test(ctx)) fill(el, PROFILE.twitter);
    else if (/location|city|address/.test(ctx)) fill(el, PROFILE.location);
    else if (/country/.test(ctx)) fill(el, PROFILE.country);
    else if (/why|motivat|goal|plan|ambassador/.test(ctx)) fill(el, PROFILE.whyAmbassador);
    else if (/bio|about|yourself|background|experience/.test(ctx)) fill(el, PROFILE.bio);
    else if (el.tagName === "TEXTAREA") fill(el, PROFILE.whyAmbassador);
  });

  // Handle country/region dropdowns
  document.querySelectorAll("select").forEach((sel) => {
    const ctx = (sel.name + " " + sel.id + " " + (sel.getAttribute("aria-label") || "")).toLowerCase();
    for (let i = 0; i < sel.options.length; i++) {
      const optText = sel.options[i].text.toLowerCase();
      if (/country|nation/.test(ctx) && /india/.test(optText)) {
        sel.selectedIndex = i;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
        break;
      }
    }
  });

  document.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    if (!cb.checked) cb.click();
  });

  console.log("✅ Form filled! Review and click Submit.");
})();
