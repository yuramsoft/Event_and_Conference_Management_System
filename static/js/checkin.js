/* Check-in scanner: camera QR scanning (html5-qrcode) + manual entry → DRF /api/checkin/scan/ */
(function () {
  "use strict";
  var app = document.getElementById("checkin-app");
  if (!app) return;

  var eventId = parseInt(app.dataset.event, 10);
  var result = document.getElementById("scan-result");
  var recent = document.getElementById("recent-scans");
  var startBtn = document.getElementById("start-scan");
  var stopBtn = document.getElementById("stop-scan");
  var sound = document.getElementById("sound-toggle");
  var gate = document.getElementById("gate");
  var scanner = null, busy = false, lastCode = "", lastAt = 0;

  var audioCtx = null;
  function beep(ok) {
    if (!sound.checked) return;
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      var o = audioCtx.createOscillator(), g = audioCtx.createGain();
      o.frequency.value = ok ? 880 : 220; o.type = ok ? "sine" : "square";
      g.gain.value = 0.08; o.connect(g); g.connect(audioCtx.destination);
      o.start(); o.stop(audioCtx.currentTime + (ok ? 0.12 : 0.35));
    } catch (e) {}
    if (navigator.vibrate) navigator.vibrate(ok ? 80 : [80, 60, 80]);
  }

  function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }

  function show(data) {
    var cls = data.ok ? "ok" : (data.result === "duplicate" ? "warn" : "bad");
    var icon = data.ok ? "check-circle-fill" : (data.result === "duplicate" ? "exclamation-triangle-fill" : "x-octagon-fill");
    result.className = "eh-scan-result rounded-4 p-4 mb-3 text-center " + cls;
    var t = data.ticket;
    result.innerHTML =
      '<i class="bi bi-' + icon + ' display-5"></i>' +
      '<div class="fs-5 fw-bold mt-2">' + esc(data.message) + "</div>" +
      (t ? '<div class="small mt-1">' + esc(t.ticket_type) + " · " + esc(t.code) + " · order " + esc(t.order) + "</div>" : "");
    beep(data.ok);

    if (data.stats) {
      document.getElementById("st-in").textContent = data.stats.checked_in;
      document.getElementById("st-left").textContent = data.stats.remaining;
      document.getElementById("st-rej").textContent = data.stats.rejected;
      document.getElementById("st-bar").style.width = data.stats.pct + "%";
    }
    var empty = recent.querySelector("[data-empty]");
    if (empty) empty.remove();
    var li = document.createElement("li");
    li.className = "d-flex justify-content-between py-1 border-bottom";
    var now = new Date();
    li.innerHTML = '<span><i class="bi bi-' + (data.ok ? "check-circle-fill text-success" : "x-circle-fill text-danger") + ' me-1"></i>' +
      esc(t ? t.attendee : "Unknown code") + '</span><span class="text-body-secondary">' + esc(data.result.replace("_", " ")) + " · " +
      now.toTimeString().slice(0, 5) + "</span>";
    recent.prepend(li);
    while (recent.children.length > 25) recent.lastElementChild.remove();
  }

  function submit(code, method) {
    code = (code || "").trim();
    if (!code || busy) return;
    // ignore the same QR held in front of the camera
    if (method === "scan" && code === lastCode && Date.now() - lastAt < 3000) return;
    lastCode = code; lastAt = Date.now(); busy = true;
    ehFetch(app.dataset.scanUrl, { json: { event: eventId, code: code, method: method, gate: gate.value } })
      .then(function (r) {
        if (r.status === 401 || r.status === 403) { show({ ok: false, result: "invalid", message: "Your session expired — reload and sign in." }); return; }
        if (!r.ok) { show({ ok: false, result: "invalid", message: (r.data && r.data.detail) || "Scan failed." }); return; }
        show(r.data);
      })
      .catch(function () { show({ ok: false, result: "invalid", message: "Network error — check your connection." }); })
      .finally(function () { setTimeout(function () { busy = false; }, 700); });
  }

  startBtn.addEventListener("click", function () {
    if (!window.Html5Qrcode) { alert("Scanner library failed to load. Use manual entry."); return; }
    scanner = scanner || new Html5Qrcode("reader");
    scanner.start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 240, height: 240 } },
      function (text) { submit(text, "scan"); }, function () {})
      .then(function () { startBtn.classList.add("d-none"); stopBtn.classList.remove("d-none"); })
      .catch(function (e) { alert("Couldn't start the camera: " + e); });
  });
  stopBtn.addEventListener("click", function () {
    if (scanner) scanner.stop().then(function () { stopBtn.classList.add("d-none"); startBtn.classList.remove("d-none"); });
  });

  document.getElementById("manual-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var input = document.getElementById("manual-code");
    submit(input.value.trim(), "manual");
    input.value = "";
    input.focus();
  });

  // Keep counters fresh when several gates scan at once
  setInterval(function () {
    ehFetch(app.dataset.statsUrl).then(function (r) {
      if (!r.ok) return;
      document.getElementById("st-in").textContent = r.data.checked_in;
      document.getElementById("st-left").textContent = r.data.remaining;
      document.getElementById("st-rej").textContent = r.data.rejected;
      document.getElementById("st-bar").style.width = r.data.pct + "%";
    });
  }, 15000);
})();
