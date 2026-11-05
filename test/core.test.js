import test from 'node:test';
import assert from 'node:assert/strict';
import { filterBooks, clampPage, assetUrl, loadBook, loadCatalog } from '../src/index.js';
const books = [
  { id: '1', title: 'SGK – Đạo đức', grade: 2, role: 'student' },
  { id: '2', title: 'SGV – Toán', grade: 2, role: 'teacher' },
  { id: '3', title: 'SGK – Toán', grade: 3, role: 'student' },
];
test('Vietnamese search combines grade and audience filters without mutating input', () => {
  assert.deepEqual(filterBooks(books, { query: 'dao duc', grade: '2', role: 'student' }), [books[0]]);
  assert.deepEqual(filterBooks(books, { query: 'toan', role: 'teacher' }), [books[1]]);
  assert.deepEqual(filterBooks(books, { grade: 4 }), []);
  assert.equal(books.length, 3);
});
test('page navigation clamps invalid values and empty books', () => {
  for (const [value, count, expected] of [[-1, 4, 0], [99, 4, 3], [2.8, 4, 2], [NaN, 4, 0], [4, 0, 0]]) assert.equal(clampPage(value, count), expected);
});
test('asset paths support application subdirectories and reject traversal', () => {
  assert.equal(assetUrl('books/12.json', '/app/books/'), '/app/books/books/12.json');
  assert.equal(assetUrl('assets/a.png', 'https://cdn.example.com/data'), 'https://cdn.example.com/data/assets/a.png');
  assert.throws(() => assetUrl('../secret'));
  assert.throws(() => assetUrl('/etc/passwd'));
});
test('data loader preserves cancellation and surfaces HTTP failures', async () => {
  const original = globalThis.fetch;
  const abort = new AbortController();
  try {
    globalThis.fetch = async (url, opts) => { assert.equal(url, '/data/books/1.json'); assert.equal(opts.signal, abort.signal); return { ok: true, json: async () => ({ pages: [] }) }; };
    assert.deepEqual(await loadBook({ id: '1' }, { baseUrl: '/data/', signal: abort.signal }), { pages: [] });
    globalThis.fetch = async () => ({ ok: false, status: 404 });
    await assert.rejects(loadCatalog(), /404/);
  } finally { globalThis.fetch = original; }
});
