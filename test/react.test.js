import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { BookLibrary, BookReader } from '../src/react.js';
test('React adapters render safely on the server before mounting browser UI', () => {
  assert.equal(renderToStaticMarkup(createElement(BookLibrary, { className: 'books', baseUrl: '/books/' })), '<div class="books"></div>');
  assert.equal(renderToStaticMarkup(createElement(BookReader, { book: {id:'1',title:'Toán',pages:[],covers:{}} })), '<div></div>');
});
