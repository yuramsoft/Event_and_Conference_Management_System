/* EventHandler — shared vanilla JS (no framework) */
(function () {
  "use strict";

  function getCookie(name) {
    var m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? decodeURIComponent(m.pop()) : "";
  }
  function csrfToken() {
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return (input && input.value) || getCookie("csrftoken");
  }

  /** fetch() wrapper for DRF endpoints using session auth + CSRF. */
  window.ehFetch = function (url, opts) {
    opts = opts || {};
    opts.credentials = "same-origin";
    opts.headers = Object.assign({ "Accept": "application/json", "X-CSRFToken": csrfToken() }, opts.headers || {});
    if (opts.json !== undefined) {
      opts.method = opts.method || "POST";
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.json);
      delete opts.json;
    }
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) { return { ok: r.ok, status: r.status, data: data }; });
    });
  };

  window.ehMoney = function (n) {
    var sym = window.EH_CURRENCY || "₦";
    n = Number(n || 0);
    return sym + n.toLocaleString(undefined, { minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 });
  };

  /* ---------- theme toggle ---------- */
  document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var root = document.documentElement;
      var next = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-bs-theme", next);
      try { localStorage.setItem("eh-theme", next); } catch (e) {}
    });
  });

  /* ---------- toasts auto-hide ---------- */
  document.querySelectorAll(".eh-toasts .toast").forEach(function (el) {
    if (window.bootstrap) new bootstrap.Toast(el).show();
  });

  /* ---------- confirm buttons ---------- */
  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-confirm]");
    if (el && !window.confirm(el.getAttribute("data-confirm"))) { e.preventDefault(); e.stopPropagation(); }
  }, true);

  /* ---------- countdown (reservation timer) ---------- */
  document.querySelectorAll("[data-countdown]").forEach(function (el) {
    var left = parseInt(el.getAttribute("data-countdown"), 10) || 0;
    function tick() {
      if (left <= 0) {
        el.textContent = el.getAttribute("data-expired-text") || "00:00";
        el.classList.add("text-danger");
        var form = document.getElementById("checkout-form");
        if (form) form.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
        return;
      }
      var m = Math.floor(left / 60), s = left % 60;
      el.textContent = (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
      if (left < 120) el.classList.add("text-danger");
      left -= 1;
      setTimeout(tick, 1000);
    }
    tick();
  });

  /* ---------- relative time ---------- */
  document.querySelectorAll("[data-relative]").forEach(function (el) {
    var d = new Date(el.getAttribute("data-relative")), diff = (d - new Date()) / 86400000;
    if (isNaN(diff)) return;
    el.textContent = diff < 1 ? "today" : diff < 2 ? "tomorrow" : "in " + Math.round(diff) + " days";
  });

  /* ---------- ticket selection + live quote ---------- */
  var form = document.getElementById("ticket-form");
  if (form) {
    var inputs = form.querySelectorAll("input[data-tt]");
    var btn = document.getElementById("reserve-btn");
    var codeInput = document.getElementById("discount-code");
    var msg = document.getElementById("discount-msg");
    var err = document.getElementById("q-error");
    var timer = null;

    function selections() {
      var sel = {}, count = 0;
      inputs.forEach(function (i) { var q = parseInt(i.value, 10) || 0; if (q > 0) { sel[i.dataset.tt] = q; count += q; } });
      return { sel: sel, count: count };
    }
    function localTotal() {
      var t = 0;
      inputs.forEach(function (i) { t += (parseInt(i.value, 10) || 0) * parseFloat(i.dataset.price); });
      return t;
    }
    function render(sub, disc, total) {
      document.getElementById("q-subtotal").textContent = ehMoney(sub);
      document.getElementById("q-discount").textContent = disc > 0 ? "−" + ehMoney(disc) : "—";
      document.getElementById("q-total").textContent = ehMoney(total);
    }
    function refresh(withCode) {
      var s = selections();
      btn.disabled = s.count === 0;
      btn.textContent = s.count === 0 ? "Select tickets" : "Reserve " + s.count + " ticket" + (s.count > 1 ? "s" : "");
      var sub = localTotal();
      render(sub, 0, sub);
      err.textContent = "";
      if (!s.count) return;
      clearTimeout(timer);
      timer = setTimeout(function () {
        ehFetch(form.dataset.quoteUrl, { json: { selections: s.sel, discount_code: codeInput.value.trim() } }).then(function (r) {
          if (!r.ok || !r.data.ok) { err.textContent = (r.data && (r.data.error || r.data.detail)) || "Could not price this selection."; btn.disabled = true; return; }
          render(r.data.subtotal, parseFloat(r.data.discount), r.data.total);
          if (codeInput.value.trim()) {
            if (r.data.discount_error) { msg.className = "small mt-1 text-danger"; msg.textContent = r.data.discount_error; }
            else if (r.data.discount_label) { msg.className = "small mt-1 text-success"; msg.textContent = "✓ " + r.data.discount_label + " applied"; }
          } else { msg.textContent = ""; }
        });
      }, withCode ? 0 : 250);
    }
    form.querySelectorAll("[data-step]").forEach(function (b) {
      b.addEventListener("click", function () {
        var input = b.parentElement.querySelector("input");
        var v = parseInt(input.value, 10) || 0, step = parseInt(b.dataset.step, 10);
        var min = parseInt(input.dataset.min, 10) || 1, max = parseInt(input.max, 10);
        v = v + step;
        if (step > 0 && v > 0 && v < min) v = min;     // jump to minimum
        if (step < 0 && v < min) v = 0;
        v = Math.max(0, Math.min(max, v));
        input.value = v;
        refresh();
      });
    });
    inputs.forEach(function (i) { i.addEventListener("input", function () { refresh(); }); });
    document.getElementById("apply-discount").addEventListener("click", function () {
      if (!selections().count) { msg.className = "small mt-1 text-body-secondary"; msg.textContent = "Select tickets first."; return; }
      refresh(true);
    });
    codeInput.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); refresh(true); } });
    form.addEventListener("submit", function () { btn.disabled = true; btn.textContent = "Reserving…"; });
    refresh();
  }
})();
