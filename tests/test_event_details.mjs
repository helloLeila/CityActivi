import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
const context = { URL, Intl, Date };
vm.runInNewContext(readFileSync(new URL('../static/event-details.js', import.meta.url), 'utf8'), context);
const { render, dateKeys, safeUrl } = context.CityActiviDetails;
test('rich details escape HTML and reject executable links', () => {
  const html = render({ details: { highlights: ['<script>alert(1)</script>'], registration_url: 'javascript:alert(1)', transport: { plan: '地铁' } }, sources: [] });
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('href="javascript:'));
  assert.ok(html.includes('（估算）'));
  assert.equal(safeUrl('data:text/html,test'), '');
});
test('ongoing event occupies remaining local dates without timezone shift', () => {
  const keys = dateKeys({ facts: { start_at: '2026-10-17T16:00:00Z', end_at: '2026-10-20T10:00:00Z', timezone: 'Asia/Shanghai' } }, new Date('2026-10-19T00:00:00Z'), 3);
  assert.deepEqual(Array.from(keys), ['2026-10-19', '2026-10-20']);
});
test('date-only event uses inclusive declared end date', () => {
  const keys = dateKeys({ facts: { start_at: '2026-10-17T16:00:00Z', end_at: '2026-10-20T16:00:00Z', timezone: 'Asia/Shanghai' }, details: { end_date: '2026-10-20' } }, new Date('2026-10-18T00:00:00Z'), 5);
  assert.deepEqual(Array.from(keys), ['2026-10-18', '2026-10-19', '2026-10-20']);
});
