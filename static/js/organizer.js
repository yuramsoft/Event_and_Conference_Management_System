/* Organizer dashboard helpers: Chart.js sales chart, DataTables, schedule overlap check. */
(function () {
  "use strict";

  /* ---------- sales chart ---------- */
  var canvas = document.getElementById("salesChart");
  if (canvas && window.Chart) {
    var d = JSON.parse(canvas.dataset.chart || "{}");
    var cur = canvas.dataset.currency || "₦";
    var dark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    var grid = dark ? "rgba(255,255,255,.08)" : "rgba(0,0,0,.06)";
    var text = dark ? "#cbd5e1" : "#64748b";
    new Chart(canvas, {
      data: {
        labels: d.labels,
        datasets: [
          { type: "bar", label: "Revenue", data: d.revenue, backgroundColor: "rgba(79,70,229,.75)", borderRadius: 4, yAxisID: "y" },
          { type: "line", label: "Orders", data: d.orders, borderColor: "#f59e0b", backgroundColor: "#f59e0b", cubicInterpolationMode: "monotone", pointRadius: 2, yAxisID: "y1" }
        ]
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { color: text, boxWidth: 12 } },
          tooltip: { callbacks: { label: function (c) { return c.dataset.label === "Revenue" ? " " + cur + Number(c.raw).toLocaleString() : " " + c.raw + " orders"; } } }
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: text, maxRotation: 0, autoSkip: true, maxTicksLimit: 10 } },
          y: { grid: { color: grid }, ticks: { color: text, callback: function (v) { return cur + Number(v).toLocaleString(); } }, beginAtZero: true },
          y1: { position: "right", grid: { display: false }, ticks: { color: text, precision: 0 }, beginAtZero: true }
        }
      }
    });
  }

  /* ---------- DataTables ---------- */
  if (window.DataTable) {
    document.querySelectorAll("table[data-datatable]").forEach(function (t) {
      var col = t.dataset.orderCol;
      new DataTable(t, {
        pageLength: 25,
        order: col !== undefined ? [[parseInt(col, 10), "desc"]] : [],
        language: { search: "", searchPlaceholder: "Search…" }
      });
    });
  }

  /* ---------- schedule overlaps ---------- */
  document.querySelectorAll(".eh-room").forEach(function (room) {
    var items = Array.prototype.map.call(room.querySelectorAll(".eh-session"), function (el) {
      return { el: el, s: new Date(el.dataset.start), e: new Date(el.dataset.end) };
    });
    items.forEach(function (a, i) {
      items.forEach(function (b, j) {
        if (i !== j && a.s < b.e && b.s < a.e) {
          a.el.classList.add("is-overlap");
          a.el.querySelector(".eh-overlap").classList.remove("d-none");
        }
      });
    });
  });
})();
