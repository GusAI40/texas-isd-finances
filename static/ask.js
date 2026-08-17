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
 * - Answers are TEXT. They are written with textContent into spans, never
 *   innerHTML — a model's output must not be able to inject markup.
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
      body: JSON.stringify({ question: q }),
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
  function reveal(bub, text, mine) {
    if (reduce) { finish(bub, text); return; }
    var words = text.split(/(\s+)/);
    bub.innerHTML = '<span class="ta-caret">▌</span>';
    var caret = bub.querySelector('.ta-caret');
    /* long answers speed up so nothing ever takes more than ~6 seconds */
    var base = words.length > 260 ? 6 : words.length > 120 ? 11 : 18;
    var i = 0;
    var step = function () {
      if (mine !== token) return;
      if (i >= words.length) {
        caret.remove();
        if (sr) sr.textContent = text;
        busy = false;
        sendBtn.disabled = false;
        input.focus();
        return;
      }
      var tok = words[i++];
      if (tok.trim() === '') {
        caret.insertAdjacentText('beforebegin', tok);
      } else {
        var s = document.createElement('span');
        s.className = 'w';
        s.textContent = tok;
        caret.insertAdjacentElement('beforebegin', s);
      }
      thread.scrollTop = thread.scrollHeight;
      setTimeout(step, /[.!?;:]$/.test(tok) ? base * 5 : base);
    };
    step();
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

  window.TISDAsk = { open: open, close: close };
}());
