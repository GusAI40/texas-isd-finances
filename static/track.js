/* Dwell beacon for outreach recipients.
 *
 * Runs for one kind of visitor only: someone who arrived from a link we
 * mailed them. The server signals that by setting a contentless `txj_on=1`
 * cookie next to the real (httpOnly) identity cookie. This script can see the
 * flag and never the identity — the rid is not readable from JavaScript, is
 * not in the DOM, and is not in the beacon body. The server reads it from the
 * httpOnly cookie that rides along with the POST.
 *
 * Everyone else: this file returns immediately and the page behaves exactly as
 * it did before, counted only in the daily aggregate totals.
 *
 * What is measured is VISIBLE time, not wall-clock time. A tab left open
 * behind another window is not reading, and counting it would turn "how long
 * did the superintendent spend on their deficit page" into a measure of how
 * untidy their desktop is.
 */
(function () {
  "use strict";

  if (document.cookie.indexOf("txj_on=1") === -1) return;

  var visibleMs = 0;
  var since = document.visibilityState === "visible" ? Date.now() : 0;
  var sent = false;

  function district() {
    try {
      return new URLSearchParams(location.search).get("d") || null;
    } catch (e) {
      return null;
    }
  }

  function accumulate() {
    if (since) {
      visibleMs += Date.now() - since;
      since = 0;
    }
  }

  /* ---- section engagement -------------------------------------------------
     Page views say someone arrived. They do not say what they read. Sections
     mark themselves with data-section, and a section counts as ENGAGED only
     when it has been at least half on screen for four seconds — scrolling past
     something is not reading it, and an event per scroll pixel would be a
     stream nobody could aggregate.

     Time accrues only while the tab is VISIBLE, for the same reason the page
     dwell does: a tab behind another window is not a superintendent reading
     their deficit page, it is an untidy desktop. */
  var SECTION_MIN_MS = 4000;
  var VISIBLE_FRACTION = 0.5;
  var sections = {};                        // slug -> {ms, since, sent}
  var sessionMark = String(Date.now()) + "-" + Math.floor(Math.random() * 1e6);

  function bumpSections() {
    var now = Date.now();
    for (var k in sections) {
      var s = sections[k];
      if (s.since) { s.ms += now - s.since; s.since = now; }
    }
  }

  function pauseSections() {
    var now = Date.now();
    for (var k in sections) {
      var s = sections[k];
      if (s.since) { s.ms += now - s.since; s.since = 0; }
    }
  }

  function watchSections() {
    if (!window.IntersectionObserver) return;   // no observer, no section data
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        var slug = e.target.getAttribute("data-section");
        if (!slug) return;
        var s = sections[slug] || (sections[slug] = { ms: 0, since: 0, sent: 0 });
        if (e.isIntersecting && document.visibilityState === "visible") {
          if (!s.since) s.since = Date.now();
        } else if (s.since) {
          s.ms += Date.now() - s.since;
          s.since = 0;
        }
      });
    }, { threshold: VISIBLE_FRACTION });
    document.querySelectorAll("[data-section]").forEach(function (el) {
      obs.observe(el);
    });
  }

  /* Only what has newly accrued past the threshold, and only the increment —
     `sent` is the high-water mark already reported, so a section read for 41s
     and flushed three times reports 41s once, not 123s. The key makes a
     replayed beacon a no-op at the database as well. */
  function pendingSections() {
    bumpSections();
    var out = [];
    for (var k in sections) {
      var s = sections[k];
      if (s.ms >= SECTION_MIN_MS && s.ms > s.sent) {
        out.push({
          event: "section",
          section: k,
          path: location.pathname,
          ms: s.ms,
          d: district(),
          key: sessionMark + ":" + k + ":" + location.pathname + ":" + s.ms
        });
        s.sent = s.ms;
      }
    }
    return out;
  }

  function send(final) {
    accumulate();
    var secs = pendingSections();
    if (visibleMs < 1000 && !secs.length) return;   // a bounce is not a read
    if (final && sent) return;
    sent = final;

    var body = JSON.stringify({
      path: location.pathname,
      ms: visibleMs,
      d: district(),
      sections: secs
    });
    visibleMs = 0;                          // never double-count a flushed span

    // sendBeacon survives the page unloading; fetch(keepalive) is the fallback
    // for the few browsers that still lack it.
    try {
      var blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon && navigator.sendBeacon("/e", blob)) return;
    } catch (e) { /* fall through */ }
    try {
      fetch("/e", {
        method: "POST",
        body: body,
        keepalive: true,
        headers: { "Content-Type": "application/json" }
      });
    } catch (e) { /* a lost beacon is not worth an error */ }
  }

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") {
      pauseSections();
      send(false);                          // flush, but the page may come back
    } else {
      if (!since) since = Date.now();
      bumpSections();
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watchSections);
  } else {
    watchSections();
  }

  // pagehide is the reliable end-of-life event on mobile Safari, where
  // beforeunload often never fires at all.
  window.addEventListener("pagehide", function () { send(true); });

  // A long read that never hides and never unloads (a dashboard left open on
  // one page) would otherwise report nothing at all. Flush every 60s.
  setInterval(function () {
    if (document.visibilityState === "visible") {
      accumulate();
      since = Date.now();
      send(false);
    }
  }, 60000);
})();
