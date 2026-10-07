/* Auditable browser evidence collector: tight painted marks and text ranges only. */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import zlib from 'node:zlib';
import { classifyPage } from './measurement-core.mjs';
import { chromium, firefox } from '@playwright/test';

const phase = process.argv[2];
if (!['baseline', 'prototype', 'final'].includes(phase)) throw new Error('phase required');
const baseURL = process.env.TISD_BASE_URL || 'http://127.0.0.1:8765';
const root = path.resolve('../..');
const evidence = path.join(root, 'docs/evidence/visual');
const output = path.join(evidence, 'measurements.json.gz');
const { states } = JSON.parse(fs.readFileSync('fixtures/public-states.json', 'utf8'));
const manifest = JSON.parse(fs.readFileSync('visual-regions.json', 'utf8'));
const prototypeManifest = JSON.parse(fs.readFileSync('visual-regions-prototype.json', 'utf8'));
const endpointFixture = JSON.parse(fs.readFileSync('fixtures/public-endpoints.json', 'utf8'));
const viewports = [{ width: 1440, height: 900 }, { width: 768, height: 1024 }, { width: 390, height: 844 }];
const onlyStates = process.env.TISD_CAPTURE_STATES ? new Set(process.env.TISD_CAPTURE_STATES.split(',')) : null;
const compactRegions = regions => regions.map(({ text, ...region }) => region);
const historicalRevision = '73df1896ed0818020ec1c15c06f5ee823db7ec0f';
const digest = value => crypto.createHash('sha256').update(value).digest('hex');
const gitBlob = file => execFileSync('git', ['show', `${historicalRevision}:${file}`], { cwd: root });
const contentType = pathname => pathname.endsWith('.css') ? 'text/css' : pathname.endsWith('.js') ? 'text/javascript' : 'text/html';

function phaseAssets() {
  if (phase === 'baseline') {
    const files = {
      '/static/design.css': gitBlob('static/design.css'),
      '/static/ask.js': gitBlob('static/ask.js'),
      '/static/track.js': gitBlob('static/track.js'),
    };
    const document = gitBlob('static/index.html');
    return {
      document, documentPath: 'static/index.html', files,
      provenance: {
        source_mode: 'retrospective-git-blob-interceptor', source_revision: historicalRevision,
        captured_after_source_revision: true,
        sha256: {
          'static/index.html': digest(document),
          ...Object.fromEntries(Object.entries(files).map(([pathname, value]) => [pathname.slice(1), digest(value)])),
        },
        telemetry: 'external Vercel insights blocked; historical track.js fulfilled from pinned Git blob',
      },
    };
  }
  if (phase === 'prototype') {
    const prototypePath = path.join(root, 'design/public-portal-prototype.html');
    const document = fs.readFileSync(prototypePath);
    return {
      document, documentPath: 'design/public-portal-prototype.html', files: {},
      provenance: {
        source_mode: 'test-only-file-interceptor', source_revision: 'working-tree immutable prototype',
        captured_after_source_revision: true,
        sha256: { 'design/public-portal-prototype.html': digest(document) },
        scope: 'Dallas concept only; controls are intentionally nonfunctional',
      },
    };
  }
  return null;
}
const assets = phaseAssets();
const selectedManifest = phase === 'prototype' ? prototypeManifest : manifest;

const classify = page => classifyPage(page, selectedManifest);
function cropRegions(regions, scrollX, scrollY, viewport) {
  const right = scrollX + viewport.width;
  const bottom = scrollY + viewport.height;
  return regions.map(region => ({
    ...region,
    left: Math.max(region.left, scrollX),
    top: Math.max(region.top, scrollY),
    right: Math.min(region.right, right),
    bottom: Math.min(region.bottom, bottom),
  })).filter(region => region.right > region.left && region.bottom > region.top);
}

async function annotate(page, outputPath, regions, fullPage) {
  await page.evaluate(regions => {
    const overlay = document.createElement('div');
    overlay.id = 'visual-measurement-overlay';
    overlay.style.cssText = 'position:absolute;inset:0;z-index:2147483647;pointer-events:none';
    for (const region of regions) {
      const item = document.createElement('i');
      const color = region.kind === 'visual' ? '#0067ff' : '#d60000';
      item.style.cssText = `position:absolute;left:${region.left}px;top:${region.top}px;width:${region.right - region.left}px;height:${region.bottom - region.top}px;border:1px solid ${color};background:${color}18;box-sizing:border-box`;
      overlay.appendChild(item);
    }
    document.body.appendChild(overlay);
  }, regions);
  const image = outputPath.endsWith('.png')
    ? { type: 'png' }
    : { type: 'jpeg', quality: 84 };
  await page.screenshot({ path: outputPath, fullPage, ...image });
  await page.locator('#visual-measurement-overlay').evaluate(element => element.remove());
}

function fixtureRouteMap() {
  return new Map(Object.entries(endpointFixture.routes).map(([key, route]) => [route, key]));
}

async function installPublicFixtures(page, unavailable, externalRequests) {
  const routes = fixtureRouteMap();
  const origin = new URL(baseURL).origin;
  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) {
      externalRequests.push(request.url());
      return route.abort('blockedbyclient');
    }
    if (assets && request.method() === 'GET') {
      const isDocument = request.resourceType() === 'document';
      if (isDocument) {
        return route.fulfill({ status: 200, contentType: 'text/html', body: assets.document });
      }
      const historicalAsset = assets.files[url.pathname];
      if (historicalAsset) {
        return route.fulfill({ status: 200, contentType: contentType(url.pathname), body: historicalAsset });
      }
    }
    const routeKey = `${url.pathname}${url.search}`;
    if (request.method() === 'POST' && url.pathname === '/query') {
      return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"fixture unavailable"}' });
    }
    if (url.pathname === '/districts' && url.searchParams.has('search')) {
      const query = (url.searchParams.get('search') || '').toLowerCase();
      const row = endpointFixture.payloads.houston_summary.find(item => item.district_name);
      const result = row && (row.district_name || '').toLowerCase().includes(query)
        ? [{ district_number: '101912', district_name: row.district_name }] : [];
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(result) });
    }
    const key = routes.get(routeKey);
    if (key) {
      if (unavailable) return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"fixture unavailable"}' });
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(endpointFixture.payloads[key]) });
    }
    return route.continue();
  });
}

async function waitForSettledUi(page, stateName) {
  if (phase === 'prototype') {
    await page.locator('main').waitFor({ state: 'visible', timeout: 10000 });
    await page.locator('.bars > i').first().waitFor({ state: 'visible', timeout: 10000 });
    await page.evaluate(async () => { if (document.fonts?.ready) await document.fonts.ready; });
    return;
  }
  try {
    await page.waitForFunction(name => {
      if (name === 'statewide') {
        const hero = document.querySelector('#hero-num');
        if (!hero || /[$—]\s*$/.test(hero.textContent.trim())) return false;
      } else {
        const dash = document.querySelector('#dash');
        const district = document.querySelector('#dname');
        if (!dash || dash.classList.contains('hidden') || !district?.textContent.trim()) return false;
      }
      return ![...document.querySelectorAll('[aria-label]')].some(element => element._armed && !element._done);
    }, stateName, { timeout: 15000 });
  } catch (error) {
    const diagnostic = await page.evaluate(() => ({
      hero: document.querySelector('#hero-num')?.textContent,
      dashClass: document.querySelector('#dash')?.className,
      district: document.querySelector('#dname')?.textContent,
      counters: [...document.querySelectorAll('[aria-label]')].filter(element => element._armed && !element._done).map(element => ({ id: element.id, text: element.textContent, label: element.getAttribute('aria-label') })).slice(0, 20),
      bodyClass: document.documentElement.className,
    }));
    throw new Error(`UI did not settle for ${stateName}: ${JSON.stringify(diagnostic)}`, { cause: error });
  }
  await page.evaluate(async () => {
    if (document.fonts?.ready) await document.fonts.ready;
    const finite = document.getAnimations().filter(animation => animation.effect?.getTiming().iterations !== Infinity);
    await Promise.allSettled(finite.map(animation => animation.finished));
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  });
}

async function selectHoustonComparison(page) {
  await page.locator('#btn-compare').click();
  await page.locator('#csearch').fill('Houston');
  await page.locator('#csearchbtn').click();
  const result = page.locator('#cresults button', { hasText: '101912' });
  await result.waitFor({ state: 'visible', timeout: 10000 });
  await result.click();
  await page.waitForFunction(() => /Houston/i.test(document.querySelector('#comparebar')?.textContent || ''), null, { timeout: 10000 });
}

async function activateScrollContent(page, viewportHeight) {
  const start = await page.evaluate(() => ({ x: scrollX, y: scrollY }));
  let height = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y < height; y += Math.max(320, Math.floor(viewportHeight * .72))) {
    await page.evaluate(next => scrollTo(0, next), y);
    await page.waitForTimeout(24);
    height = Math.max(height, await page.evaluate(() => document.documentElement.scrollHeight));
  }
  await page.evaluate(position => scrollTo(position.x, position.y), start);
  await page.waitForTimeout(100);
  await page.evaluate(async () => {
    const finite = document.getAnimations().filter(animation => animation.effect?.getTiming().iterations !== Infinity);
    await Promise.allSettled(finite.map(animation => animation.finished));
  });
}

const report = fs.existsSync(output)
  ? JSON.parse(zlib.gunzipSync(fs.readFileSync(output)).toString('utf8'))
  : { phases: {} };
const cases = [];
const stateEntries = phase === 'prototype'
  ? [['dallas', states.dallas]]
  : Object.entries(states).filter(([stateName]) => stateName !== 'missing');
fs.mkdirSync(evidence, { recursive: true });
for (const [browserName, type] of [['chromium', chromium], ['firefox', firefox]]) {
  const browser = await type.launch();
  for (const viewport of viewports) for (const theme of ['light', 'dark']) for (const [stateName, state] of stateEntries) {
    if (onlyStates && !onlyStates.has(stateName)) continue;
    const page = await browser.newPage({ viewport, colorScheme: theme, reducedMotion: 'reduce' });
    const pageErrors = [];
    const rendererWarnings = [];
    const externalRequests = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    page.on('console', message => {
      if (/section .* could not render/i.test(message.text())) rendererWarnings.push(message.text());
    });
    await page.addInitScript(theme => {
      localStorage.clear();
      sessionStorage.clear();
      if (theme === 'dark') localStorage.setItem('tisd_theme', 'dark');
      const proto = window.CanvasRenderingContext2D && CanvasRenderingContext2D.prototype;
      if (!proto || proto.__visualInstrumented) return;
      Object.defineProperty(proto, '__visualInstrumented', { value: true });
      const record = (context, operation) => {
        const canvas = context.canvas;
        if (!canvas) return;
        (canvas.__visualPaintOps ||= []).push({ opacity: Number(context.globalAlpha ?? 1), ...operation });
      };
      const wrap = (name, after) => {
        const original = proto[name];
        if (typeof original !== 'function') return;
        proto[name] = function (...args) { const result = original.apply(this, args); after.call(this, args); return result; };
      };
      wrap('fillRect', function ([x, y, width, height]) { record(this, { left: x, top: y, width, height, role: 'data-mark' }); });
      wrap('strokeRect', function ([x, y, width, height]) { const pad = Math.max(1, this.lineWidth || 1) / 2; record(this, { left: x - pad, top: y - pad, width: width + pad * 2, height: height + pad * 2, role: 'data-mark' }); });
      wrap('drawImage', function (args) {
        if (args.length < 3) return;
        const source = args[0];
        const width = args.length >= 9 ? args[7] : (args.length >= 5 ? args[3] : source?.width || 0);
        const height = args.length >= 9 ? args[8] : (args.length >= 5 ? args[4] : source?.height || 0);
        const left = args.length >= 9 ? args[5] : args[1];
        const top = args.length >= 9 ? args[6] : args[2];
        record(this, { left, top, width, height, role: 'data-mark' });
      });
      for (const name of ['fillText', 'strokeText']) wrap(name, function ([text, x, y, maxWidth]) {
        const metrics = this.measureText(String(text));
        const width = Math.min(maxWidth || Infinity, metrics.width || 1);
        const height = (metrics.actualBoundingBoxAscent || 8) + (metrics.actualBoundingBoxDescent || 2);
        record(this, { left: x, top: y - (metrics.actualBoundingBoxAscent || 8), width, height, role: 'necessary-label', text: String(text) });
      });
      wrap('beginPath', function () { this.__visualPathPoints = []; });
      wrap('moveTo', function ([x, y]) { (this.__visualPathPoints ||= []).push([x, y]); });
      wrap('lineTo', function ([x, y]) { (this.__visualPathPoints ||= []).push([x, y]); });
      wrap('arc', function ([x, y, radius, start = 0, end = Math.PI * 2]) {
        const points = (this.__visualPathPoints ||= []);
        const count = Math.max(8, Math.ceil(Math.abs(end - start) * radius / 8));
        for (let index = 0; index <= count; index++) {
          const angle = start + (end - start) * index / count;
          points.push([x + Math.cos(angle) * radius, y + Math.sin(angle) * radius]);
        }
      });
      for (const name of ['stroke', 'fill']) wrap(name, function () {
        const points = this.__visualPathPoints || [];
        if (points.length < 2) return;
        const pad = Math.max(1.5, this.lineWidth || 1) / 2;
        for (let index = 1; index < points.length; index++) {
          const prior = points[index - 1], point = points[index];
          const distance = Math.hypot(point[0] - prior[0], point[1] - prior[1]);
          const segments = Math.max(1, Math.ceil(distance / 8));
          for (let segment = 0; segment < segments; segment++) {
            const a = segment / segments, b = (segment + 1) / segments;
            const x1 = prior[0] + (point[0] - prior[0]) * a, y1 = prior[1] + (point[1] - prior[1]) * a;
            const x2 = prior[0] + (point[0] - prior[0]) * b, y2 = prior[1] + (point[1] - prior[1]) * b;
            record(this, { left: Math.min(x1, x2) - pad, top: Math.min(y1, y2) - pad, width: Math.abs(x2 - x1) + pad * 2, height: Math.abs(y2 - y1) + pad * 2, role: 'data-mark' });
          }
        }
      });
    }, theme);
    await installPublicFixtures(page, stateName === 'unavailable', externalRequests);
    const target = new URL(phase === 'prototype' ? '/design/public-portal-prototype.html' : state.route, baseURL).href;
    await page.goto(target, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await waitForSettledUi(page, stateName);
    if (phase !== 'prototype' && stateName === 'compare') {
      await selectHoustonComparison(page);
      await waitForSettledUi(page, stateName);
    }
    const key = `${phase}-${browserName}-${stateName}-${viewport.width}x${viewport.height}-${theme}`;
    const imageExtension = phase === 'final' ? 'png' : 'jpg';
    const imageOptions = phase === 'final' ? { type: 'png' } : { type: 'jpeg', quality: 84 };
    const screenshot = `docs/evidence/visual/${key}.${imageExtension}`;
    const annotation = `docs/evidence/visual/${key}-annotated.${imageExtension}`;
    const initialScreenshot = `docs/evidence/visual/${key}-initial.${imageExtension}`;
    const initialAnnotation = `docs/evidence/visual/${key}-initial-annotated.${imageExtension}`;
    const initialScroll = await page.evaluate(() => ({ x: scrollX, y: scrollY }));
    await page.screenshot({ path: path.join(root, initialScreenshot), fullPage: false, ...imageOptions });
    const initialMeasured = await classify(page);
    const initialRegions = cropRegions(initialMeasured.regions, initialMeasured.scrollX, initialMeasured.scrollY, viewport);
    await annotate(page, path.join(root, initialAnnotation), initialRegions, false);
    await activateScrollContent(page, viewport.height);
    await page.screenshot({ path: path.join(root, screenshot), fullPage: true, ...imageOptions });
    const measured = await classify(page);
    await annotate(page, path.join(root, annotation), measured.regions, true);
    const visibleArtifactSections = stateName === 'unavailable'
      ? await page.locator('#dash section:not(.hidden) svg[role="img"], #dash section:not(.hidden) .pennies[role="img"]').count()
      : null;
    cases.push({
      id: key, phase, state: stateName, browser: browserName, browser_version: browser.version(),
      viewport, theme, reduced_motion: true, zoom: 1, url: target,
      screenshot, annotation, initial_screenshot: initialScreenshot, initial_annotation: initialAnnotation,
      status: 'measured', regions: compactRegions(measured.regions), initial_regions: compactRegions(initialRegions),
      inventory: measured.inventory, unclassified: measured.unclassified,
      graphics: measured.graphics, manifest_errors: measured.manifest_errors,
      initial_scroll: initialScroll, comparison_selected: stateName === 'compare' ? true : null,
      unavailable_artifact_graphics: visibleArtifactSections,
      page_errors: pageErrors, renderer_warnings: rendererWarnings, blocked_external_requests: externalRequests,
      reviewed: false,
      review_note: 'Geometry is automated. A fresh independent semantic reviewer must inspect every raw and annotated image and record reviewer identity before setting reviewed=true. Agent review does not constitute human-participant or assistive-technology testing.',
    });
    await page.close();
  }
  await browser.close();
}
const retainedCases = onlyStates && report.phases[phase]
  ? report.phases[phase].cases.filter(item => !onlyStates.has(item.state)) : [];
report.source_revision = process.env.TISD_REVISION || 'working-tree';
report.captured_at = new Date().toISOString();
report.collector = 'tests/browser/capture-visuals.mjs';
report.rubric_version = selectedManifest.rubric_version;
report.phases[phase] = {
  base_url: baseURL, rubric_version: selectedManifest.rubric_version,
  fixture_origin: endpointFixture.origin, fixture_captured_at: endpointFixture.captured_at,
  fixture_hashes: endpointFixture.sha256,
  source_provenance: assets?.provenance || { source_mode: 'working-tree-server', source_revision: process.env.TISD_REVISION || 'working-tree' },
  scope: phase === 'prototype' ? {
    captured: ['dallas'],
    unverified: {
      statewide: 'not implemented by the immutable Dallas concept prototype',
      compare: 'not implemented by the immutable Dallas concept prototype',
      unavailable: 'not implemented by the immutable Dallas concept prototype',
    },
    out_of_scope: ['small', 'charter'],
  } : undefined,
  cases: [...retainedCases, ...cases],
};
const serialized = Buffer.from(JSON.stringify(report) + '\n');
fs.writeFileSync(output, zlib.gzipSync(serialized, { level: 9 }));
fs.writeFileSync(path.join(evidence, 'measurements-provenance.json'), JSON.stringify({
  format: 'gzip-compressed canonical JSON',
  canonical_path: 'docs/evidence/visual/measurements.json.gz',
  uncompressed_bytes: serialized.length,
  uncompressed_sha256: digest(serialized),
  gzip_bytes: fs.statSync(output).size,
  gzip_sha256: digest(fs.readFileSync(output)),
  case_counts: Object.fromEntries(Object.entries(report.phases).map(([name, value]) => [name, value.cases?.length || 0])),
}, null, 2) + '\n');
