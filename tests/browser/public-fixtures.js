/* Recorded public GET fixtures for browser workflow checks.  Keep this helper
 * read-only: the fixture records the captured public API responses and hashes. */
const fs = require('node:fs');
const path = require('node:path');

const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'public-endpoints.json'), 'utf8'));
const districtGeo = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'district_geo.json'), 'utf8'));
const argyleEvidence = JSON.parse(fs.readFileSync(
  path.join(__dirname, '..', '..', 'docs', 'evidence', 'mcp', 'framing-argyle-public.json'), 'utf8'));

const SEARCH_ROWS = [
  ['057905', 'DALLAS ISD'], ['101912', 'HOUSTON ISD'],
  ['091907', 'TIOGA ISD'], ['003801', 'PINEYWOODS COMMUNITY ACADEMY'],
  // The registry contains two distinct districts with this exact public name.
  // Keeping both real six-digit TEA IDs makes the ambiguity workflow honest.
  ['043914', 'WYLIE ISD'], ['221912', 'WYLIE ISD'],
  ['061910', 'ARGYLE ISD'],
];
const MUTATING_PATHS = new Set(['/feedback', '/query', '/track', '/telemetry']);
// Minimal projection of the read-only public peers response used by the
// browser framing check. Source: https://txisd.dev/district/061910/peers,
// checked 2026-10-07T23:07:44Z; raw-response SHA-256:
// 0515e88e227707c27966607b99785902beb1ce91e1905a6fd9f9bd99cf8fb516.
const ARGYLE_PEERS_EVIDENCE = {
  district: argyleEvidence.row,
  peers: [],
  statewide: { spend_percentile: 85, statewide_median_spend: 19314 },
  basis: 'similarity_graph',
};
// Current read-only public optional sections, checked 2026-10-07T23:39Z.
// Raw SHA-256: turnarounds 20705c14fd09b0ef4e55f1ec7f8977d637dee9a1f9e489b8fe05e7edcb9a4313;
// insights 10c7321ed9fc14bc494b7f0e103adf49732abbef7cf26b040c5c366400f867d5.
const ARGYLE_OPTIONAL_EVIDENCE = {
  turnarounds: {
    turnarounds: [{ district_number: '091908', district_name: 'VAN ALSTYNE ISD',
      type: 'enrollment_reversal', struggled: '2011-2013', recovered_since: 2014 }],
    peers_scanned: 12, absence: null,
  },
  insights: {
    district_number: '061910', district_name: 'ARGYLE ISD', year: 2025,
    peer_count: 12, enrollment: 6114, net_variance_vs_peers: 5842812,
    insights: [{ metric: 'Debt service', your_value: 5151.88, peer_median: 4196.24,
      unit: 'per student', pct_vs_peers: 23.0, direction: 'above', dollar_impact: 5842812,
      annual_dollars_vs_peers: '$5,842,812/year above peers',
      finding: 'Debt payments per student are heavier than peers — check the bond schedule.' }],
    absence: null,
  },
};

// Read-only public dollar responses checked 2026-10-07T23:10Z.
// Dallas SHA-256 2c02553325e9b62e18b5bf877e8a9cf37a063447e9b3a9dcc17b811403dae26d;
// Argyle SHA-256 66769cfa53a3a3ac88fa422b13325911e276873facb9460bc4f2414252b387c3.
const DOLLAR_EVIDENCE = {
  '057905': JSON.parse("{\"district_number\":\"057905\",\"district_name\":\"DALLAS ISD\",\"year\":2025,\"prev_year\":2020,\"enrollment\":139776,\"total_spend\":3319208715,\"per_student\":23747,\"peer_count\":12,\"state_count\":1202,\"parts\":[{\"key\":\"classroom\",\"label\":\"Classroom teaching\",\"contents\":\"Teachers' pay and benefits, classroom materials, school libraries and media specialists, and training for teachers.\",\"codes\":\"TEA functions 11, 12, 13\",\"columns\":[\"classroom_instruction\"],\"components\":[],\"amount\":1092607589,\"per_student\":7817,\"cents\":33,\"cents_prev\":42,\"peer_cents\":42,\"state_cents\":47,\"peer_per_student\":7597,\"state_per_student\":7833,\"dollars_vs_peers\":30677729},{\"key\":\"construction\",\"label\":\"Construction\",\"contents\":\"New buildings, major renovations, land, and large equipment purchases.\",\"codes\":\"TEA object 6600\",\"columns\":[\"capital_projects\"],\"components\":[],\"amount\":766316261,\"per_student\":5482,\"cents\":23,\"cents_prev\":13,\"peer_cents\":14,\"state_cents\":6,\"peer_per_student\":2656,\"state_per_student\":1042,\"dollars_vs_peers\":395011607},{\"key\":\"debt\",\"label\":\"Debt payments\",\"contents\":\"Principal and interest on bonds voters approved in past elections — mostly for buildings that are already standing.\",\"codes\":\"TEA object 6500\",\"columns\":[\"debt_service\"],\"components\":[],\"amount\":500174938,\"per_student\":3578,\"cents\":15,\"cents_prev\":12,\"peer_cents\":16,\"state_cents\":9,\"peer_per_student\":2663,\"state_per_student\":1537,\"dollars_vs_peers\":127941034},{\"key\":\"admin\",\"label\":\"Principals & administration\",\"contents\":\"Principals and assistant principals, campus front offices, the superintendent's office, and central business functions.\",\"codes\":\"TEA functions 21, 23, 41, 92\",\"columns\":[\"leadership_admin\"],\"components\":[],\"amount\":232463626,\"per_student\":1663,\"cents\":7,\"cents_prev\":9,\"peer_cents\":7,\"state_cents\":11,\"peer_per_student\":1151,\"state_per_student\":1803,\"dollars_vs_peers\":71531368},{\"key\":\"facilities\",\"label\":\"Buildings & upkeep\",\"contents\":\"Custodians, electricity and water, groundskeeping, and the repairs that keep buildings open.\",\"codes\":\"TEA function 51\",\"columns\":[\"facilities_maintenance\"],\"components\":[],\"amount\":190226926,\"per_student\":1361,\"cents\":6,\"cents_prev\":7,\"peer_cents\":6,\"state_cents\":10,\"peer_per_student\":1186,\"state_per_student\":1717,\"dollars_vs_peers\":24501279},{\"key\":\"transport_food\",\"label\":\"Buses & meals\",\"contents\":\"School buses, routes and drivers, plus cafeterias and the food served in them.\",\"codes\":\"TEA functions 34, 35\",\"columns\":[\"transportation\",\"food_service\"],\"components\":[{\"label\":\"School buses\",\"amount\":71975189},{\"label\":\"Cafeterias & food\",\"amount\":109777955}],\"amount\":181753144,\"per_student\":1300,\"cents\":5,\"cents_prev\":7,\"peer_cents\":5,\"state_cents\":6,\"peer_per_student\":989,\"state_per_student\":1187,\"dollars_vs_peers\":43534963},{\"key\":\"support\",\"label\":\"Counselors, nurses & support\",\"contents\":\"Counselors, social workers, and school nurses.\",\"codes\":\"TEA functions 31, 32, 33\",\"columns\":[\"student_support\"],\"components\":[],\"amount\":131385802,\"per_student\":940,\"cents\":4,\"cents_prev\":4,\"peer_cents\":4,\"state_cents\":3,\"peer_per_student\":727,\"state_per_student\":574,\"dollars_vs_peers\":29812730},{\"key\":\"safety_tech\",\"label\":\"Safety & technology\",\"contents\":\"Campus security and policing, plus the district's computers, networks, and data systems. (Technology cannot be separated from security in this dataset.)\",\"codes\":\"TEA functions 52, 53\",\"columns\":[\"safety_technology\"],\"components\":[],\"amount\":90230486,\"per_student\":646,\"cents\":3,\"cents_prev\":2,\"peer_cents\":2,\"state_cents\":3,\"peer_per_student\":420,\"state_per_student\":563,\"dollars_vs_peers\":31562954},{\"key\":\"extracurricular\",\"label\":\"Sports & activities\",\"contents\":\"Athletics, band, UIL academics, clubs, and other activities outside class time.\",\"codes\":\"TEA function 36\",\"columns\":[\"extracurricular\"],\"components\":[],\"amount\":49377351,\"per_student\":353,\"cents\":1,\"cents_prev\":1,\"peer_cents\":2,\"state_cents\":3,\"peer_per_student\":336,\"state_per_student\":659,\"dollars_vs_peers\":2370918},{\"key\":\"community\",\"label\":\"Community services\",\"contents\":\"Programs the district runs for the wider community, such as adult education and parent outreach.\",\"codes\":\"TEA function 61\",\"columns\":[\"community_services\"],\"components\":[],\"amount\":18123871,\"per_student\":130,\"cents\":1,\"cents_prev\":1,\"peer_cents\":0,\"state_cents\":0,\"peer_per_student\":97,\"state_per_student\":2,\"dollars_vs_peers\":4524891},{\"key\":\"other\",\"label\":\"Everything else\",\"contents\":\"Everything the function codes above do not capture — including transfers between funds and smaller categories TEA does not break out separately.\",\"codes\":\"residual: total spending minus the categories above\",\"columns\":[],\"components\":[],\"amount\":66548721,\"per_student\":476,\"cents\":2,\"cents_prev\":2,\"peer_cents\":2,\"state_cents\":2,\"peer_per_student\":null,\"state_per_student\":null,\"dollars_vs_peers\":null}]}"),
  '061910': JSON.parse("{\"district_number\":\"061910\",\"district_name\":\"ARGYLE ISD\",\"year\":2025,\"prev_year\":2020,\"enrollment\":6114,\"total_spend\":193842830,\"per_student\":31705,\"peer_count\":12,\"state_count\":1202,\"parts\":[{\"key\":\"construction\",\"label\":\"Construction\",\"contents\":\"New buildings, major renovations, land, and large equipment purchases.\",\"codes\":\"TEA object 6600\",\"columns\":[\"capital_projects\"],\"components\":[],\"amount\":98300926,\"per_student\":16078,\"cents\":51,\"cents_prev\":44,\"peer_cents\":48,\"state_cents\":6,\"peer_per_student\":15042,\"state_per_student\":1042,\"dollars_vs_peers\":6333270},{\"key\":\"classroom\",\"label\":\"Classroom teaching\",\"contents\":\"Teachers' pay and benefits, classroom materials, school libraries and media specialists, and training for teachers.\",\"codes\":\"TEA functions 11, 12, 13\",\"columns\":[\"classroom_instruction\"],\"components\":[],\"amount\":36246162,\"per_student\":5928,\"cents\":19,\"cents_prev\":25,\"peer_cents\":22,\"state_cents\":47,\"peer_per_student\":6785,\"state_per_student\":7833,\"dollars_vs_peers\":-5237693},{\"key\":\"debt\",\"label\":\"Debt payments\",\"contents\":\"Principal and interest on bonds voters approved in past elections — mostly for buildings that are already standing.\",\"codes\":\"TEA object 6500\",\"columns\":[\"debt_service\"],\"components\":[],\"amount\":31498615,\"per_student\":5152,\"cents\":16,\"cents_prev\":14,\"peer_cents\":14,\"state_cents\":9,\"peer_per_student\":4196,\"state_per_student\":1537,\"dollars_vs_peers\":5842812},{\"key\":\"facilities\",\"label\":\"Buildings & upkeep\",\"contents\":\"Custodians, electricity and water, groundskeeping, and the repairs that keep buildings open.\",\"codes\":\"TEA function 51\",\"columns\":[\"facilities_maintenance\"],\"components\":[],\"amount\":7306663,\"per_student\":1195,\"cents\":4,\"cents_prev\":4,\"peer_cents\":3,\"state_cents\":10,\"peer_per_student\":1156,\"state_per_student\":1717,\"dollars_vs_peers\":241335},{\"key\":\"admin\",\"label\":\"Principals & administration\",\"contents\":\"Principals and assistant principals, campus front offices, the superintendent's office, and central business functions.\",\"codes\":\"TEA functions 21, 23, 41, 92\",\"columns\":[\"leadership_admin\"],\"components\":[],\"amount\":6283209,\"per_student\":1028,\"cents\":3,\"cents_prev\":4,\"peer_cents\":4,\"state_cents\":11,\"peer_per_student\":1101,\"state_per_student\":1803,\"dollars_vs_peers\":-446642},{\"key\":\"transport_food\",\"label\":\"Buses & meals\",\"contents\":\"School buses, routes and drivers, plus cafeterias and the food served in them.\",\"codes\":\"TEA functions 34, 35\",\"columns\":[\"transportation\",\"food_service\"],\"components\":[{\"label\":\"School buses\",\"amount\":2599207},{\"label\":\"Cafeterias & food\",\"amount\":3274034}],\"amount\":5873241,\"per_student\":961,\"cents\":3,\"cents_prev\":3,\"peer_cents\":3,\"state_cents\":6,\"peer_per_student\":1028,\"state_per_student\":1187,\"dollars_vs_peers\":-413798},{\"key\":\"support\",\"label\":\"Counselors, nurses & support\",\"contents\":\"Counselors, social workers, and school nurses.\",\"codes\":\"TEA functions 31, 32, 33\",\"columns\":[\"student_support\"],\"components\":[],\"amount\":2837209,\"per_student\":464,\"cents\":2,\"cents_prev\":2,\"peer_cents\":2,\"state_cents\":3,\"peer_per_student\":588,\"state_per_student\":574,\"dollars_vs_peers\":-756189},{\"key\":\"extracurricular\",\"label\":\"Sports & activities\",\"contents\":\"Athletics, band, UIL academics, clubs, and other activities outside class time.\",\"codes\":\"TEA function 36\",\"columns\":[\"extracurricular\"],\"components\":[],\"amount\":2673412,\"per_student\":437,\"cents\":1,\"cents_prev\":2,\"peer_cents\":2,\"state_cents\":3,\"peer_per_student\":436,\"state_per_student\":659,\"dollars_vs_peers\":5359},{\"key\":\"safety_tech\",\"label\":\"Safety & technology\",\"contents\":\"Campus security and policing, plus the district's computers, networks, and data systems. (Technology cannot be separated from security in this dataset.)\",\"codes\":\"TEA functions 52, 53\",\"columns\":[\"safety_technology\"],\"components\":[],\"amount\":2105378,\"per_student\":344,\"cents\":1,\"cents_prev\":1,\"peer_cents\":2,\"state_cents\":3,\"peer_per_student\":478,\"state_per_student\":563,\"dollars_vs_peers\":-819478},{\"key\":\"community\",\"label\":\"Community services\",\"contents\":\"Programs the district runs for the wider community, such as adult education and parent outreach.\",\"codes\":\"TEA function 61\",\"columns\":[\"community_services\"],\"components\":[],\"amount\":0,\"per_student\":0,\"cents\":0,\"cents_prev\":0,\"peer_cents\":0,\"state_cents\":0,\"peer_per_student\":11,\"state_per_student\":2,\"dollars_vs_peers\":-66516},{\"key\":\"other\",\"label\":\"Everything else\",\"contents\":\"Everything the function codes above do not capture — including transfers between funds and smaller categories TEA does not break out separately.\",\"codes\":\"residual: total spending minus the categories above\",\"columns\":[],\"components\":[],\"amount\":718015,\"per_student\":117,\"cents\":0,\"cents_prev\":1,\"peer_cents\":0,\"state_cents\":2,\"peer_per_student\":null,\"state_per_student\":null,\"dollars_vs_peers\":null}]}"),
};

function endpointMap() {
  return new Map(Object.entries(fixture.routes).map(([key, route]) => [route, key]));
}

async function installPublicFixtures(page, options = {}) {
  const endpoints = endpointMap();
  const baseOrigin = new URL(options.baseURL || process.env.TISD_BASE_URL || 'http://127.0.0.1:8787').origin;
  const blocked = options.blockedRequests || [];
  const requests = options.requests || [];
  const unavailable = !!options.unavailable;
  await page.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    requests.push(`${request.method()} ${url.pathname}${url.search}`);
    if (url.pathname === '/district-geo' && options.geoDelayMs) {
      await new Promise(resolve => setTimeout(resolve, options.geoDelayMs));
    }
    if (url.origin !== baseOrigin) {
      blocked.push(request.url());
      return route.abort('blockedbyclient');
    }
    const routePath = `${url.pathname}${url.search}`;
    if (MUTATING_PATHS.has(url.pathname) || request.method() !== 'GET') {
      blocked.push(`${request.method()} ${routePath}`);
      return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"blocked by browser fixture"}' });
    }
    if (url.pathname === '/districts' && url.searchParams.has('search')) {
      const needle = (url.searchParams.get('search') || '').toLowerCase();
      const rows = SEARCH_ROWS.filter(([, name]) => name.toLowerCase().includes(needle))
        .map(([district_number, district_name]) => ({ district_number, district_name }));
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(rows) });
    }
    if (url.pathname === '/district-geo' && options.geoPatches) {
      const patched = structuredClone(districtGeo);
      for (const [id, metrics] of Object.entries(options.geoPatches)) {
        if (!patched.d[id]) throw new Error(`test-only geo patch references unknown district ${id}`);
        patched.d[id].m = { ...(patched.d[id].m || {}), ...metrics };
      }
      return route.fulfill({
        contentType: 'application/json',
        headers: { 'x-txisd-test-fixture': 'synthetic-edge-case' },
        body: JSON.stringify(patched),
      });
    }
    if (url.pathname === '/district/061910/summary') {
      if (unavailable) return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"fixture unavailable"}' });
      return route.fulfill({
        contentType: 'application/json',
        headers: { 'x-txisd-fixture-origin': 'read-only-public-evidence' },
        body: JSON.stringify([argyleEvidence.row]),
      });
    }
    const dollarMatch = url.pathname.match(/^\/district\/(057905|061910)\/dollar$/);
    if (dollarMatch) {
      if (unavailable) return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"fixture unavailable"}' });
      const id = dollarMatch[1];
      return route.fulfill({
        contentType: 'application/json',
        headers: {
          'x-txisd-fixture-origin': 'read-only-public-evidence',
          'x-txisd-source-sha256': id === '057905'
            ? '2c02553325e9b62e18b5bf877e8a9cf37a063447e9b3a9dcc17b811403dae26d'
            : '66769cfa53a3a3ac88fa422b13325911e276873facb9460bc4f2414252b387c3',
        },
        body: JSON.stringify(DOLLAR_EVIDENCE[id]),
      });
    }
    if (url.pathname === '/district/061910/peers') {
      if (unavailable) return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"fixture unavailable"}' });
      return route.fulfill({
        contentType: 'application/json',
        headers: {
          'x-txisd-fixture-origin': 'read-only-public-evidence-projection',
          'x-txisd-source-sha256': '0515e88e227707c27966607b99785902beb1ce91e1905a6fd9f9bd99cf8fb516',
        },
        body: JSON.stringify(ARGYLE_PEERS_EVIDENCE),
      });
    }
    const argyleOptional = url.pathname.match(/^\/district\/061910\/(turnarounds|insights)$/);
    if (argyleOptional) {
      if (unavailable) return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"fixture unavailable"}' });
      const key = argyleOptional[1];
      return route.fulfill({
        contentType: 'application/json',
        headers: {
          'x-txisd-fixture-origin': 'read-only-public-evidence',
          'x-txisd-source-sha256': key === 'turnarounds'
            ? '20705c14fd09b0ef4e55f1ec7f8977d637dee9a1f9e489b8fe05e7edcb9a4313'
            : '10c7321ed9fc14bc494b7f0e103adf49732abbef7cf26b040c5c366400f867d5',
        },
        body: JSON.stringify(ARGYLE_OPTIONAL_EVIDENCE[key]),
      });
    }
    if (/^\/district\/061910\/(breakdown|spending-detail)$/.test(url.pathname)
        || (url.pathname === '/anomalies' && url.searchParams.get('district_number') === '061910')) {
      return route.fulfill({ contentType: 'application/json', body: '[]' });
    }
    const key = endpoints.get(routePath);
    if (key) {
      if (unavailable) return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"fixture unavailable"}' });
      return route.fulfill({ contentType: 'application/json', body: JSON.stringify(fixture.payloads[key]) });
    }
    return route.continue();
  });
}

async function cleanState(page, theme = 'light') {
  await page.addInitScript(({ theme }) => {
    // addInitScript runs for every navigation in the same page.  Reset once,
    // then retain state so cross-page district handoffs are actually tested.
    if (sessionStorage.getItem('__public_fixture_initialized') !== '1') {
      localStorage.clear(); sessionStorage.clear();
      sessionStorage.setItem('__public_fixture_initialized', '1');
      if (theme === 'dark') localStorage.setItem('tisd_theme', 'dark');
    }
  }, { theme });
}

async function waitForDashboard(page) {
  await page.waitForFunction(() => {
    const dash = document.querySelector('#dash');
    const name = document.querySelector('#dname');
    return dash && !dash.classList.contains('hidden') && !!name?.textContent.trim();
  }, null, { timeout: 15000 });
}

async function waitForMap(page, mapSelector = '#map') {
  await page.waitForFunction(selector => {
    const map = document.querySelector(selector);
    const table = document.querySelector('#a11y-table');
    const rect = map?.getBoundingClientRect();
    return !!map && rect.width > 100 && rect.height > 100
      && !!table?.querySelector('tbody tr');
  }, mapSelector, { timeout: 20000 });
}

module.exports = { fixture, installPublicFixtures, cleanState, waitForDashboard, waitForMap };
