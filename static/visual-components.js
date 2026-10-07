/* Shared, dependency-free semantics for public visual reporting.
   This file deliberately owns no page state so the website and an optional
   embedded surface can render the same public-data meaning. */
(function (global) {
  'use strict';

  const STATUS = new Set(['observed', 'modeled', 'missing', 'not_applicable', 'unverified']);
  const safeUrl = value => {
    try {
      const url = new URL(value, global.location && global.location.href);
      return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
    } catch (_) { return null; }
  };
  const text = value => value == null || value === '' ? 'Not available' : String(value);

  function teacherRetention(turnoverPercent) {
    if (turnoverPercent == null) return { status: 'missing', reason: 'Annual district turnover was not reported.' };
    const turnover = Number(turnoverPercent);
    if (!Number.isFinite(turnover) || turnover < 0 || turnover > 100) {
      return { status: 'unverified', reason: 'Annual district turnover is outside the valid 0–100% range.' };
    }
    const periods = 6;
    const expected = 10 * Math.pow(1 - turnover / 100, periods);
    return {
      status: 'modeled', turnoverPercent: turnover, expected, rounded: Math.round(expected), periods,
      assumption: 'Hypothetical district cohort of ten teachers; annual turnover is held constant and each teacher is assumed equally likely to remain.'
    };
  }

  function renderMetricMeta(container, metric) {
    if (!container || !metric || !global.document) return;
    const doc = global.document;
    const wrap = doc.createElement('div');
    wrap.className = 'visual-metric-meta';
    const line = doc.createElement('p');
    line.className = 'visual-metric-status';
    const status = STATUS.has(metric.status) ? metric.status : 'unverified';
    line.textContent = `${status.replace('_', ' ')} · ${text(metric.period)} · ${text(metric.unit)}`;
    wrap.appendChild(line);
    if (metric.population || metric.denominator) {
      const cohort = doc.createElement('p');
      cohort.textContent = [metric.population, metric.denominator].filter(Boolean).join(' · ');
      wrap.appendChild(cohort);
    }
    const source = metric.source || {};
    if (source.label) {
      const sourceLine = doc.createElement('p');
      const label = source.period ? `${source.label} (${source.period})` : source.label;
      const href = safeUrl(source.url);
      if (href) {
        const a = doc.createElement('a');
        a.href = href; a.target = '_blank'; a.rel = 'noopener'; a.textContent = `Source: ${label}`;
        sourceLine.appendChild(a);
      } else sourceLine.textContent = `Source: ${label}`;
      wrap.appendChild(sourceLine);
    }
    const limits = Array.isArray(metric.limits) ? metric.limits.filter(Boolean) : [];
    if (metric.model || limits.length) {
      const details = doc.createElement('details');
      const summary = doc.createElement('summary'); summary.textContent = 'Method and limits'; details.appendChild(summary);
      if (metric.model && metric.model.assumptions) {
        const p = doc.createElement('p'); p.textContent = metric.model.assumptions; details.appendChild(p);
      }
      limits.forEach(limit => { const p = doc.createElement('p'); p.textContent = String(limit); details.appendChild(p); });
      wrap.appendChild(details);
    }
    container.replaceChildren(wrap);
  }

  function renderAccessibleTable(container, columns, rows, caption) {
    if (!container || !global.document) return;
    const doc = global.document, table = doc.createElement('table');
    table.className = 'table visual-table';
    const cap = doc.createElement('caption'); cap.textContent = text(caption); table.appendChild(cap);
    const head = doc.createElement('thead'), headRow = doc.createElement('tr');
    (columns || []).forEach(column => { const th = doc.createElement('th'); th.scope = 'col'; th.textContent = text(column); headRow.appendChild(th); });
    head.appendChild(headRow); table.appendChild(head);
    const body = doc.createElement('tbody');
    (rows || []).forEach(row => { const tr = doc.createElement('tr'); (row || []).forEach((value, index) => {
      const cell = doc.createElement(index === 0 ? 'th' : 'td'); if (index === 0) cell.scope = 'row'; cell.textContent = text(value); tr.appendChild(cell);
    }); body.appendChild(tr); });
    table.appendChild(body); container.replaceChildren(table);
  }

  global.TxisdVisual = Object.freeze({ teacherRetention, renderMetricMeta, renderAccessibleTable });
})(window);
