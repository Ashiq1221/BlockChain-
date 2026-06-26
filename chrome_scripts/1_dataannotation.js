// ============================================================
// DataAnnotation.tech Signup
// URL: https://app.dataannotation.tech/worker_signup
// Open the URL above in Chrome, then paste this in Console
// ============================================================

(function () {
  function fill(selector, value) {
    const el = document.querySelector(selector);
    if (!el) return false;
    el.focus();
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  // Try common field selectors
  fill('input[name="user[first_name]"]', "Ashiq") ||
  fill('input[placeholder*="First"]', "Ashiq") ||
  fill('input[id*="first_name"]', "Ashiq");

  fill('input[name="user[last_name]"]', "Ganaie") ||
  fill('input[placeholder*="Last"]', "Ganaie") ||
  fill('input[id*="last_name"]', "Ganaie");

  fill('input[name="user[email]"]', "naveeddurfi@gmail.com") ||
  fill('input[type="email"]', "naveeddurfi@gmail.com");

  fill('input[name="user[phone]"]', "+919541246728") ||
  fill('input[type="tel"]', "+919541246728") ||
  fill('input[placeholder*="Phone"]', "+919541246728");

  const passwords = document.querySelectorAll('input[type="password"]');
  if (passwords[0]) {
    passwords[0].focus();
    passwords[0].value = "Ashiq@DA2026!";
    passwords[0].dispatchEvent(new Event("input", { bubbles: true }));
  }
  if (passwords[1]) {
    passwords[1].focus();
    passwords[1].value = "Ashiq@DA2026!";
    passwords[1].dispatchEvent(new Event("input", { bubbles: true }));
  }

  // Check any required checkboxes
  document.querySelectorAll('input[type="checkbox"]').forEach((cb) => cb.click());

  console.log("✅ Form filled! Submitting in 2 seconds...");
  setTimeout(() => {
    const btn =
      document.querySelector('input[type="submit"]') ||
      document.querySelector('button[type="submit"]') ||
      document.querySelector('button');
    if (btn) { btn.click(); console.log("✅ Submitted!"); }
    else console.log("⚠️ Submit button not found — click it manually.");
  }, 2000);
})();
