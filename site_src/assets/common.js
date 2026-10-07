"use strict";
// Theme (light/dark, remembered), count-up numbers, scroll reveal. Shared by both pages.
(function () {
  const root = document.documentElement, store = (() => { try { return window.localStorage; } catch (e) { return null; } })();
  const saved = store && store.getItem("theme");
  root.dataset.theme = saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  window.setTheme = t => { root.dataset.theme = t; if (store) store.setItem("theme", t); document.dispatchEvent(new CustomEvent("themechange")); };
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-theme-toggle]"); if (!b) return;
    window.setTheme(root.dataset.theme === "dark" ? "light" : "dark");
  });
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.countUp = el => {
    const final = el.dataset.final || el.textContent, m = final.match(/^([^\d-]*)(-?[\d,]*\.?\d+)(.*)$/);
    if (!m || reduce) { el.textContent = final; return; }
    const target = parseFloat(m[2].replace(/,/g, "")), dec = (m[2].split(".")[1] || "").length, t0 = performance.now(), dur = 900;
    const fmt = v => v.toLocaleString("en-US", {minimumFractionDigits: dec, maximumFractionDigits: dec});
    (function tick(now) {
      const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = m[1] + fmt(target * e) + m[3];
      if (p < 1) requestAnimationFrame(tick); else el.textContent = final;
    })(t0);
  };
  window.observeReveal = () => {
    const io = new IntersectionObserver(es => es.forEach(x => {
      if (!x.isIntersecting) return; x.target.classList.add("in");
      x.target.querySelectorAll(".num[data-final]").forEach(window.countUp); io.unobserve(x.target);
    }), {threshold: 0.15});
    document.querySelectorAll(".reveal").forEach(el => io.observe(el));
  };
  window.vegaTheme = () => {
    const cs = getComputedStyle(root), v = n => cs.getPropertyValue(n).trim();
    return {background: "transparent", font: "Lato, system-ui, sans-serif", view: {stroke: "transparent"},
      axis: {labelColor: v("--muted"), titleColor: v("--muted"), gridColor: v("--line"), domainColor: v("--line"), tickColor: v("--line"), labelFont: "Lato, sans-serif"},
      legend: {labelColor: v("--muted"), titleColor: v("--muted")}, title: {color: v("--ink"), font: "Newsreader, Georgia, serif", fontWeight: 500},
      range: {category: [v("--chart-a"), v("--chart-hot"), "#8ec2a4", "#2b6a46", "#e2b93b", "#6ba3d6", "#c97ab0", "#9ca38f", "#b9b6ac", "#4d8aa8", "#a98467", "#d5c29a"]}};
  };
  window.ICON = {
    contrast: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 3v18a9 9 0 0 0 0-18z" fill="currentColor"/></svg>',
    gh: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>',
    logo: '<svg viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#2b6a46"/><path d="M7 22l6-7 4 4 8-10" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="25" cy="9" r="2.4" fill="#ef6c0f"/></svg>'
  };
  // Shared top navigation and footer, injected so both pages stay identical.
  window.mountChrome = page => {
    const base = page === "home" ? "" : "../";
    document.getElementById("nav").outerHTML = `<nav class="top" aria-label="Main"><div class="in">
      <a class="brand" href="${base || './'}">${ICON.logo}<span>Deduction Analytics</span></a><span class="spacer"></span>
      <a class="link" href="${base || './'}" ${page === "home" ? 'aria-current="page"' : ""}>Home</a>
      <a class="link" href="${base}dashboard/" ${page === "dashboard" ? 'aria-current="page"' : ""}>Dashboard</a>
      <a class="iconbtn" href="https://github.com/jainamh029/cpg-deduction-analytics" aria-label="Source code on GitHub" title="Source code">${ICON.gh}</a>
      <button class="iconbtn" data-theme-toggle aria-label="Toggle light and dark theme" title="Toggle theme">${ICON.contrast}</button></div></nav>`;
  };
})();
