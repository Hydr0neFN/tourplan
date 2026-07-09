(function () {
  "use strict";
  var state = JSON.parse(document.getElementById("bootstrap").textContent);
  var T = JSON.parse(document.getElementById("i18n").textContent);
  var LANG = window.LANG || "zh";
  var MONTH_EN = ["", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];
  var expandedId = null;
  var pollTimer = null;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function d(iso) { var p = iso.split("-"); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function iso(dt) {
    var m = dt.getMonth() + 1, day = dt.getDate();
    return dt.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (day < 10 ? "0" : "") + day;
  }
  function addDays(dt, n) { var x = new Date(dt); x.setDate(x.getDate() + n); return x; }
  function isOpen() {
    return state.tour.open_now !== undefined ? !!state.tour.open_now : state.tour.status === "open";
  }
  function joined() { return !!state.me; }

  function label(p) {
    var base = LANG === "zh" ? p.label_zh : p.label_en;
    if (p.is_me && state.me && state.me.name) base = state.me.name;
    return base + (p.is_me ? T.you_suffix : "");
  }

  function rangesText(isoList) {
    if (!isoList.length) return T.none;
    var ds = isoList.slice().sort().map(d);
    var out = [], lastMonth = -1, i = 0;
    while (i < ds.length) {
      var s = ds[i], e = s, j = i + 1;
      while (j < ds.length && ds[j] - e === 86400000) { e = ds[j]; j++; }
      var sm = s.getMonth() + 1, em = e.getMonth() + 1, txt;
      if (sm === em) {
        txt = (sm !== lastMonth ? sm + "/" : "") + s.getDate();
        if (e > s) txt += "–" + e.getDate();
        lastMonth = sm;
      } else {
        txt = sm + "/" + s.getDate() + "–" + em + "/" + e.getDate();
        lastMonth = em;
      }
      out.push(txt);
      i = j;
    }
    return out.join("、");
  }

  function rangeDays() {
    var out = [], cur = d(state.tour.date_start), end = d(state.tour.date_end);
    while (cur <= end) { out.push(iso(cur)); cur = addDays(cur, 1); }
    return out;
  }
  function yesDaysOf(denies) {
    var dset = {};
    denies.forEach(function (x) { dset[x] = 1; });
    return rangeDays().filter(function (day) { return !dset[day]; });
  }

  function othersAt(day) {
    var yes = [], no = [];
    state.participants.forEach(function (p) {
      if (p.is_me) return;
      (p.denies.indexOf(day) >= 0 ? no : yes).push(p.icon);
    });
    return { yes: yes, no: no };
  }

  function iconRow(list, cls) {
    if (!list.length) return "";
    var h = '<div class="vrow ' + cls + '">';
    if (list.length <= 2) {
      list.forEach(function (em) { h += '<span class="em">' + em + "</span>"; });
    } else {
      h += '<span class="em">' + list[0] + "</span><span>+" + (list.length - 1) + "</span>";
    }
    return h + "</div>";
  }

  function monthTitle(y, m) {
    return LANG === "zh"
      ? y + "年" + m + "月"
      : MONTH_EN[m] + " " + y;
  }

  function renderMonths() {
    var start = d(state.tour.date_start), end = d(state.tour.date_end);
    var myDenies = {};
    if (joined()) state.me.denies.forEach(function (x) { myDenies[x] = 1; });
    var interactive = isOpen() && joined();
    var h = "";
    var y = start.getFullYear(), m = start.getMonth();
    while (y < end.getFullYear() || (y === end.getFullYear() && m <= end.getMonth())) {
      var first = new Date(y, m, 1);
      var daysInMonth = new Date(y, m + 1, 0).getDate();
      h += '<section class="month"><h2 class="month-title">' + monthTitle(y, m + 1) + "</h2>";
      h += '<div class="grid">';
      T.weekdays.forEach(function (w) { h += '<div class="wd">' + esc(w) + "</div>"; });
      for (var b = 0; b < first.getDay(); b++) h += "<div></div>";
      for (var day = 1; day <= daysInMonth; day++) {
        var dt = new Date(y, m, day), di = iso(dt);
        var inRange = dt >= start && dt <= end;
        if (!inRange) {
          h += '<div class="cell out"><span class="dnum">' + day + "</span></div>";
          continue;
        }
        var mine = myDenies[di] ? "no" : "yes";
        var oth = othersAt(di);
        h += '<div class="cell in ' + mine + (interactive ? "" : " readonly") +
          '" data-date="' + di + '"><span class="dnum">' + day + "</span>" +
          iconRow(oth.yes, "okrow") + "</div>";
      }
      h += "</div></section>";
      m++;
      if (m === 12) { m = 0; y++; }
    }
    document.getElementById("months").innerHTML = h;
  }

  function renderList() {
    var ps = state.participants.slice().sort(function (a, b) {
      return (b.is_me ? 1 : 0) - (a.is_me ? 1 : 0) || a.id - b.id;
    });
    var h = "";
    ps.forEach(function (p) {
      var open = expandedId === p.id;
      var sum = p.denies.length === 0
        ? '<span class="psum okc">' + esc(T.all_ok) + "</span>"
        : '<span class="psum noc">' + esc(T.deny_prefix) + " " + esc(rangesText(p.denies)) + "</span>";
      h += '<button class="prow" data-pid="' + p.id + '">' +
        '<span class="avatar">' + p.icon + "</span>" +
        '<span class="pname">' + esc(label(p)) + "</span>" + sum +
        '<span class="chev">' + (open ? "▲" : "▼") + "</span></button>";
      if (open) {
        h += '<div class="pdetail">' +
          '<p class="okline">✓ ' + esc(T.ok_label) + "：" + esc(rangesText(yesDaysOf(p.denies))) + "</p>" +
          '<p class="noline">✕ ' + esc(T.no_label) + "：" + esc(rangesText(p.denies)) + "</p></div>";
      }
    });
    document.getElementById("plist").innerHTML = h;
  }

  function render() { renderMonths(); renderList(); }

  function applyState(next) {
    if (next && next.tour) { state = next; render(); syncBanner(); }
  }

  function syncBanner() {
    if (isOpen() || document.querySelector(".banner-closed")) return;
    var div = document.createElement("div");
    div.className = "banner-closed";
    div.textContent = T.closed_banner;
    var months = document.getElementById("months");
    months.parentNode.insertBefore(div, months);
  }

  function api(path, body) {
    return fetch("/t/" + state.tour.slug + "/api" + path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin"
    }).then(function (r) {
      if (!r.ok) throw new Error("http " + r.status);
      return r.json();
    });
  }

  document.getElementById("months").addEventListener("click", function (e) {
    var cell = e.target.closest(".cell.in");
    if (!cell || !isOpen() || !joined()) return;
    var day = cell.getAttribute("data-date");
    var denies = state.me.denies;
    var idx = denies.indexOf(day);
    var deny = idx < 0;
    if (deny) denies.push(day); else denies.splice(idx, 1);
    state.participants.forEach(function (p) {
      if (!p.is_me) return;
      p.denies = denies.slice();
    });
    render();
    api("/vote", { date: day, deny: deny }).then(applyState).catch(function () {
      api("/state").then(applyState);
    });
  });

  document.getElementById("plist").addEventListener("click", function (e) {
    var row = e.target.closest(".prow");
    if (!row) return;
    var pid = +row.getAttribute("data-pid");
    expandedId = expandedId === pid ? null : pid;
    renderList();
  });

  // ---- overlays -------------------------------------------------------
  var modalRoot = document.getElementById("modal-root");

  function showJoinModal() {
    var required = !!state.tour.require_name;
    modalRoot.innerHTML =
      '<div class="overlay"><div class="dialog">' +
      "<h2>" + esc(T.name_title) + "</h2>" +
      "<p>" + esc(required ? T.name_required_hint : T.name_hint) + "</p>" +
      '<input id="join-name" maxlength="20" placeholder="' + esc(T.name_placeholder) + '">' +
      '<p id="join-err" class="err" style="display:none; margin:-8px 0 12px; font-size:13px;"></p>' +
      '<div class="btnrow">' +
      (required ? "" : '<button class="btn" id="join-skip">' + esc(T.skip) + "</button>") +
      '<button class="btn primary" id="join-go">' + esc(T["continue"]) + "</button>" +
      "</div></div></div>";
    function join(name) {
      if (required && !name.trim()) {
        var err = document.getElementById("join-err");
        err.textContent = T.name_required_error;
        err.style.display = "block";
        return;
      }
      api("/join", { name: name }).then(function (next) {
        modalRoot.innerHTML = "";
        applyState(next);
        maybeTutorial(true);
        startPoll();
      }).catch(function () { modalRoot.innerHTML = ""; });
    }
    var skipBtn = document.getElementById("join-skip");
    if (skipBtn) skipBtn.onclick = function () { join(""); };
    document.getElementById("join-go").onclick = function () {
      join(document.getElementById("join-name").value);
    };
  }

  var tutSteps = [
    { t: "tut1_title", b: "tut1_body" },
    { t: "tut2_title", b: "tut2_body" },
    { t: "tut3_title", b: "tut3_body" }
  ];
  function showTutorial(step) {
    var s = tutSteps[step];
    var dots = tutSteps.map(function (_, i) {
      return "<span" + (i === step ? ' class="on"' : "") + "></span>";
    }).join("");
    var last = step === tutSteps.length - 1;
    modalRoot.innerHTML =
      '<div class="overlay"><div class="dialog">' +
      '<div class="tut-dots">' + dots + "</div>" +
      "<h2>" + esc(T[s.t]) + "</h2><p>" + esc(T[s.b]) + "</p>" +
      '<div class="btnrow"><button class="btn primary" id="tut-next">' +
      esc(last ? T.tut_done : T.tut_next) + "</button></div></div></div>";
    document.getElementById("tut-next").onclick = function () {
      if (last) { modalRoot.innerHTML = ""; }
      else showTutorial(step + 1);
    };
  }
  function maybeTutorial(force) {
    var key = "tut_" + state.tour.slug;
    if (!force && localStorage.getItem(key)) return;
    localStorage.setItem(key, "1");
    showTutorial(0);
  }
  document.getElementById("btn-tutorial").addEventListener("click", function () {
    showTutorial(0);
  });

  function refresh() {
    api("/state").then(applyState).catch(function () {});
  }

  function startPoll() {
    if (pollTimer) return;
    pollTimer = setInterval(function () {
      if (document.hidden) return;
      refresh();
    }, 5000);
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && joined()) refresh();
  });

  // ---- boot -----------------------------------------------------------
  render();
  if (!joined() && isOpen()) showJoinModal();
  else if (joined()) { maybeTutorial(false); startPoll(); }
})();
