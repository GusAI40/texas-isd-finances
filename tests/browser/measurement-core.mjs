/* Shared semantic painted-mark classifier. Keep one implementation for portal and MCP evidence. */
export async function classifyPage(page, manifest) {
  return page.evaluate(manifest => {
    const roots = [];
    const manifestErrors = [];
    const query = selector => {
      try { return [...document.querySelectorAll(selector)]; }
      catch (error) { manifestErrors.push(`invalid selector ${selector}: ${error.message}`); return []; }
    };
    for (const rule of manifest.analytic_roots) {
      const matches = query(rule.selector);
      if (rule.required && !matches.length) manifestErrors.push(`required analytic root missing: ${rule.selector}`);
      roots.push(...matches);
    }
    const inRoot = el => roots.some(root => root === el || root.contains(el));
    const styleState = el => {
      let opacity = 1;
      for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
        const style = getComputedStyle(node);
        if (node.hidden || style.display === 'none' || style.visibility === 'hidden') return { visible: false, opacity: 0 };
        opacity *= Number(style.opacity || 1);
      }
      const box = el.getBoundingClientRect();
      return { visible: opacity > 0 && box.width > 0 && box.height > 0, opacity };
    };
    const identity = el => {
      if (el.id) return `#${CSS.escape(el.id)}`;
      const bits = [];
      for (let node = el; node && node !== document.body; node = node.parentElement) {
        if (!node.parentElement) break;
        const index = [...node.parentElement.children].indexOf(node) + 1;
        bits.unshift(`${node.tagName.toLowerCase()}:nth-child(${index})`);
      }
      return `body>${bits.join('>')}`;
    };
    const directTextIdentity = node => {
      const parent = node.parentElement;
      const index = [...parent.childNodes].filter(n => n.nodeType === Node.TEXT_NODE).indexOf(node) + 1;
      return `${identity(parent)}::text(${index})`;
    };
    const pageRect = box => ({
      left: box.left + scrollX, top: box.top + scrollY,
      right: box.right + scrollX, bottom: box.bottom + scrollY,
    });
    const excludedRule = el => manifest.exclusions.find(rule => {
      try { return !!el.closest(rule.selector); } catch (_) { return false; }
    });
    const closestAny = (el, selectors) => selectors.some(selector => {
      try { return !!el.closest(selector); } catch (_) { return false; }
    });
    const proseMissing = text => /^(?:—|–|-|n\/?a|none)$/i.test(text)
      || /\b(?:unavailable|not available|missing|unknown|could not load|no data)\b/i.test(text);
    const regions = [];
    const exclusions = [];
    const inventory = [];
    const unclassified = [];
    const inventoryKeys = new Set();
    const pushInventory = item => {
      const key = `${item.selector}|${item.node_type}`;
      if (inventoryKeys.has(key)) return;
      inventoryKeys.add(key);
      inventory.push(item);
      if (item.classification === 'unclassified') unclassified.push(item);
    };
    const addTextNode = node => {
      const parent = node.parentElement;
      if (!parent || !inRoot(parent)) return;
      const value = (node.nodeValue || '').replace(/\s+/g, ' ').trim();
      if (!value) return;
      const state = styleState(parent);
      if (!state.visible) return;
      const selector = directTextIdentity(node);
      const exclusion = excludedRule(parent);
      const tag = parent.tagName.toLowerCase();
      const isHeading = /^h[1-6]$/.test(tag);
      const explicitVisual = closestAny(parent, manifest.visual_text);
      const narrative = closestAny(parent, manifest.prose);
      let classification = 'unclassified';
      let semanticRole = null;
      let reason = null;
      if (exclusion) {
        classification = 'excluded'; reason = exclusion.reason;
      } else if (proseMissing(value)) {
        classification = 'prose'; semanticRole = 'missing-status';
      } else if (parent.closest('svg[role="img"]:not([aria-hidden="true"])')) {
        classification = 'visual';
        semanticRole = /\b(?:observed|modeled|fiscal|fy\d|source)\b/i.test(value) ? 'necessary-status' : 'necessary-label';
      } else if (explicitVisual) {
        classification = 'visual';
        semanticRole = /\b(?:observed|modeled|fiscal|fy\d|source)\b/i.test(value) ? 'necessary-status' : 'necessary-label';
      } else if (narrative || isHeading) {
        classification = 'prose'; semanticRole = 'narrative';
      }
      const record = { selector, node_type: 'text', text: value.slice(0, 240), classification, semantic_role: semanticRole, reason };
      pushInventory(record);
      const range = document.createRange();
      range.selectNodeContents(node);
      const boxes = [...range.getClientRects()].filter(box => box.width > 0 && box.height > 0);
      boxes.forEach((box, index) => {
        const item = { selector: `${selector}[line=${index + 1}]`, ...pageRect(box), visible: true, opacity: state.opacity, text: value.slice(0, 180) };
        if (classification === 'excluded') exclusions.push({ ...item, kind: 'excluded', reason });
        else if (classification === 'visual' || classification === 'prose') {
          regions.push({ ...item, kind: classification, bounds_kind: 'text-range', semantic_role: semanticRole });
        }
      });
    };
    for (const root of roots) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) addTextNode(node);
    }

    const addHtmlMark = el => {
      if (!inRoot(el)) return false;
      const state = styleState(el);
      if (!state.visible) return false;
      const selector = identity(el);
      const exclusion = excludedRule(el);
      const classification = exclusion ? 'excluded' : 'visual';
      pushInventory({ selector, node_type: 'html-mark', text: '', classification, semantic_role: classification === 'visual' ? 'data-mark' : null, reason: exclusion?.reason || null });
      const item = { selector, ...pageRect(el.getBoundingClientRect()), visible: true, opacity: state.opacity };
      if (exclusion) exclusions.push({ ...item, kind: 'excluded', reason: exclusion.reason });
      else regions.push({ ...item, kind: 'visual', bounds_kind: 'html-mark', semantic_role: 'data-mark' });
      return !exclusion;
    };
    const htmlMarks = new Set();
    for (const selector of manifest.html_marks) query(selector).forEach(el => htmlMarks.add(el));
    htmlMarks.forEach(addHtmlMark);

    const svgMarkRects = el => {
      const style = getComputedStyle(el);
      const stroke = Math.max(1.5, parseFloat(style.strokeWidth) || 0);
      const tag = el.tagName.toLowerCase();
      const box = el.getBoundingClientRect();
      if (tag === 'rect') return box.width && box.height ? [pageRect(box)] : [];
      if (tag === 'circle' || tag === 'ellipse') {
        const strips = [];
        const count = 10;
        for (let index = 0; index < count; index++) {
          const y0 = -1 + 2 * index / count;
          const y1 = -1 + 2 * (index + 1) / count;
          const half = Math.sqrt(Math.max(0, 1 - Math.max(Math.abs(y0), Math.abs(y1)) ** 2));
          const midY = box.top + (index + .5) * box.height / count;
          strips.push(pageRect({ left: box.left + box.width * (.5 - half / 2), right: box.left + box.width * (.5 + half / 2), top: midY - box.height / count / 2, bottom: midY + box.height / count / 2 }));
        }
        return strips;
      }
      if (typeof el.getTotalLength !== 'function' || typeof el.getPointAtLength !== 'function') return [];
      let length;
      try { length = el.getTotalLength(); } catch (_) { return []; }
      if (!Number.isFinite(length) || length <= 0) return [];
      const matrix = el.getScreenCTM();
      if (!matrix) return [];
      const count = Math.min(240, Math.max(2, Math.ceil(length / 8)));
      const points = [];
      for (let index = 0; index <= count; index++) {
        const point = el.getPointAtLength(length * index / count);
        const transformed = new DOMPoint(point.x, point.y).matrixTransform(matrix);
        points.push(transformed);
      }
      return points.slice(1).map((point, index) => {
        const prior = points[index];
        return {
          left: Math.min(prior.x, point.x) - stroke / 2 + scrollX,
          top: Math.min(prior.y, point.y) - stroke / 2 + scrollY,
          right: Math.max(prior.x, point.x) + stroke / 2 + scrollX,
          bottom: Math.max(prior.y, point.y) + stroke / 2 + scrollY,
        };
      });
    };
    const graphics = [];
    const graphicRoots = new Set();
    for (const selector of manifest.graphic_roots) query(selector).forEach(el => { if (inRoot(el)) graphicRoots.add(el); });
    for (const graphic of graphicRoots) {
      const graphicState = styleState(graphic);
      if (!graphicState.visible) continue;
      let dataMarks = 0;
      if (graphic.matches('canvas')) {
        const box = graphic.getBoundingClientRect();
        const scaleX = box.width / (graphic.width || box.width || 1);
        const scaleY = box.height / (graphic.height || box.height || 1);
        for (const [index, operation] of (graphic.__visualPaintOps || []).entries()) {
          if (!operation || operation.opacity <= 0 || operation.width <= 0 || operation.height <= 0) continue;
          const coversCanvas = operation.width * operation.height / Math.max(1, graphic.width * graphic.height) > .85;
          if (coversCanvas && operation.role !== 'necessary-label') continue;
          const selector = `${identity(graphic)}::paint(${index + 1})`;
          const region = {
            selector,
            left: box.left + operation.left * scaleX + scrollX,
            top: box.top + operation.top * scaleY + scrollY,
            right: box.left + (operation.left + operation.width) * scaleX + scrollX,
            bottom: box.top + (operation.top + operation.height) * scaleY + scrollY,
            visible: true, opacity: graphicState.opacity * operation.opacity,
            kind: 'visual', bounds_kind: 'canvas-mark', semantic_role: operation.role || 'data-mark',
          };
          regions.push(region);
          pushInventory({ selector, node_type: 'canvas-mark', text: operation.text || '', classification: 'visual', semantic_role: region.semantic_role, reason: null });
          if (region.semantic_role === 'data-mark') dataMarks += 1;
        }
      } else if (graphic.matches('svg')) {
        const graphicBox = graphic.getBoundingClientRect();
        for (const mark of graphic.querySelectorAll('path,line,polyline,polygon,rect,circle,ellipse')) {
          if (mark.closest('defs,clipPath,mask') || mark.closest('[aria-hidden="true"]') || mark.matches('.grid,.axis')) continue;
          const state = styleState(mark);
          if (!state.visible) continue;
          const markBox = mark.getBoundingClientRect();
          const coversPlot = graphicBox.width * graphicBox.height > 0
            && markBox.width * markBox.height / (graphicBox.width * graphicBox.height) > .85;
          if (coversPlot && !mark.hasAttribute('data-tip') && !mark.hasAttribute('data-value')) continue;
          const selector = identity(mark);
          const rects = svgMarkRects(mark).filter(rect => rect.right > rect.left && rect.bottom > rect.top);
          if (!rects.length) continue;
          dataMarks += 1;
          pushInventory({ selector, node_type: 'svg-mark', text: '', classification: 'visual', semantic_role: 'data-mark', reason: null });
          rects.forEach((rect, index) => regions.push({
            selector: `${selector}[paint=${index + 1}]`, ...rect, visible: true,
            opacity: state.opacity, kind: 'visual', bounds_kind: 'svg-mark', semantic_role: 'data-mark',
          }));
        }
      } else {
        for (const mark of htmlMarks) if (graphic.contains(mark) && styleState(mark).visible && !excludedRule(mark)) dataMarks += 1;
      }
      graphics.push({ selector: identity(graphic), visible: true, data_marks: dataMarks });
    }
    return { regions, exclusions, inventory, unclassified, graphics, manifest_errors: manifestErrors, scrollY, scrollX };
  }, manifest);
}

