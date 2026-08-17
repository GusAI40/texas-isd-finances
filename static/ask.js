/* The intelligence layer, reachable from every page without leaving it.
 *
 * One floating "Ask" button on every page opens a sheet: type a plain-English
 * question, an AI answers from the same read-only official data as /query,
 * and the words write themselves onto the screen. No navigation, no reload —
 * the page underneath is exactly where the reader left it.
 *
 * Design rules this file keeps:
 * - House system only: design.css tokens (with fallbacks), monochrome + the
 *   one accent, system type. No external assets — the CSP forbids them.
 * - The reveal is presentation, never latency: the full answer has already
 *   arrived when the first word appears. Reduced motion gets it instantly.
 * - Large targets and large type throughout: the bar this has to clear is a
 *   grandmother on a phone, not a designer on a studio monitor.
 * - Progressive enhancement: every "Ask a question" link keeps its real
 *   /#ask-section href. This script intercepts in the CAPTURE phase (the
 *   masthead's own click resolver runs at bubble) and opens the sheet in
 *   place; if this file ever fails to load, the links still navigate.
 * - Answers are DATA, not text and not markup. /query returns a `structured`
 *   object (src/answer.py): a lead, typed blocks, deterministic figures, a
 *   computed comparison, sources, and follow-up questions. This file decides
 *   what those LOOK like. The model decides what they MEAN. Nothing it writes
 *   is ever interpreted as markup — every string lands via textContent, so
 *   the worst a hostile answer can do is read oddly.
 *
 *   Before this, /query returned one string and the sheet printed it with
 *   textContent — correct security, but it meant the reader saw the model's
 *   literal `**bold**` and `| pipes |`. The bug looked like a missing Markdown
 *   renderer. It was actually presentation delegated to the model.
 */
(function () {
  'use strict';
  if (window.TISDAsk) return;

  var reduce = window.matchMedia
    && matchMedia('(prefers-reduced-motion: reduce)').matches;

  var STARTERS = [
    'How much does Dallas ISD spend per student?',
    'How many school districts are in Texas?',
    'Which district has the most students?',
  ];

  var css = [
    '.ta-fab { position:fixed; right:16px; bottom:16px; z-index:190;',
    '  display:flex; align-items:center; gap:.55rem; min-height:52px;',
    '  padding:.75rem 1.25rem; border-radius:999px; cursor:pointer;',
    '  border:1px solid var(--rule, #e3e6e8);',
    '  background:var(--ink, #14171a); color:var(--bg, #fff);',
    '  font:600 1rem/1 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;',
    '  box-shadow:0 6px 24px rgba(0,0,0,.18); }',
    '.ta-fab:hover { transform:translateY(-1px); }',
    '.ta-fab:focus-visible { outline:3px solid var(--accent, #1a56a8); outline-offset:2px; }',
    '.ta-fab .ta-mk { display:grid; grid-template-columns:1fr 1fr; gap:2px; width:16px; height:16px; }',
    '.ta-fab .ta-mk i { background:var(--accent, #6ea8ee); border-radius:2px; }',
    '.ta-fab .ta-mk i:last-child { background:var(--bg, #fff); opacity:.65; }',
    '@media (max-width: 480px) { .ta-fab .ta-long { display:none; } }',
    /* overlay + sheet */
    '.ta-wrap { position:fixed; inset:0; z-index:200; display:none; }',
    '.ta-wrap.open { display:block; }',
    '.ta-back { position:absolute; inset:0; background:rgba(10,12,14,.42);',
    '  backdrop-filter:blur(3px); -webkit-backdrop-filter:blur(3px); }',
    '.ta-sheet { position:absolute; left:50%; transform:translateX(-50%);',
    '  bottom:0; width:min(680px, 100%); max-height:88vh;',
    '  display:flex; flex-direction:column;',
    '  background:var(--bg, #fff); color:var(--ink, #14171a);',
    '  border:1px solid var(--rule, #e3e6e8); border-bottom:none;',
    '  border-radius:18px 18px 0 0; box-shadow:0 -12px 48px rgba(0,0,0,.22);',
    '  font:16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }',
    '@media (min-width: 720px) { .ta-sheet { bottom:auto; top:50%;',
    '  transform:translate(-50%,-50%); border-radius:16px; border-bottom:1px solid var(--rule,#e3e6e8);',
    '  max-height:min(84vh, 720px); } }',
    '.ta-wrap.open .ta-sheet { animation:ta-up .32s cubic-bezier(.2,.8,.25,1); }',
    '@keyframes ta-up { from { opacity:0; transform:translate(-50%, 24px); } }',
    '@media (min-width: 720px) { .ta-wrap.open .ta-sheet {',
    '  animation:ta-in .28s cubic-bezier(.2,.8,.25,1); } }',
    '@keyframes ta-in { from { opacity:0; transform:translate(-50%, calc(-50% + 14px)); } }',
    '@media (prefers-reduced-motion: reduce) { .ta-wrap.open .ta-sheet { animation:none; } }',
    /* header */
    '.ta-head { display:flex; align-items:flex-start; gap:.7rem; padding:1.1rem 1.25rem .4rem; }',
    '.ta-head h2 { margin:0; font-size:1.2rem; line-height:1.3; letter-spacing:-.01em; }',
    '.ta-head p { margin:.15rem 0 0; color:var(--muted, #5a6572); font-size:.92rem; }',
    '.ta-x { margin-left:auto; flex:none; width:44px; height:44px; border-radius:10px;',
    '  border:1px solid var(--rule, #e3e6e8); background:none; color:var(--muted, #5a6572);',
    '  font-size:1.35rem; line-height:1; cursor:pointer; }',
    '.ta-x:hover { color:var(--ink, #14171a); background:var(--wash, #f4f5f4); }',
    '.ta-x:focus-visible { outline:3px solid var(--accent, #1a56a8); outline-offset:2px; }',
    /* thread */
    '.ta-thread { flex:1; overflow-y:auto; padding:.6rem 1.25rem; min-height:4rem;',
    '  overscroll-behavior:contain; scroll-behavior:smooth; }',
    '@media (prefers-reduced-motion: reduce) { .ta-thread { scroll-behavior:auto; } }',
    '.ta-msg { display:flex; gap:.6rem; margin:.65rem 0; }',
    '.ta-msg.me { justify-content:flex-end; }',
    '.ta-msg.me .ta-bub { background:var(--accent, #1a56a8); color:var(--accent-ink, #fff);',
    '  border-radius:16px 16px 4px 16px; max-width:85%; }',
    '.ta-msg.ai .ta-bub { background:var(--surface, #f6f7f6);',
    '  border:1px solid var(--rule, #e3e6e8); border-radius:4px 16px 16px 16px; max-width:92%; }',
    '.ta-bub { padding:.65rem .9rem; font-size:1rem; overflow-wrap:anywhere; }',
    '.ta-av { flex:none; width:24px; height:24px; margin-top:2px; display:grid;',
    '  grid-template-columns:1fr 1fr; gap:2px; align-content:center; padding:4px;',
    '  background:var(--ink, #14171a); border-radius:7px; }',
    '.ta-av i { background:var(--accent, #6ea8ee); border-radius:1.5px; min-height:6px; }',
    '.ta-av i:last-child { background:#fff; opacity:.6; }',
    /* the skeleton: shimmering lines while the model reads the data */
    '.ta-skel { display:block; }',
    '.ta-skel i { display:block; height:.72em; margin:.45em 0; border-radius:4px;',
    '  background:linear-gradient(90deg, var(--rule, #e3e6e8) 25%,',
    '    var(--wash, #eef0ef) 42%, var(--rule, #e3e6e8) 58%);',
    '  background-size:200% 100%; animation:ta-shim 1.15s linear infinite; }',
    '.ta-skel i:nth-child(1) { width:92%; } .ta-skel i:nth-child(2) { width:78%; }',
    '.ta-skel i:nth-child(3) { width:60%; }',
    '@keyframes ta-shim { to { background-position:-200% 0; } }',
    '@media (prefers-reduced-motion: reduce) { .ta-skel i { animation:none; } }',
    '.ta-think { color:var(--muted, #5a6572); font-size:.85rem; }',
    /* the words, arriving */
    '.ta-bub .w { opacity:0; filter:blur(5px); display:inline-block;',
    '  animation:ta-word .34s cubic-bezier(.2,.7,.3,1) forwards; }',
    '@keyframes ta-word { to { opacity:1; filter:blur(0); transform:none; } }',
    '.ta-bub .w { transform:translateY(3px); }',
    '@media (prefers-reduced-motion: reduce) { .ta-bub .w { animation:none; opacity:1; filter:none; transform:none; } }',
    '.ta-caret { display:inline-block; width:.55em; margin-left:1px;',
    '  animation:ta-blink 1s steps(1) infinite; color:var(--accent, #1a56a8); }',
    '@keyframes ta-blink { 50% { opacity:0; } }',
    /* starters */
    '.ta-chips { display:flex; flex-wrap:wrap; gap:.5rem; padding:.2rem 1.25rem .4rem; }',
    '.ta-chips button { font:inherit; font-size:.9rem; min-height:44px; padding:.5rem .95rem;',
    '  border-radius:999px; border:1px solid var(--rule, #e3e6e8);',
    '  background:var(--bg, #fff); color:var(--ink-2, #3d454d); cursor:pointer; text-align:left; }',
    '.ta-chips button:hover { border-color:var(--accent, #1a56a8); color:var(--accent, #1a56a8); }',
    /* composer */
    '.ta-row { display:flex; gap:.6rem; padding:.5rem 1.25rem .35rem; }',
    '.ta-row input { flex:1; min-height:52px; padding:.7rem 1rem; font:inherit; font-size:1.05rem;',
    '  border:1.5px solid var(--rule, #cfd4d8); border-radius:12px;',
    '  background:var(--bg, #fff); color:var(--ink, #14171a); }',
    '.ta-row input:focus { outline:none; border-color:var(--accent, #1a56a8);',
    '  box-shadow:0 0 0 3px color-mix(in srgb, var(--accent, #1a56a8) 18%, transparent); }',
    '.ta-row button { min-height:52px; min-width:84px; padding:.7rem 1.3rem;',
    '  font:inherit; font-weight:600; font-size:1.05rem; line-height:1;',
    '  border:none; border-radius:12px; cursor:pointer;',
    '  background:var(--accent, #1a56a8); color:var(--accent-ink, #fff); }',
    '.ta-row button:focus-visible { outline:3px solid var(--ink, #14171a); outline-offset:2px; }',
    '.ta-row button[disabled] { opacity:.55; cursor:default; }',
    '.ta-fine { margin:0; padding:.15rem 1.25rem calc(1rem + env(safe-area-inset-bottom, 0px));',
    '  color:var(--faint, #8b95a1); font-size:.78rem; line-height:1.5; }',
    '.ta-fine a { color:inherit; }',
    /* ---- the structured answer, drawn as components ---- */
    '.ta-msg.ai.rich .ta-bub { max-width:100%; background:var(--bg, #fff);',
    '  border-radius:4px 14px 14px 14px; padding:.85rem 1rem 1rem; }',
    '.ta-lead { margin:0; font-size:1.12rem; line-height:1.45; font-weight:600;',
    '  letter-spacing:-.011em; color:var(--ink, #14171a); }',
    '.ta-sec { margin:.9rem 0 0; }',
    '.ta-cards { display:grid; gap:.5rem; margin:.85rem 0 0;',
    '  grid-template-columns:repeat(auto-fit, minmax(132px, 1fr)); }',
    '.ta-card { text-align:left; padding:.6rem .7rem; border-radius:10px;',
    '  border:1px solid var(--rule, #e3e6e8); background:var(--surface, #f6f7f6);',
    '  font:inherit; color:inherit; }',
    'button.ta-card { cursor:pointer; }',
    'button.ta-card:hover { border-color:var(--accent, #1a56a8); }',
    'button.ta-card:focus-visible { outline:3px solid var(--accent, #1a56a8); outline-offset:2px; }',
    '.ta-card b { display:block; font-size:1.22rem; line-height:1.15;',
    '  letter-spacing:-.02em; font-variant-numeric:tabular-nums; }',
    '.ta-card span { display:block; margin-top:.2rem; font-size:.76rem;',
    '  text-transform:uppercase; letter-spacing:.05em; color:var(--muted, #5a6572); }',
    '.ta-cap { margin:.4rem 0 0; font-size:.78rem; color:var(--faint, #8b95a1); }',
    '.ta-lin { margin:.55rem 0 0; padding:.7rem .8rem; border-radius:10px;',
    '  border:1px solid var(--rule, #e3e6e8); background:var(--wash, #f4f5f4); }',
    '.ta-linhead { display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; }',
    '.ta-badge { font-size:.68rem; font-weight:700; letter-spacing:.08em;',
    '  padding:.2rem .45rem; border-radius:5px; background:var(--ink, #14171a);',
    '  color:var(--bg, #fff); }',
    '.ta-badge.v-verified { background:#1d6f42; color:#fff; }',
    '.ta-badge.v-unverified, .ta-badge.v-stale { background:#8a6a12; color:#fff; }',
    '.ta-badge.v-refused, .ta-badge.v-failed { background:#8a2a1e; color:#fff; }',
    '.ta-sum { margin:.4rem 0 0; font-size:1rem; font-variant-numeric:tabular-nums;',
    '  color:var(--ink, #14171a); }',
    '.ta-h { margin:.95rem 0 .2rem; font-size:.8rem; font-weight:700;',
    '  text-transform:uppercase; letter-spacing:.07em; color:var(--muted, #5a6572); }',
    '.ta-p { margin:.5rem 0 0; font-size:.98rem; line-height:1.6; color:var(--ink-2, #3d454d); }',
    '.ta-ul { margin:.5rem 0 0; padding-left:1.1rem; }',
    '.ta-ul li { margin:.28rem 0; font-size:.98rem; line-height:1.55; color:var(--ink-2, #3d454d); }',
    /* a table must scroll inside its own box; the sheet must never scroll sideways */
    '.ta-tw { margin:.7rem 0 0; overflow-x:auto; -webkit-overflow-scrolling:touch;',
    '  border:1px solid var(--rule, #e3e6e8); border-radius:10px; }',
    '.ta-tb { border-collapse:collapse; width:100%; font-size:.92rem; }',
    '.ta-tb th, .ta-tb td { padding:.5rem .7rem; text-align:left; white-space:nowrap;',
    '  border-bottom:1px solid var(--rule, #e3e6e8); }',
    '.ta-tb th { font-size:.74rem; text-transform:uppercase; letter-spacing:.05em;',
    '  color:var(--muted, #5a6572); background:var(--surface, #f6f7f6); }',
    '.ta-tb td:not(:first-child) { font-variant-numeric:tabular-nums; }',
    '.ta-tb tr:last-child td { border-bottom:none; }',
    '.ta-tb tr.me td { font-weight:600; background:var(--wash, #f4f5f4); }',
    '.ta-basis { margin:.35rem 0 0; font-size:.78rem; line-height:1.5; color:var(--faint, #8b95a1); }',
    '.ta-next { display:flex; flex-wrap:wrap; gap:.45rem; margin:.9rem 0 0;',
    '  padding-top:.8rem; border-top:1px solid var(--rule, #e3e6e8); }',
    '.ta-next button { font:inherit; font-size:.9rem; min-height:40px; padding:.4rem .85rem;',
    '  border-radius:999px; border:1px solid var(--rule, #e3e6e8); cursor:pointer;',
    '  background:var(--bg, #fff); color:var(--accent, #1a56a8); text-align:left; }',
    '.ta-next button:hover { background:var(--accent, #1a56a8); color:var(--accent-ink, #fff);',
    '  border-color:var(--accent, #1a56a8); }',
    '.ta-next button:focus-visible { outline:3px solid var(--ink, #14171a); outline-offset:2px; }',
    '.ta-foot { margin:.75rem 0 0; font-size:.78rem; line-height:1.55; color:var(--faint, #8b95a1); }',
    '.ta-foot a { color:inherit; }',
    '.ta-foot + .ta-foot { margin-top:.3rem; }',
    '.ta-sr { position:absolute; width:1px; height:1px; overflow:hidden;',
    '  clip:rect(0 0 0 0); clip-path:inset(50%); white-space:nowrap; }',
  '@media print { .ta-fab, .ta-wrap { display:none !important; } }',
  ].join('\n');

  var STYLE_ID = 'ta-style';

  function h(html) {
    var t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  var wrap, thread, input, sendBtn, chips, fab, sr, lastFocus, busy = false;

  function build() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = css;
    document.head.appendChild(style);

    fab = h('<button class="ta-fab" type="button" aria-haspopup="dialog">'
      + '<span class="ta-mk" aria-hidden="true"><i></i><i></i><i></i><i></i></span>'
      + 'Ask<span class="ta-long">&nbsp;a question</span></button>');
    fab.addEventListener('click', function () { open(); });
    document.body.appendChild(fab);

    wrap = h('<div class="ta-wrap" role="dialog" aria-modal="true" aria-labelledby="ta-title" hidden>'
      + '<div class="ta-back"></div>'
      + '<div class="ta-sheet">'
      + '  <div class="ta-head">'
      + '    <div><h2 id="ta-title">Ask about any Texas school district</h2>'
      + '    <p>Plain English. Answered from the state&rsquo;s own numbers.</p></div>'
      + '    <button class="ta-x" type="button" aria-label="Close">&times;</button>'
      + '  </div>'
      + '  <div class="ta-thread"></div>'
      + '  <div class="ta-sr" aria-live="polite"></div>'
      + '  <div class="ta-chips" aria-label="Example questions"></div>'
      + '  <div class="ta-row">'
      + '    <input type="text" maxlength="500" placeholder="Type your question&hellip;"'
      + '           aria-label="Ask a question about any Texas district">'
      + '    <button type="button">Ask</button>'
      + '  </div>'
      + '  <p class="ta-fine">AI answers from official TEA data and can make mistakes '
      + '&mdash; double-check important figures. Questions are kept on their own, with '
      + 'nothing that identifies you (<a href="/about#privacy">what we collect</a>).</p>'
      + '</div></div>');
    document.body.appendChild(wrap);

    thread = wrap.querySelector('.ta-thread');
    input = wrap.querySelector('.ta-row input');
    sendBtn = wrap.querySelector('.ta-row button');
    chips = wrap.querySelector('.ta-chips');
    sr = wrap.querySelector('.ta-sr');

    STARTERS.forEach(function (q) {
      var b = h('<button type="button"></button>');
      b.textContent = q;
      b.addEventListener('click', function () { input.value = q; submit(); });
      chips.appendChild(b);
    });

    wrap.querySelector('.ta-x').addEventListener('click', close);
    wrap.querySelector('.ta-back').addEventListener('click', close);
    sendBtn.addEventListener('click', submit);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.isComposing) submit();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && wrap.classList.contains('open')) close();
      /* a soft focus loop: Tab from the last control returns to the first,
         so keyboard readers cannot fall out of the dialog into the page */
      if (e.key === 'Tab' && wrap.classList.contains('open')) {
        var focusables = wrap.querySelectorAll('button, input, a[href]');
        var first = focusables[0], last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus();
        }
      }
    });
  }

  function open() {
    build();
    lastFocus = document.activeElement;
    wrap.hidden = false;
    /* two frames so the animation class change actually transitions */
    requestAnimationFrame(function () { wrap.classList.add('open'); });
    document.documentElement.style.overflow = 'hidden';
    setTimeout(function () { input.focus(); }, reduce ? 0 : 220);
  }

  function close() {
    if (!wrap) return;
    wrap.classList.remove('open');
    wrap.hidden = true;
    document.documentElement.style.overflow = '';
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function bubble(kind) {
    var m = kind === 'me'
      ? h('<div class="ta-msg me"><div class="ta-bub"></div></div>')
      : h('<div class="ta-msg ai"><span class="ta-av" aria-hidden="true">'
          + '<i></i><i></i><i></i><i></i></span><div class="ta-bub"></div></div>');
    thread.appendChild(m);
    thread.scrollTop = thread.scrollHeight;
    return m.querySelector('.ta-bub');
  }

  var token = 0;

  /* The district the reader is looking at, taken from the URL the page is
     already on. It is sent as context so the answer's figures and follow-ups
     are about the district on screen — it never reaches the model's query, so
     it cannot steer what the data says. */
  function districtNumber() {
    try {
      var d = new URLSearchParams(location.search).get('d');
      return /^\d{6}$/.test(d || '') ? d : null;
    } catch (e) { return null; }
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  /* Inline runs -> text nodes and <b>. This is the whole reason the model's
     prose is parsed server-side into {t, b} pairs: there is no branch here
     that can produce anything but a text node or a bold element. */
  function runsInto(node, runs) {
    (runs || []).forEach(function (r) {
      if (!r || !r.t) return;
      if (r.b) node.appendChild(el('b', null, r.t));
      else node.appendChild(document.createTextNode(r.t));
    });
    return node;
  }

  function tableOf(head, rows, selfRow) {
    var wrapEl = el('div', 'ta-tw');
    var t = el('table', 'ta-tb');
    if (head && head.length) {
      var thead = document.createElement('thead');
      var hr = document.createElement('tr');
      head.forEach(function (c) { hr.appendChild(el('th', null, String(c))); });
      thead.appendChild(hr);
      t.appendChild(thead);
    }
    var tb = document.createElement('tbody');
    if (selfRow) {
      var mr = el('tr', 'me');
      [selfRow.name, selfRow.students, selfRow.pct_poor, 'this district']
        .forEach(function (c) { mr.appendChild(el('td', null, String(c == null ? '' : c))); });
      tb.appendChild(mr);
    }
    (rows || []).forEach(function (row) {
      var tr = document.createElement('tr');
      (row || []).forEach(function (c) { tr.appendChild(el('td', null, String(c == null ? '' : c))); });
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    wrapEl.appendChild(t);
    return wrapEl;
  }

  /* "Why is this number this number." Opens the same evidence the district
     page shows — numerator, denominator, WHICH student count the denominator
     is, the formula, the publisher, and the publication gate's verdict — in
     place, so checking a figure never costs the reader their conversation. */
  function openLineage(num, metric, label, shown, after) {
    var old = after.parentNode.querySelector('.ta-lin');
    if (old) {
      var wasSame = old.getAttribute('data-metric') === metric;
      old.remove();
      if (wasSame) return;              /* clicking the same figure closes it */
    }
    var panel = el('div', 'ta-lin');
    panel.setAttribute('data-metric', metric);
    panel.appendChild(el('p', 'ta-basis', 'Checking ' + label + '…'));
    after.parentNode.insertBefore(panel, after.nextSibling);
    fetch('/district/' + encodeURIComponent(num) + '/lineage/'
          + encodeURIComponent(metric))
      .then(function (r) { return r.json(); })
      .then(function (ev) {
        panel.textContent = '';
        var g = ev.gate || {};
        var head = el('div', 'ta-linhead');
        head.appendChild(el('span', 'ta-badge v-' +
          String(g.verdict || 'unknown').toLowerCase(), g.verdict || 'UNKNOWN'));
        head.appendChild(el('strong', null, label));
        panel.appendChild(head);
        if (ev.numerator != null && ev.denominator != null) {
          panel.appendChild(el('p', 'ta-sum',
            Number(ev.numerator).toLocaleString() + ' ÷ '
            /* the result is written the way the card writes it — a reader
               comparing the two must not have to notice that one is $14,210
               and the other is 14210 */
            + Number(ev.denominator).toLocaleString() + ' = '
            + (shown != null ? shown : ev.value)));
        }
        if (ev.formula) panel.appendChild(el('p', 'ta-basis', ev.formula));
        if (ev.denominator_type) {
          panel.appendChild(el('p', 'ta-basis',
            'The denominator is ' + ev.denominator_type + '.'));
        }
        var foot = el('p', 'ta-basis',
          'Fiscal ' + (ev.fiscal_year || '?') + '. ' + (ev.source || ''));
        if (ev.source_url) {
          foot.appendChild(document.createTextNode(' '));
          var a = el('a', null, 'the original file');
          a.href = ev.source_url; a.target = '_blank'; a.rel = 'noopener';
          foot.appendChild(a);
        }
        panel.appendChild(foot);
        (g.why || []).forEach(function (w) {
          panel.appendChild(el('p', 'ta-basis', w));
        });
      })
      .catch(function () {
        panel.textContent = '';
        panel.appendChild(el('p', 'ta-basis',
          'The working for that figure could not be loaded just now.'));
      });
  }

  /* Everything below the lead: figures we computed, then the model's blocks,
     then the comparison we computed, then sources and the next questions. */
  function bodyOf(s) {
    var frag = document.createDocumentFragment();

    if (s.figures && s.figures.cards && s.figures.cards.length) {
      var grid = el('div', 'ta-cards');
      s.figures.cards.forEach(function (c) {
        /* A figure with a lineage metric is a button that opens its own
           calculation; one without is a plain box, because there is nothing
           to open. A control that looks clickable and is not is a small lie. */
        var box = el(c.metric ? 'button' : 'div', 'ta-card');
        if (c.metric) {
          box.type = 'button';
          box.title = 'See how this number is calculated';
          box.addEventListener('click', function () {
            openLineage(s.figures.district_number, c.metric, c.label, c.value, grid);
          });
        }
        box.appendChild(el('b', null, c.value));
        box.appendChild(el('span', null, c.label));
        grid.appendChild(box);
      });
      frag.appendChild(grid);
      frag.appendChild(el('p', 'ta-cap',
        (s.figures.name ? s.figures.name + ', ' : '') + 'fiscal '
        + s.figures.year + ' · ' + s.figures.note));
    }

    (s.blocks || []).forEach(function (b, i) {
      if (!b) return;
      if (b.type === 'heading') frag.appendChild(el('h3', 'ta-h', b.text || ''));
      else if (b.type === 'list') {
        var ul = el('ul', 'ta-ul');
        (b.items || []).forEach(function (item) {
          ul.appendChild(runsInto(el('li'), item));
        });
        frag.appendChild(ul);
      } else if (b.type === 'table') {
        frag.appendChild(tableOf(b.head, b.rows, null));
      } else if (b.type === 'paragraph') {
        /* the first paragraph is already the lead — do not print it twice */
        if (i === 0 && s.lead && sameStart(b.runs, s.lead)) return;
        frag.appendChild(runsInto(el('p', 'ta-p'), b.runs));
      }
    });

    if (s.comparison) {
      frag.appendChild(el('h3', 'ta-h', s.comparison.title));
      frag.appendChild(tableOf(s.comparison.head, s.comparison.rows, s.comparison.self));
      frag.appendChild(el('p', 'ta-basis', s.comparison.basis));
    }

    if (s.follow_ups && s.follow_ups.length) {
      var next = el('div', 'ta-next');
      next.setAttribute('aria-label', 'Suggested follow-up questions');
      s.follow_ups.forEach(function (f) {
        /* the chip shows the short label; asking sends the full question, so
           the engine receives something precise rather than two words */
        var b = el('button', null, f.label);
        b.type = 'button';
        b.title = f.question;
        b.addEventListener('click', function () {
          /* the same chip appears in the sheet and, via renderInto, on the
             landing page — opening first makes both cases identical */
          open();
          input.value = f.question;
          submit();
        });
        next.appendChild(b);
      });
      frag.appendChild(next);
    }

    (s.limitations || []).forEach(function (t) {
      frag.appendChild(el('p', 'ta-foot', t));
    });
    if (s.sources && s.sources.length) {
      var p = el('p', 'ta-foot');
      p.appendChild(document.createTextNode('Source: '));
      s.sources.forEach(function (src, i) {
        if (i) p.appendChild(document.createTextNode(' · '));
        var a = el('a', null, src.name);
        a.href = src.url;
        if (/^https?:/.test(src.url)) { a.target = '_blank'; a.rel = 'noopener'; }
        p.appendChild(a);
      });
      frag.appendChild(p);
    }
    return frag;
  }

  function sameStart(runs, leadText) {
    var t = (runs || []).map(function (r) { return r.t; }).join('');
    return t.slice(0, 40).trim() === String(leadText || '').slice(0, 40).trim();
  }

  /* Plain text for the screen reader and for the one-shot announcement: the
     components mutate as they arrive, and a live region reading fragments is
     worse than no live region. */
  function plainOf(s) {
    var parts = [s.lead || ''];
    (s.blocks || []).forEach(function (b) {
      if (b.type === 'table') {
        (b.rows || []).forEach(function (r) { parts.push(r.join(', ')); });
      } else if (b.type === 'list') {
        (b.items || []).forEach(function (i) {
          parts.push(i.map(function (r) { return r.t; }).join(''));
        });
      } else if (b.runs) {
        parts.push(b.runs.map(function (r) { return r.t; }).join(''));
      } else if (b.text) parts.push(b.text);
    });
    return parts.join(' ').replace(/\s+/g, ' ').trim();
  }

  function submit() {
    var q = (input.value || '').trim();
    if (q.length < 3 || busy) return;
    var mine = ++token;
    busy = true;
    sendBtn.disabled = true;
    input.value = '';
    chips.style.display = 'none';

    bubble('me').textContent = q;
    var bub = bubble('ai');
    bub.innerHTML = '<span class="ta-think">Reading the official data&hellip;</span>'
      + '<span class="ta-skel" aria-hidden="true"><i></i><i></i><i></i></span>';

    fetch('/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, district_number: districtNumber() }),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        return { status: r.status, body: body };
      });
    }).then(function (res) {
      if (mine !== token) return;
      var text;
      if (res.status === 429) {
        text = 'A lot of people are asking right now — please wait a minute '
          + 'and try again.';
      } else if (res.status >= 400 || !res.body || res.body.success === false) {
        text = (res.body && res.body.error)
          ? 'That one stumped the system: ' + res.body.error
          : 'The question service is resting right now. Please try again in '
            + 'a little while.';
      } else if (res.body.structured && res.body.structured.lead) {
        render(bub, res.body.structured, mine);
        return;
      } else {
        text = res.body.answer || 'No answer came back. Please try rephrasing.';
      }
      reveal(bub, text, mine);
    }).catch(function () {
      if (mine !== token) return;
      finish(bub, 'The question service could not be reached. Please check '
        + 'your connection and try again.');
    });
  }

  function finish(bub, text) {
    bub.textContent = text;
    /* announced ONCE, complete — the animated copy mutates word by word,
       which would make a screen reader stutter through fragments */
    if (sr) sr.textContent = text;
    busy = false;
    sendBtn.disabled = false;
    input.focus();
    thread.scrollTop = thread.scrollHeight;
  }

  /* The answer, written onto the screen one word at a time — each word fades
     and sharpens into place behind a blinking caret. It is the answer we
     already hold, presented for the eye; reduced motion gets it whole. */
  function writeWords(target, text, alive, done) {
    var words = String(text).split(/(\s+)/);
    var caret = el('span', 'ta-caret', '▌');
    target.textContent = '';
    target.appendChild(caret);
    /* long answers speed up so nothing ever takes more than ~6 seconds */
    var base = words.length > 260 ? 6 : words.length > 120 ? 11 : 18;
    var i = 0;
    var step = function () {
      if (!alive()) return;
      if (i >= words.length) {
        caret.remove();
        done();
        return;
      }
      var tok = words[i++];
      if (tok.trim() === '') {
        caret.insertAdjacentText('beforebegin', tok);
      } else {
        caret.insertAdjacentElement('beforebegin', el('span', 'w', tok));
      }
      if (thread) thread.scrollTop = thread.scrollHeight;
      setTimeout(step, /[.!?;:]$/.test(tok) ? base * 5 : base);
    };
    step();
  }

  function settle(text) {
    if (sr) sr.textContent = text;
    busy = false;
    sendBtn.disabled = false;
    input.focus();
    thread.scrollTop = thread.scrollHeight;
  }

  function reveal(bub, text, mine) {
    if (reduce) { finish(bub, text); return; }
    writeWords(bub, text, function () { return mine === token; },
               function () { settle(text); });
  }

  /* The structured answer, drawn. The LEAD writes itself onto the screen the
     way it always did; the components appear underneath once it lands, so the
     reader gets the conclusion first and the evidence a beat later — which is
     the order the answer is actually built in, not a loading trick.
     `alive` lets a caller cancel a stale render — the landing page runs its
     own question token and must be able to stop an older answer writing over
     a newer one. */
  function renderInto(target, s, alive, done) {
    alive = alive || function () { return true; };
    target.textContent = '';
    var leadEl = el('p', 'ta-lead');
    target.appendChild(leadEl);
    var rest = function () {
      if (!alive()) return;
      target.appendChild(bodyOf(s));
      if (done) done();
    };
    if (reduce) { leadEl.textContent = s.lead; rest(); return; }
    writeWords(leadEl, s.lead, alive, rest);
  }

  function render(bub, s, mine) {
    var plain = plainOf(s);
    bub.parentNode.classList.add('rich');
    renderInto(bub, s, function () { return mine === token; },
               function () { settle(plain); });
  }

  /* Every "Ask a question" link on every page opens the sheet IN PLACE.
     Capture phase, so this wins over the masthead's own click resolver and
     the browser's anchor jump; the href stays as a real fallback for the
     day this file fails to load. Modified clicks keep native behaviour. */
  document.addEventListener('click', function (e) {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
    var a = e.target.closest && e.target.closest(
      'a[href="/#ask-section"], .finder-ask a[href="#ask-section"]');
    if (!a) return;
    e.preventDefault();
    e.stopPropagation();
    var dd = a.closest('details');
    if (dd) dd.open = false;
    open();
  }, true);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }

  /* `render` is the whole point of exporting anything: the landing page has
     its own inline answer box, and before this it had its own copy of the
     answer renderer too. Two renderers means one of them is always the older
     one — the raw-Markdown bug lived in exactly that gap. One implementation,
     two places it can draw. */
  window.TISDAsk = {
    open: open,
    close: close,
    render: function (target, structured, alive) {
      build();
      renderInto(target, structured, alive, null);
    },
  };
}());
