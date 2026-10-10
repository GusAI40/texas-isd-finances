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
    '.ta-head .ta-scope { display:inline-flex; margin-top:.35rem; padding:.16rem .45rem; border-radius:999px; background:var(--wash,#f4f5f4); color:var(--ink-2,#3d454d); font-size:.875rem; font-weight:700; }',
    '.ta-head p { margin:.15rem 0 0; color:var(--muted, #5a6572); font-size:.92rem; }',
    '.ta-x { margin-left:auto; flex:none; width:44px; height:44px; border-radius:10px;',
    '  border:1px solid var(--rule, #e3e6e8); background:none; color:var(--muted, #5a6572);',
    '  font-size:1.35rem; line-height:1; cursor:pointer; }',
    '.ta-x:hover { color:var(--ink, #14171a); background:var(--wash, #f4f5f4); }',
    '.ta-x:focus-visible { outline:3px solid var(--accent, #1a56a8); outline-offset:2px; }',
    /* thread */
    '.ta-thread { flex:1; overflow-y:auto; padding:.6rem 1.25rem; min-height:4rem;',
    '  overscroll-behavior:contain; scroll-behavior:smooth; }',
    '.ta-thread:empty { flex:0; min-height:0; padding-top:0; padding-bottom:0; }',
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
    '.ta-think { color:var(--muted, #5a6572); font-size:.875rem; }',
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
    '@media (max-width:430px) { .ta-chips { flex-wrap:nowrap; overflow-x:auto; overscroll-behavior-x:contain; }.ta-chips button { flex:0 0 auto; max-width:15rem; } }',
    '@media (max-width:240px) { .ta-example-flow { grid-template-columns:1fr; } .ta-example-stage { min-width:0; overflow-wrap:anywhere; } .ta-row { flex-direction:column; } .ta-row input,.ta-row button { width:100%; min-width:0; box-sizing:border-box; } }',
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
    '.ta-actions { display:flex; gap:.5rem; padding:0 1.25rem .4rem; }',
    '.ta-actions[hidden] { display:none; }',
    '.ta-actions button { min-height:44px; padding:.4rem .75rem; border-radius:9px; font:600 .9rem/1 system-ui,sans-serif; cursor:pointer; border:1px solid var(--rule,#cfd4d8); background:var(--bg,#fff); color:var(--ink,#14171a); }',
    '.ta-actions .ta-stop { color:var(--accent,#1a56a8); border-color:var(--accent,#1a56a8); }',
    '.ta-empty { margin:.15rem 1.25rem .5rem; padding:.65rem; border:1px solid var(--rule,#e3e6e8); border-radius:12px; background:var(--surface,#f6f7f6); color:var(--ink-2,#3d454d); font-size:.875rem; line-height:1.35; }',
    '.ta-example-head { display:flex; justify-content:space-between; gap:.6rem; align-items:baseline; margin-bottom:.5rem; }',
    '.ta-example-head b { color:var(--ink,#14171a); font-size:.9rem; }',
    '.ta-example-head span { font-size:.875rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; color:var(--accent,#1a56a8); }',
    '.ta-example-q { margin:0 0 .55rem; padding:.38rem .5rem; border-left:3px solid var(--accent,#1a56a8); background:var(--bg,#fff); color:var(--ink,#14171a); font-weight:700; }',
    '.ta-example-flow { display:grid; grid-template-columns:minmax(0,1.1fr) minmax(4.8rem,.52fr) minmax(0,1.1fr); gap:.7rem; align-items:stretch; }',
    '.ta-example-stage { position:relative; min-width:0; padding:.45rem; border:1px solid var(--rule,#e3e6e8); border-radius:8px; background:var(--bg,#fff); }',
    '.ta-example-stage:not(:last-child)::after { content:""; position:absolute; left:100%; top:50%; width:.75rem; border-top:2px solid var(--accent,#1a56a8); }',
    '.ta-example-stage > b { display:block; margin-bottom:.3rem; font-size:.875rem; color:var(--ink,#14171a); }',
    '.ta-example-records { display:grid; gap:3px; } .ta-example-records i { display:block; height:.42rem; width:var(--w); border-radius:2px; background:var(--accent,#1a56a8); opacity:var(--o); }',
    '.ta-example-codes { display:flex; justify-content:space-between; gap:.2rem; margin-top:.25rem; font-size:.875rem; font-variant-numeric:tabular-nums; }',
    '.ta-example-match { display:grid; place-items:center; text-align:center; } .ta-example-match strong { padding:.28rem; border:2px solid var(--accent,#1a56a8); border-radius:6px; color:var(--accent,#1a56a8); font-size:.9rem; letter-spacing:.05em; }',
    '.ta-example-match small { font-size:.875rem; }',
    '.ta-example-stack { display:flex; height:2.15rem; overflow:hidden; border-radius:5px; } .ta-example-stack i { display:block; min-width:2px; }',
    '.ta-example-stack .c { width:32.9177%; background:#174f9b; }.ta-example-stack .b { width:23.0873%; background:#4c73a4; }.ta-example-stack .d { width:15.0691%; background:#334e68; }.ta-example-stack .o { width:28.9259%; background:#376fba; }',
    '.ta-example-answer strong { display:block; margin-top:.28rem; color:var(--ink,#14171a); font-size:.875rem; font-variant-numeric:tabular-nums; }',
    '@media (max-width:430px) { .ta-example-flow { grid-template-columns:minmax(0,1.05fr) minmax(4.25rem,.58fr) minmax(0,1.08fr); gap:.5rem; }.ta-example-stage { padding:.35rem; }.ta-example-stage:not(:last-child)::after { width:.55rem; }.ta-example-codes span:not(:first-child) { display:none; } }',
    '.ta-fine { margin:0; padding:.15rem 1.25rem calc(1rem + env(safe-area-inset-bottom, 0px));',
    '  color:var(--ink-2, #52606d); font-size:.875rem; line-height:1.5; }',
    '.ta-fine a { color:var(--accent, #1a56a8); }',
    /* ---- the structured answer, drawn as components ---- */
    '.ta-msg.ai.rich .ta-bub { max-width:100%; display:flex; flex-direction:column; background:var(--bg, #fff);',
    '  border-radius:4px 14px 14px 14px; padding:.85rem 1rem 1rem; }',
    '.ta-lead { margin:0; font-size:1.12rem; line-height:1.45; font-weight:600;',
    '  letter-spacing:-.011em; color:var(--ink, #14171a); }',
    /* The lead is the model's whole opening paragraph, and a four-sentence
       paragraph at heading weight is a wall. Long leads step down; nothing is
       split or hidden, only sized to what it is. */
    '.ta-lead.long { font-size:1.02rem; font-weight:500; letter-spacing:0; }',
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
    '.ta-card span { display:block; margin-top:.2rem; font-size:.875rem;',
    '  text-transform:uppercase; letter-spacing:.05em; color:var(--muted, #5a6572); }',
    '.ta-cap { margin:.4rem 0 0; font-size:.875rem; color:var(--ink-2, #52606d); }',
    '.ta-lin { margin:.55rem 0 0; padding:.7rem .8rem; border-radius:10px;',
    '  border:1px solid var(--rule, #e3e6e8); background:var(--wash, #f4f5f4); }',
    '.ta-linhead { display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; }',
    '.ta-badge { font-size:.875rem; font-weight:700; letter-spacing:.08em;',
    '  padding:.2rem .45rem; border-radius:5px; background:var(--ink, #14171a);',
    '  color:var(--bg, #fff); }',
    '.ta-badge.v-verified { background:#1d6f42; color:#fff; }',
    '.ta-badge.v-unverified, .ta-badge.v-stale { background:#8a6a12; color:#fff; }',
    '.ta-badge.v-refused, .ta-badge.v-failed { background:#8a2a1e; color:#fff; }',
    '.ta-sum { margin:.4rem 0 0; font-size:1rem; font-variant-numeric:tabular-nums;',
    '  color:var(--ink, #14171a); }',
    '.ta-h { margin:.95rem 0 .2rem; font-size:.875rem; font-weight:700;',
    '  text-transform:uppercase; letter-spacing:.07em; color:var(--muted, #5a6572); }',
    '.ta-p { margin:.5rem 0 0; font-size:.98rem; line-height:1.6; color:var(--ink-2, #3d454d); }',
    '.ta-ul { margin:.5rem 0 0; padding-left:1.1rem; }',
    '.ta-ul li { margin:.28rem 0; font-size:.98rem; line-height:1.55; color:var(--ink-2, #3d454d); }',
    /* a table must scroll inside its own box; the sheet must never scroll sideways */
    '.ta-tw { margin:.7rem 0 0; overflow-x:auto; -webkit-overflow-scrolling:touch;',
    '  border:1px solid var(--rule, #e3e6e8); border-radius:10px; }',
    '.ta-tw.tall { max-height:340px; overflow-y:auto; }',
    '.ta-tw.tall .ta-tb th { position:sticky; top:0; z-index:1; }',
    '.ta-tb { border-collapse:collapse; width:100%; font-size:.92rem; }',
    '.ta-tb th, .ta-tb td { padding:.5rem .7rem; text-align:left; white-space:nowrap;',
    '  border-bottom:1px solid var(--rule, #e3e6e8); }',
    '.ta-tb th { font-size:.875rem; text-transform:uppercase; letter-spacing:.05em;',
    '  color:var(--muted, #5a6572); background:var(--surface, #f6f7f6); }',
    '.ta-tb td:not(:first-child) { font-variant-numeric:tabular-nums; }',
    '.ta-tb tr:last-child td { border-bottom:none; }',
    '.ta-tb tr.me td { font-weight:600; background:var(--wash, #f4f5f4); }',
    '.ta-basis { margin:.35rem 0 0; font-size:.875rem; line-height:1.5; color:var(--faint, #8b95a1); }',
    '.ta-chart { margin:.8rem 0 0; padding:1rem; border:1px solid var(--accent,#1a56a8); border-radius:12px; background:var(--surface, #f6f7f6); }',
    '.ta-bub .ta-chart { order:-4; } .ta-bub .ta-lead { order:-3; } .ta-bub .ta-context { order:-2; } .ta-bub .ta-answer-source { order:-1; }',
    '.ta-chart-title { display:flex; justify-content:space-between; gap:.7rem; margin:0 0 .7rem; font-size:.95rem; font-weight:700; color:var(--ink-2, #3d454d); }',
    '.ta-chart-title span { font-size:.875rem; font-weight:600; color:var(--muted,#5a6572); }',
    '.ta-chart-row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:.3rem .7rem; align-items:center; margin:.62rem 0; }',
    '.ta-chart-row strong { font-size:.9rem; line-height:1.25; color:var(--ink,#14171a); }',
    '.ta-chart-row span { font-size:.88rem; font-variant-numeric:tabular-nums; color:var(--ink,#14171a); }',
    '.ta-chart-track { grid-column:1 / -1; height:1.55rem; overflow:hidden; border-radius:5px; background:var(--rule,#e3e6e8); }',
    '.ta-chart-bar { display:block; height:100%; min-width:2px; border-radius:inherit; background:var(--accent,#1a56a8); }',
    '.ta-chart-row:nth-of-type(3n+2) .ta-chart-bar { opacity:.82; }.ta-chart-row:nth-of-type(3n+3) .ta-chart-bar { opacity:.66; }',
    '.ta-chart-record { display:grid; grid-template-columns:auto minmax(0,1fr); gap:.15rem .55rem; margin:.8rem 0 0; padding:.55rem .65rem; border-top:2px solid var(--accent,#1a56a8); background:var(--bg,#fff); font-size:.875rem; line-height:1.35; }',
    '.ta-chart-record span { color:var(--muted,#5a6572); font-weight:700; text-transform:uppercase; letter-spacing:.05em; }.ta-chart-record strong { color:var(--ink,#14171a); overflow-wrap:anywhere; }.ta-chart-record small { grid-column:2; color:var(--ink-2,#3d454d); font-size:.875rem; }',
    '@media (max-width:360px) { .ta-chart-title { display:block; }.ta-chart-title span { display:block; margin-top:.2rem; }.ta-chart-row { grid-template-columns:1fr; }.ta-chart-row span,.ta-chart-track { grid-column:1; }.ta-chart-record { grid-template-columns:1fr; }.ta-chart-record small { grid-column:1; } }',
    '.ta-evidence, .ta-support { margin:.8rem 0 0; font-size:.9rem; color:var(--ink-2,#3d454d); }',
    '.ta-evidence summary, .ta-support summary { display:flex; align-items:center; min-height:44px; cursor:pointer; color:var(--accent,#1a56a8); font-weight:600; }',
    '.ta-support p { margin:.55rem 0 0; }',
    '.ta-context, .ta-answer-source, .ta-limit { margin:.55rem 0 0; font-size:.875rem; line-height:1.45; color:var(--ink-2,#3d454d); }',
    '.ta-answer-source a { color:var(--accent,#1a56a8); }',
    '.ta-next { display:flex; flex-wrap:wrap; gap:.45rem; margin:.9rem 0 0;',
    '  padding-top:.8rem; border-top:1px solid var(--rule, #e3e6e8); }',
    '.ta-next button { font:inherit; font-size:.9rem; min-height:44px; padding:.4rem .85rem;',
    '  border-radius:999px; border:1px solid var(--rule, #e3e6e8); cursor:pointer;',
    '  background:var(--bg, #fff); color:var(--accent, #1a56a8); text-align:left; }',
    '.ta-next button:hover { background:var(--accent, #1a56a8); color:var(--accent-ink, #fff);',
    '  border-color:var(--accent, #1a56a8); }',
    '.ta-next button:focus-visible { outline:3px solid var(--ink, #14171a); outline-offset:2px; }',
    /* Keep this after the 430px example layout so the 200% reflow viewport
       really becomes one column instead of restoring the three-stage grid. */
    '@media (max-width:240px) { .ta-empty .ta-example-flow { grid-template-columns:minmax(0,1fr); } .ta-empty .ta-example-stage { min-width:0; overflow-wrap:anywhere; } .ta-empty .ta-example-stage:not(:last-child)::after { left:50%; top:100%; width:0; height:.7rem; border-top:0; border-left:2px solid var(--accent,#1a56a8); } }',
    '.ta-foot { margin:.75rem 0 0; font-size:.875rem; line-height:1.55; color:var(--ink-2, #52606d); }',
    '.ta-foot a { color:var(--accent, #1a56a8); }',
    '.ta-foot + .ta-foot { margin-top:.3rem; }',
    /* ---- beta chip + feedback ---- */
    '.m-beta { display:inline-block; margin-left:.45rem; padding:.1rem .4rem;',
    '  border-radius:5px; border:1px solid var(--rule, #e3e6e8); cursor:pointer;',
    '  font:inherit; font-size:.62rem; font-weight:700; letter-spacing:.07em;',
    '  text-transform:uppercase; vertical-align:middle;',
    '  background:var(--accent, #1a56a8); color:var(--accent-ink, #fff); }',
    '.m-beta:hover { filter:brightness(1.12); }',
    '.m-beta:focus-visible { outline:3px solid var(--ink, #14171a); outline-offset:2px; }',
    '.tf-wrap { position:fixed; inset:0; z-index:210; display:none; }',
    '.tf-wrap.open { display:block; }',
    '.tf-back { position:absolute; inset:0; background:rgba(10,12,14,.45); }',
    '.tf-box { position:absolute; left:50%; bottom:0; transform:translateX(-50%);',
    '  width:min(560px, 100%); max-height:92vh; overflow:auto;',
    '  background:var(--bg, #fff); color:var(--ink, #14171a);',
    '  border:1px solid var(--rule, #e3e6e8); border-radius:16px 16px 0 0;',
    '  padding:1.15rem 1.25rem calc(1.25rem + env(safe-area-inset-bottom, 0px));',
    '  font:16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }',
    '@media (min-width: 720px) { .tf-box { bottom:auto; top:50%;',
    '  transform:translate(-50%,-50%); border-radius:16px; } }',
    '.tf-box h2 { margin:0 0 .3rem; font-size:1.15rem; letter-spacing:-.01em; }',
    '.tf-box p { margin:.35rem 0 0; font-size:.92rem; color:var(--muted, #5a6572); }',
    '.tf-box textarea { width:100%; margin-top:.8rem; min-height:110px; padding:.7rem .85rem;',
    '  font:inherit; font-size:1rem; border-radius:12px; resize:vertical;',
    '  border:1.5px solid var(--rule, #cfd4d8); background:var(--bg, #fff);',
    '  color:var(--ink, #14171a); }',
    '.tf-box input { width:100%; margin-top:.6rem; min-height:48px; padding:.6rem .85rem;',
    '  font:inherit; font-size:1rem; border-radius:12px;',
    '  border:1.5px solid var(--rule, #cfd4d8); background:var(--bg, #fff);',
    '  color:var(--ink, #14171a); }',
    '.tf-box textarea:focus, .tf-box input:focus { outline:none;',
    '  border-color:var(--accent, #1a56a8); }',
    '.tf-row { display:flex; gap:.6rem; margin-top:.9rem; align-items:center; }',
    '.tf-row button { min-height:48px; padding:.6rem 1.2rem; font:inherit;',
    '  font-weight:600; border-radius:12px; border:none; cursor:pointer;',
    '  background:var(--accent, #1a56a8); color:var(--accent-ink, #fff); }',
    '.tf-row button.ghost { background:none; color:var(--muted, #5a6572);',
    '  border:1px solid var(--rule, #e3e6e8); }',
    '.tf-row button[disabled] { opacity:.55; cursor:default; }',
    '.tf-fine { margin-top:.85rem; font-size:.875rem; line-height:1.5;',
    '  color:var(--faint, #8b95a1); }',
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
  var controller = null, requestTimer = null, focusTimer = null, retryState = null, activeRequest = null, activeBubble = null;
  var previousOverflow = '', focusSerial = 0;

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
      + '    <div><h2 id="ta-title">Texas school-finance workspace</h2>'
      + '    <p>Plain English answers from official records.</p><span class="ta-scope">Texas public records</span></div>'
      + '    <button class="ta-x" type="button" aria-label="Close">&times;</button>'
      + '  </div>'
      + '  <div class="ta-thread"></div>'
      + '  <div class="ta-empty">'
      + '    <div class="ta-example-head"><b>Question to source to answer</b><span>Recorded example</span></div>'
      + '    <p class="ta-example-q">How much went to Dallas classrooms?</p>'
      + '    <div class="ta-example-flow" aria-label="Example workflow from Dallas question through TEA records to a sourced quantitative answer.">'
      + '      <div class="ta-example-stage"><b>TEA PEIMS &middot; FY 2025 all funds</b><div class="ta-example-records" role="img" aria-label="Separate record groups: classroom 32.9 percent, construction 23.1 percent, debt 15.1 percent, other combined 28.9 percent."><i style="--w:100%;--o:1"></i><i style="--w:70.1%;--o:.82"></i><i style="--w:45.8%;--o:.66"></i><i style="--w:87.9%;--o:.74"></i></div><div class="ta-example-codes"><span>11+12+13</span><span>6600</span><span>6500</span></div></div>'
      + '      <div class="ta-example-stage ta-example-match"><b>District match</b><strong>057905</strong><small>Dallas ISD</small></div>'
      + '      <div class="ta-example-stage ta-example-answer"><b>Sourced answer</b><div class="ta-example-stack" role="img" aria-label="Dallas spending shares: classroom 32.9 percent, construction 23.1 percent, debt 15.1 percent, other combined 28.9 percent."><i class="c"></i><i class="b"></i><i class="d"></i><i class="o"></i></div><strong>Classroom: $1.093B &middot; 32.9%</strong></div>'
      + '    </div>'
      + '  </div>'
      + '  <div class="ta-sr" aria-live="polite"></div>'
      + '  <div class="ta-chips" aria-label="Example questions"></div>'
      + '  <div class="ta-row">'
      + '    <input type="text" maxlength="500" placeholder="Type your question&hellip;"'
      + '           aria-label="Ask a question about any Texas district">'
      + '    <button type="button">Ask</button>'
      + '  </div>'
      + '  <div class="ta-actions" hidden><button class="ta-stop" type="button">Stop</button><button class="ta-retry" type="button" hidden>Try again</button></div>'
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

    wrap.querySelector('.ta-stop').addEventListener('click', stopRequest);
    wrap.querySelector('.ta-retry').addEventListener('click', function () {
      if (retryState) submit(retryState.question, retryState.districtNumber);
    });

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
        var focusables = Array.prototype.filter.call(wrap.querySelectorAll('button, input, a[href]'), function (node) {
          return !node.disabled && !node.hidden && node.offsetParent !== null;
        });
        if (!focusables.length) return;
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
    if (wrap.classList.contains('open') && !wrap.hidden) return;
    lastFocus = document.activeElement;
    wrap.hidden = false;
    /* two frames so the animation class change actually transitions */
    requestAnimationFrame(function () { wrap.classList.add('open'); });
    previousOverflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = 'hidden';
    var serial = ++focusSerial;
    clearTimeout(focusTimer);
    focusTimer = setTimeout(function () {
      if (serial === focusSerial && !wrap.hidden && document.activeElement === lastFocus) input.focus();
    }, reduce ? 0 : 220);
  }

  function close() {
    if (!wrap) return;
    stopRequest(true);
    ++focusSerial;
    clearTimeout(focusTimer);
    wrap.classList.remove('open');
    wrap.hidden = true;
    document.documentElement.style.overflow = previousOverflow;
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
  /* One conversation id per chat sitting, minted here and sent with every
     turn so the turns can be read back in order. It is opaque and carries no
     identity: what attaches a person to it is a `question` row in the server's
     own event stream, which exists only for someone who arrived on a token we
     mailed. An anonymous visitor's conversation stays anonymous. */
  var convo = null, turnNo = 0;
  /* Set when a suggestion chip is clicked and cleared the moment it is sent,
     so a question the reader typed themselves is never credited to a chip. */
  var pendingFollowup = null;

  function conversationId() {
    if (!convo) {
      convo = 'c' + Date.now().toString(36)
        + Math.floor(Math.random() * 1e9).toString(36);
    }
    return convo;
  }

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
    /* Tables can be wider than the phone-sized answer sheet. The wrapper is a
       named keyboard region so arrow-key users can reach the same columns as
       touch and pointer users without changing or hiding any values. */
    wrapEl.tabIndex = 0;
    wrapEl.setAttribute('role', 'region');
    wrapEl.setAttribute('aria-label', 'Scrollable answer table');
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
    /* A model told to keep lists short can still return two hundred rows, and
       one long table would push everything below it — the sources, the
       follow-ups — out of reach. The table gets its own scrollable height and
       says how many rows it has. Nothing is dropped: truncating rows would
       hide data, which is the one thing worse than a long table. */
    if ((rows || []).length > 12) {
      wrapEl.classList.add('tall');
      var cap = el('p', 'ta-cap', rows.length.toLocaleString() + ' rows — scroll the table');
      var holder = el('div');
      holder.appendChild(wrapEl);
      holder.appendChild(cap);
      return holder;
    }
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

  function moneySeries(head, rows) {
    if (!Array.isArray(head) || head.length !== 2 || !Array.isArray(rows) || rows.length < 2) return null;
    var labelHead = String(head[0] || '').trim().toLowerCase();
    var moneyHead = String(head[1] || '').trim().toLowerCase();
    if (!/^(spending\s+)?(category|item|function|type|program)$/.test(labelHead)
        || !/^(dollars?|usd|amount(?:\s*\(\s*usd\s*\))?)$/.test(moneyHead)) return null;
    var values = [];
    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      if (!Array.isArray(row) || row.length !== 2) return null;
      var label = String(row[0] == null ? '' : row[0]).trim();
      var text = String(row[1] == null ? '' : row[1]).trim();
      if (/^(total|total spending|grand total)$/i.test(label)) continue;
      if (!label || !/^\$(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d{2})?$/.test(text)) return null;
      var value = Number(text.replace(/[$,]/g, ''));
      if (!isFinite(value) || value <= 0) return null;
      values.push({ label: label, shown: text, value: value });
    }
    return values.length > 1 ? values : null;
  }

  function chartOf(head, rows, s) {
    if (!s || !s.figures || !s.figures.name || !s.figures.year || !s.figures.note
        || !s.sources || !s.sources.length) return null;
    var values = moneySeries(head, rows);
    if (!values) return null;
    var max = Math.max.apply(null, values.map(function (v) { return v.value; }));
    var chart = el('section', 'ta-chart');
    chart.setAttribute('aria-label', 'Reported dollar comparison; bars are scaled to the largest displayed amount.');
    var title = el('p', 'ta-chart-title');
    title.appendChild(el('strong', null, 'Reported dollar comparison'));
    title.appendChild(el('span', null, 'Each bar uses the largest value as 100%'));
    chart.appendChild(title);
    values.forEach(function (v) {
      var row = el('div', 'ta-chart-row');
      row.appendChild(el('strong', null, v.label));
      row.appendChild(el('span', null, v.shown));
      var track = el('div', 'ta-chart-track');
      var bar = el('i', 'ta-chart-bar');
      bar.setAttribute('data-value', String(v.value));
      bar.style.width = (v.value / max * 100) + '%';
      track.appendChild(bar); row.appendChild(track); chart.appendChild(row);
    });
    var record = el('div', 'ta-chart-record');
    record.appendChild(el('span', null, 'Official record'));
    record.appendChild(el('strong', null, String(s.sources[0].name || 'Linked source')));
    record.appendChild(el('small', null, s.figures.name + ' / Fiscal ' + s.figures.year
      + ' / ' + s.figures.note));
    chart.appendChild(record);
    return chart;
  }

  /* Everything below the lead: figures we computed, then the model's blocks,
     then the comparison we computed, then sources and the next questions. */
  function bodyOf(s, fullLead) {
    var frag = document.createDocumentFragment();
    var support = el('details', 'ta-support');
    support.appendChild(el('summary', null, 'Sources, context, and full answer'));
    if (fullLead) support.appendChild(el('p', null, fullLead));
    if (s.sources && s.sources.length) {
      var earlySource = el('p', 'ta-answer-source');
      earlySource.appendChild(document.createTextNode('Source: '));
      s.sources.forEach(function (src, i) {
        if (i) earlySource.appendChild(document.createTextNode(' · '));
        var earlyLink = el('a', null, src.name);
        earlyLink.href = src.url;
        if (/^https?:/.test(src.url)) { earlyLink.target = '_blank'; earlyLink.rel = 'noopener'; }
        earlySource.appendChild(earlyLink);
      });
      frag.appendChild(earlySource);
    }
    (s.limitations || []).forEach(function (t) {
      frag.appendChild(el('p', 'ta-limit', t));
    });
    if (s.figures && s.figures.name && s.figures.year && s.figures.note) {
      frag.appendChild(el('p', 'ta-context', s.figures.name + ' · Fiscal '
        + s.figures.year + ' · ' + s.figures.note));
    }

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
      support.appendChild(grid);
    }

    (s.blocks || []).forEach(function (b) {
      if (!b) return;
      if (b.type === 'heading') support.appendChild(el('h3', 'ta-h', b.text || ''));
      else if (b.type === 'list') {
        var ul = el('ul', 'ta-ul');
        (b.items || []).forEach(function (item) {
          ul.appendChild(runsInto(el('li'), item));
        });
        support.appendChild(ul);
      } else if (b.type === 'table') {
        var chart = chartOf(b.head, b.rows, s);
        if (chart) {
          frag.appendChild(chart);
          var evidence = el('details', 'ta-evidence');
          evidence.appendChild(el('summary', null, 'View full table - ' + b.rows.length + ' rows'));
          evidence.appendChild(tableOf(b.head, b.rows, null));
          frag.appendChild(evidence);
        } else {
          frag.appendChild(tableOf(b.head, b.rows, null));
        }
      } else if (b.type === 'paragraph') {
        support.appendChild(runsInto(el('p', 'ta-p'), b.runs));
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
          pendingFollowup = f.label;
          input.value = f.question;
          submit();
        });
        next.appendChild(b);
      });
      frag.appendChild(next);
    }

    (s.limitations || []).forEach(function (t) {
      support.appendChild(el('p', 'ta-foot', t));
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
      support.appendChild(p);
    }
    frag.appendChild(support);
    return frag;
  }

  /* Plain text for the screen reader's one-shot announcement: the components
     mutate as they arrive, and a live region reading fragments is worse than
     no live region.

     It announces the figures and the ranked table too. Reading only the
     model's prose would leave a screen-reader user hearing the part of the
     answer this project vouches for LEAST while the numbers it computed and
     checked stayed silent. */
  function plainOf(s) {
    var parts = [s.lead || ''];
    if (s.figures) {
      parts.push('Filed figures for ' + (s.figures.name || 'this district')
        + ', fiscal ' + s.figures.year + ':');
      (s.figures.cards || []).forEach(function (c) {
        parts.push(c.label + ' ' + c.value + '.');
      });
    }
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
    if (s.comparison) {
      parts.push(s.comparison.title + ':');
      (s.comparison.rows || []).forEach(function (r) { parts.push(r.join(', ')); });
      parts.push(s.comparison.basis);
    }
    return parts.join(' ').replace(/\s+/g, ' ').trim();
  }

  function setRequestControls(active) {
    var actions = wrap && wrap.querySelector('.ta-actions');
    var stop = wrap && wrap.querySelector('.ta-stop');
    var retry = wrap && wrap.querySelector('.ta-retry');
    if (actions) actions.hidden = !active && !retryState;
    if (stop) stop.hidden = !active;
    if (retry) retry.hidden = active || !retryState;
  }

  function endRequest() {
    clearTimeout(requestTimer); requestTimer = null; controller = null;
    activeRequest = null; activeBubble = null;
    busy = false;
    if (sendBtn) sendBtn.disabled = false;
    setRequestControls(false);
  }

  function stopRequest(closing) {
    if (!busy) return;
    ++token;
    if (controller) controller.abort();
    retryState = activeRequest;
    if (activeBubble) activeBubble.textContent = closing
      ? 'Request canceled.' : 'Stopped. You can try that question again.';
    endRequest();
  }

  function submit(question, requestedDistrict) {
    if (question && typeof question !== 'string') question = null;
    var q = String(question == null ? input.value : question).trim();
    if (q.length < 3 || busy) return;
    var mine = ++token;
    busy = true;
    sendBtn.disabled = true;
    input.value = '';
    chips.style.display = 'none';
    wrap.querySelector('.ta-empty').hidden = true;
    retryState = null;
    setRequestControls(true);

    bubble('me').textContent = q;
    var bub = bubble('ai');
    activeBubble = bub;
    bub.innerHTML = '<span class="ta-think">Reading the official data&hellip;</span>'
      + '<span class="ta-skel" aria-hidden="true"><i></i><i></i><i></i></span>';

    var followup = pendingFollowup;
    pendingFollowup = null; // consume at request start, including aborted requests
    var district = requestedDistrict || districtNumber();
    activeRequest = { question: q, districtNumber: district };
    controller = new AbortController();
    requestTimer = setTimeout(function () {
      if (mine === token && controller) controller.abort();
    }, 45000);
    fetch('/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify({
        question: q,
        district_number: district,
        conversation_id: conversationId(),
        turn: ++turnNo,
        /* which chip produced this question, if any — the only way to find
           out whether the suggestions help or merely decorate */
        followup_label: followup,
      }),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) {
        return { status: r.status, body: body };
      });
    }).then(function (res) {
      if (mine !== token) return;
      endRequest();
      var text;
      if (res.status === 429) {
        text = 'A lot of people are asking right now — please wait a minute '
          + 'and try again.';
      } else if (res.status >= 400 || !res.body || res.body.success === false) {
        text = (res.body && res.body.error)
          ? 'That one stumped the system: ' + res.body.error
          : 'The question service is resting right now. Please try again in '
            + 'a little while.';
      /* an answer that opens with a table has no lead and is still structured */
      } else if (res.body.structured
                 && (res.body.structured.lead
                     || (res.body.structured.blocks || []).length)) {
        render(bub, res.body.structured, mine);
        return;
      } else {
        text = res.body.answer || 'No answer came back. Please try again.';
        if (!res.body.answer) {
          retryState = { question: q, districtNumber: district };
          setRequestControls(false);
        }
      }
      if (res.status >= 400 || !res.body || res.body.success === false) {
        retryState = { question: q, districtNumber: district };
        setRequestControls(false);
      }
      reveal(bub, text, mine);
    }).catch(function (err) {
      if (mine !== token) return;
      endRequest();
      retryState = { question: q, districtNumber: district };
      setRequestControls(false);
      finish(bub, err && err.name === 'AbortError'
        ? 'The request timed out. Try again when you are ready.'
        : 'The question service could not be reached. Please check your connection and try again.');
    });
  }

  function finish(bub, text) {
    bub.textContent = text;
    /* announced ONCE, complete — the animated copy mutates word by word,
       which would make a screen reader stutter through fragments */
    if (sr) sr.textContent = text;
    busy = false;
    sendBtn.disabled = false;
    if (wrap && !wrap.hidden) input.focus();
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
    if (wrap && !wrap.hidden) input.focus();
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
    var rest = function () {
      if (!alive()) return;
      target.appendChild(bodyOf(s, s.lead || ''));
      if (done) done();
    };
    /* No lead means the model opened with a table or a heading rather than a
       sentence. There is nothing to promote, and slicing raw text off the top
       of such an answer is how `| District | Per student |` ended up as the
       headline. Draw the body and let the answer start where it starts. */
    if (!s.lead_runs || !s.lead_runs.length) { rest(); return; }
    var concise = String(s.lead || '').match(/^.*?[.!?](?:\s|$)/);
    concise = concise ? concise[0].trim() : String(s.lead || '');
    var leadEl = el('p', 'ta-lead');
    target.appendChild(leadEl);
    /* The reveal writes plain words; the bold arrives with the last one. The
       text is identical either way, so nothing moves when it lands. */
    var done2 = function () {
      leadEl.textContent = '';
      leadEl.textContent = concise;
      rest();
    };
    if (reduce) { done2(); return; }
    writeWords(leadEl, concise, alive, done2);
  }

  function render(bub, s, mine) {
    var plain = plainOf(s);
    var msg = bub.parentNode;
    msg.classList.add('rich');
    renderInto(bub, s, function () { return mine === token; }, function () {
      settle(plain);
      /* settle() scrolls to the bottom, which is right while words are still
         arriving and wrong the moment the components land: it parks the
         reader on the sources and pushes the actual answer off the top. Put
         the START of this answer at the top of the thread instead. */
      thread.scrollTop = Math.max(0, msg.offsetTop - thread.offsetTop);
    });
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

  /* ---- beta feedback -------------------------------------------------------
     The telemetry on this site can say what a visitor DID. It cannot say what
     they came for and did not find, and that is the more useful half. This is
     the only place an anonymous visitor's words are stored, and the only place
     where storing them is obviously right: they typed into a box marked "tell
     us", which is consent in a way a page view never is.

     It lives in this file rather than its own because ask.js is already on all
     ten pages and already owns a sheet and a style block. A second widget
     would be a second thing to keep in step. */
  var fbWrap, fbText, fbContact, fbSend, fbLast;

  function feedbackUI() {
    if (fbWrap) return fbWrap;
    build();                                  // guarantees the style block
    fbWrap = h('<div class="tf-wrap" role="dialog" aria-modal="true"'
      + ' aria-labelledby="tf-title" hidden>'
      + '<div class="tf-back"></div><div class="tf-box">'
      + '<h2 id="tf-title">This site is in beta</h2>'
      + '<p>Every figure here comes from the state&rsquo;s own filings, and we are '
      + 'still learning which of them people actually need. Tell us what you '
      + 'came looking for &mdash; especially if you did not find it.</p>'
      + '<textarea aria-label="Your feedback" maxlength="2000"'
      + ' placeholder="What were you trying to find out?"></textarea>'
      + '<input type="text" maxlength="160" aria-label="Email, optional"'
      + ' placeholder="Email &mdash; optional, only if you want a reply">'
      + '<div class="tf-row"><button type="button" class="tf-send">Send</button>'
      + '<button type="button" class="ghost tf-close">Close</button></div>'
      + '<p class="tf-fine">We store what you write, the page you were on, and '
      + 'an email only if you choose to give one. Nothing else, and nothing '
      + 'that identifies you otherwise '
      + '(<a href="/about#privacy">what we collect</a>).</p>'
      + '</div></div>');
    document.body.appendChild(fbWrap);
    fbText = fbWrap.querySelector('textarea');
    fbContact = fbWrap.querySelector('input');
    fbSend = fbWrap.querySelector('.tf-send');
    fbWrap.querySelector('.tf-close').addEventListener('click', closeFeedback);
    fbWrap.querySelector('.tf-back').addEventListener('click', closeFeedback);
    fbSend.addEventListener('click', sendFeedback);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && fbWrap.classList.contains('open')) closeFeedback();
    });
    return fbWrap;
  }

  function openFeedback() {
    feedbackUI();
    fbLast = document.activeElement;
    fbWrap.hidden = false;
    requestAnimationFrame(function () { fbWrap.classList.add('open'); });
    setTimeout(function () { fbText.focus(); }, reduce ? 0 : 120);
  }

  function closeFeedback() {
    if (!fbWrap) return;
    fbWrap.classList.remove('open');
    fbWrap.hidden = true;
    if (fbLast && fbLast.focus) fbLast.focus();
  }

  function sendFeedback() {
    var msg = (fbText.value || '').trim();
    if (msg.length < 3) { fbText.focus(); return; }
    fbSend.disabled = true;
    fbSend.textContent = 'Sending…';
    fetch('/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: msg,
        page: location.pathname,
        district_number: districtNumber(),
        contact: (fbContact.value || '').trim() || null,
      }),
    }).then(thanks).catch(thanks);            /* a lost note must not scold */
  }

  /* The same ending either way. Someone who took the trouble to write should
     never be shown an error for their trouble — if the note did not land that
     is our problem, and it is logged on the server rather than put in front of
     them. */
  function thanks() {
    var box = fbWrap.querySelector('.tf-box');
    box.textContent = '';
    box.appendChild(el('h2', null, 'Thank you — that genuinely helps'));
    box.appendChild(el('p', null,
      'Beta feedback goes straight onto the list of what to fix next, '
      + 'alongside what the site can measure on its own.'));
    var row = el('div', 'tf-row');
    var b = el('button', null, 'Close');
    b.type = 'button';
    b.addEventListener('click', closeFeedback);
    row.appendChild(b);
    box.appendChild(row);
    setTimeout(closeFeedback, 3200);
  }

  /* The Beta chip IS the invitation — one affordance, not a label beside a
     link nobody presses. Added to the masthead of whatever page is showing. */
  function markBeta() {
    var brand = document.querySelector('#masthead .m-brand');
    if (!brand || document.querySelector('.m-beta')) return;
    var chip = el('button', 'm-beta', 'Beta');
    chip.type = 'button';
    chip.title = 'This site is in beta — tell us what is missing';
    chip.setAttribute('aria-haspopup', 'dialog');
    chip.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();                    /* the brand is a link home */
      openFeedback();
    });
    brand.parentNode.insertBefore(chip, brand.nextSibling);
  }

  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href="#feedback"]');
    if (!a) return;
    e.preventDefault();
    e.stopPropagation();
    var dd = a.closest('details');
    if (dd) dd.open = false;
    openFeedback();
  }, true);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', markBeta);
  } else {
    markBeta();
  }

  /* `render` is the whole point of exporting anything: the landing page has
     its own inline answer box, and before this it had its own copy of the
     answer renderer too. Two renderers means one of them is always the older
     one — the raw-Markdown bug lived in exactly that gap. One implementation,
     two places it can draw. */
  window.TISDAsk = {
    open: open,
    close: close,
    ask: function (question, districtNumber) {
      open();
      submit(question, districtNumber || null);
    },
    render: function (target, structured, alive) {
      build();
      renderInto(target, structured, alive, null);
    },
    feedback: openFeedback,
  };
}());
