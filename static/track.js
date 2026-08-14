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

  function send(final) {
    accumulate();
    if (visibleMs < 1000) return;          // a bounce is not a read
    if (final && sent) return;
    sent = final;

    var body = JSON.stringify({
      path: location.pathname,
      ms: visibleMs,
      d: district()
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
      send(false);                          // flush, but the page may come back
    } else if (!since) {
      since = Date.now();
    }
  });

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
