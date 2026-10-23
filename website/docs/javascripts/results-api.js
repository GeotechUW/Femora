/* Progressive enhancement: source-generated API details stay readable without JS. */
(() => {
  function revealTarget() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const target = document.getElementById(id);
    if (!target) return;
    let parent = target.closest("details");
    while (parent) {
      parent.open = true;
      parent = parent.parentElement.closest("details");
    }
  }

  function initialize() {
    const article = document.querySelector(".md-content__inner");
    if (!article || article.dataset.resultsEnhanced) return;
    const root = article.querySelector(
      '.doc-heading[id^="femora.results."], .doc-heading[id^="femora.jobs."], .doc-heading[id^="femora.runtime."], .doc-heading[id^="femora.core."]'
    );
    if (!root) return;
    article.dataset.resultsEnhanced = "true";
    const panels = [];
    article.querySelectorAll(".doc-children > .doc-object").forEach(member => {
      if (!member.matches(".doc-function, .doc-attribute")) return;
      const heading = member.querySelector(":scope > .doc-heading");
      if (!heading) return;
      const panel = document.createElement("details");
      panel.className = "results-api-member";
      const summary = document.createElement("summary");
      member.before(panel);
      summary.append(heading);
      panel.append(summary, member);
      panels.push(panel);
    });
    if (!panels.length) return;
    const toolbar = document.createElement("div");
    toolbar.className = "results-api-controls";
    const hint = document.createElement("span");
    hint.textContent = "Select a member to expand its documentation.";
    toolbar.append(hint);
    for (const [label, open] of [["Expand all", true], ["Collapse all", false]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.addEventListener("click", () => panels.forEach(panel => { panel.open = open; }));
      toolbar.append(button);
    }
    panels[0].parentElement.prepend(toolbar);
    revealTarget();
    if (location.hash) requestAnimationFrame(() => {
      let target;
      try { target = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch { return; }
      target?.scrollIntoView();
    });
    // Opening before the browser follows a local link preserves anchor scrolling.
    document.addEventListener("click", event => {
      const link = event.target.closest("a[href]");
      if (!link) return;
      const url = new URL(link.href, location.href);
      if (url.pathname !== location.pathname || url.origin !== location.origin || !url.hash) return;
      let target;
      try { target = document.getElementById(decodeURIComponent(url.hash.slice(1))); } catch { return; }
      const panel = target?.closest(".results-api-member");
      if (panel) panel.open = true;
    });
  }
  window.addEventListener("hashchange", revealTarget);
  window.addEventListener("beforeprint", () => {
    document.querySelectorAll(".results-api-member").forEach(panel => {
      panel.dataset.wasOpen = String(panel.open);
      panel.open = true;
    });
  });
  window.addEventListener("afterprint", () => {
    document.querySelectorAll(".results-api-member").forEach(panel => {
      panel.open = panel.dataset.wasOpen === "true";
    });
  });
  if (typeof document$ !== "undefined") document$.subscribe(initialize);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize);
  else initialize();
})();
