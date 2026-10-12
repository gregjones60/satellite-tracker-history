const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const src = fs.readFileSync(path.join(__dirname, '../custom_components/spot_trace_history/www/spot-trace-history-card.js'), 'utf8');

test('card source retains a tile cache and removes obsolete tiles', () => {
  assert.match(src, /tileNodes=new Map\(\)/);
  assert.match(src, /this\.tileNodes\.get\(key\)/);
  assert.match(src, /!needed\.has\(key\)/);
});
test('tile requests use a safe referrer policy and configurable provider', () => {
  assert.match(src, /strict-origin-when-cross-origin/);
  assert.match(src, /tile_url/);
});
test('multi-device configuration and route display remain available', () => {
  assert.match(src, /deviceSettings/);
  assert.match(src, /entry_id/);
});
