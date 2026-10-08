const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const context = { window: { location: { href: 'https://txisd.dev/' } } };
vm.runInNewContext(fs.readFileSync('../../static/visual-components.js', 'utf8'), context);
const retention = context.window.TxisdVisual.teacherRetention;

test('six-period retention model has documented boundaries', () => {
  assert.equal(retention(0).rounded, 10);
  assert.equal(retention(100).rounded, 0);
  assert.equal(retention(20).rounded, 3);
  assert.equal(retention(16.8).rounded, 3);
  assert.equal(retention(18.1).rounded, 3);
  assert.equal(retention(null).status, 'missing');
  assert.equal(retention(-1).status, 'unverified');
  assert.equal(retention(101).status, 'unverified');
});
