/** Framework-independent book data and UI. Safe to import during SSR. */
export function filterBooks(books, { query = '', grade, role } = {}) {
  const normalize = value => String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/đ/g, 'd');
  const needle = normalize(query.trim());
  return books.filter(book => (!grade || book.grade === Number(grade)) && (!role || book.role === role) && normalize(book.title).includes(needle));
}

export function assetUrl(path, baseUrl = '/school-books/') {
  if (!path) return '';
  if (/^https?:\/\//i.test(path)) return path;
  if (path.startsWith('/') || path.split('/').includes('..')) throw new Error('Asset paths must be relative to data');
  return `${baseUrl.replace(/\/$/, '')}/${path}`;
}

export async function loadCatalog({ baseUrl = '/school-books/', signal } = {}) {
  return fetchJson(assetUrl('catalog.json', baseUrl), signal);
}

export async function loadBook(entry, { baseUrl = '/school-books/', signal } = {}) {
  return fetchJson(assetUrl(entry.manifest || `books/${entry.id}.json`, baseUrl), signal);
}

async function fetchJson(url, signal) {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`Không tải được dữ liệu (${response.status})`);
  return response.json();
}

export function clampPage(page, count) {
  return Math.max(0, Math.min(Math.max(0, count - 1), Math.trunc(Number(page)) || 0));
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function button(label, action, text = label) {
  const node = el('button', 'sb-button', text);
  node.type = 'button';
  node.setAttribute('aria-label', label);
  node.addEventListener('click', action);
  return node;
}
function readProgress(key) {
  try { return Number(localStorage.getItem(key)) || 0; } catch { return 0; }
}

/** Mount a reader. The returned controller must be destroyed on unmount. */
export function createBookReader(container, book, options = {}) {
  const { baseUrl = '/school-books/', allowRemote = false, onPageChange, remember = true } = options;
  const body = book.pages || [];
  const front = book.covers?.first;
  const back = book.covers?.last;
  const sameAsset = (a, b) => a && b && ((a.sourceUrl && a.sourceUrl === b.sourceUrl) || (a.path && a.path === b.path));
  const pages = [sameAsset(front, body[0]) ? null : front, ...body, sameAsset(back, body.at(-1)) ? null : back].filter(Boolean);
  const storageKey = `school-books:${book.id}:page`;
  let current = clampPage(options.initialPage ?? (remember ? readProgress(storageKey) : 0), pages.length);
  let zoom = 1;
  let timer;
  let destroyed = false;
  let touchX = null;
  const root = el('section', 'sb-reader');
  root.tabIndex = 0;
  root.setAttribute('aria-label', `Đọc sách ${book.title}`);
  const header = el('header', 'sb-reader-header');
  const heading = el('h2', '', book.title);
  const badge = el('span', 'sb-badge', book.role === 'teacher' ? 'Sách giáo viên' : 'Sách học sinh');
  header.append(heading, badge);
  const stage = el('div', 'sb-stage');
  const spread = el('div', 'sb-spread');
  const left = el('div', 'sb-paper sb-paper-left');
  const right = el('div', 'sb-paper sb-paper-right');
  const turning = el('div', 'sb-turning');
  turning.setAttribute('aria-hidden', 'true');
  spread.append(left, right, turning);
  stage.append(spread);
  const status = el('p', 'sb-status');
  status.setAttribute('aria-live', 'polite');
  const controls = el('div', 'sb-controls');
  const previous = button('Trang trước', () => goTo(current - (media.matches || current <= 1 ? 1 : 2)), '←');
  const next = button('Trang sau', () => goTo(current + step()), '→');
  const input = el('input', 'sb-page-input');
  input.type = 'number'; input.min = '1'; input.max = String(pages.length); input.setAttribute('aria-label', 'Đến trang');
  input.addEventListener('change', () => goTo(Number(input.value) - 1));
  const total = el('span', '', `/ ${pages.length}`);
  const zoomOut = button('Thu nhỏ', () => setZoom(zoom - .25), '−');
  const zoomIn = button('Phóng to', () => setZoom(zoom + .25), '+');
  const fullscreen = button('Toàn màn hình', async () => {
    try {
      if (document.fullscreenElement === root) await document.exitFullscreen();
      else if (root.requestFullscreen) await root.requestFullscreen();
      else status.textContent = 'Trình duyệt chưa hỗ trợ toàn màn hình.';
    } catch { status.textContent = 'Không mở được toàn màn hình.'; }
  }, '⛶');
  controls.append(previous, input, total, next, zoomOut, zoomIn, fullscreen);
  root.append(header, stage, status, controls);
  container.replaceChildren(root);
  const media = window.matchMedia('(max-width: 640px)');
  function step() { return media.matches || current === 0 ? 1 : 2; }
  function pageSource(item) { return item?.path ? assetUrl(item.path, baseUrl) : allowRemote ? item?.sourceUrl : ''; }
  function renderPage(target, index) {
    target.replaceChildren();
    const item = pages[index];
    if (!item) { target.append(el('div', 'sb-blank')); return; }
    const url = pageSource(item);
    if (!url) { target.append(el('p', 'sb-missing', 'Trang này chưa có dữ liệu ngoại tuyến.')); return; }
    const img = el('img', 'sb-page-image');
    img.alt = `${book.title} — ${index === 0 && book.covers?.first ? 'Bìa trước' : `Trang ${item.number || index + 1}`}`;
    img.draggable = false;
    img.addEventListener('error', () => {
      if (img.parentNode !== target) return;
      const message = el('div', 'sb-missing', 'Không tải được ảnh trang sách.');
      message.append(button('Thử lại', () => renderPage(target, index)));
      target.replaceChildren(message);
    }, { once: true });
    img.src = url;
    target.append(img);
  }
  function render() {
    const single = media.matches || current === 0;
    spread.classList.toggle('sb-single', single);
    renderPage(left, current);
    renderPage(right, single ? -1 : current + 1);
    input.value = String(current + 1);
    previous.disabled = current === 0;
    next.disabled = current >= pages.length - 1 || (!single && current + 1 >= pages.length);
    status.textContent = pages.length ? `Trang ${current + 1}${!single && current + 1 < pages.length ? `–${current + 2}` : ''} trên ${pages.length}` : 'Sách chưa có trang để hiển thị.';
    // Warm only the next two pages rather than inserting the entire book into the DOM.
    for (let i = current + 1; i <= Math.min(current + 3, pages.length - 1); i++) {
      const url = pageSource(pages[i]);
      if (url) { const img = new Image(); img.src = url; }
    }
  }
  function goTo(page) {
    if (destroyed) return;
    const target = clampPage(page, pages.length);
    if (target === current) { input.value = String(current + 1); return; }
    clearTimeout(timer);
    const forward = target > current;
    turning.className = 'sb-turning';
    renderPage(turning, forward ? current : target);
    turning.style.transformOrigin = forward ? 'left center' : 'right center';
    // Restart a CSS animation without leaving the navigation state waiting on animationend.
    void turning.offsetWidth;
    turning.classList.add(forward ? 'sb-flip-forward' : 'sb-flip-back');
    current = target;
    render();
    timer = setTimeout(() => { turning.className = 'sb-turning'; turning.replaceChildren(); }, 620);
    if (remember) { try { localStorage.setItem(storageKey, String(current)); } catch { /* optional persistence */ } }
    onPageChange?.(current, book);
  }
  function setZoom(value) {
    zoom = Math.max(.75, Math.min(3, value));
    spread.style.setProperty('--sb-zoom', String(zoom));
    zoomOut.disabled = zoom <= .75; zoomIn.disabled = zoom >= 3;
  }
  const keyboard = event => {
    if (['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON'].includes(event.target.tagName) || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === 'ArrowRight') { event.preventDefault(); goTo(current + step()); }
    if (event.key === 'ArrowLeft') { event.preventDefault(); goTo(current - (media.matches || current <= 1 ? 1 : 2)); }
    if (event.key === 'Home') { event.preventDefault(); goTo(0); }
    if (event.key === 'End') { event.preventDefault(); goTo(pages.length - 1); }
  };
  root.addEventListener('keydown', keyboard);
  stage.addEventListener('pointerdown', event => { if (zoom === 1) touchX = event.clientX; });
  stage.addEventListener('pointerup', event => {
    if (touchX !== null && Math.abs(event.clientX - touchX) > 55) goTo(current + (event.clientX < touchX ? step() : -step()));
    touchX = null;
  });
  stage.addEventListener('pointercancel', () => { touchX = null; });
  media.addEventListener('change', render);
  render();
  return { goTo, getPage: () => current, destroy() {
    destroyed = true; clearTimeout(timer); media.removeEventListener('change', render); root.remove();
  } };
}

/** Mount a searchable library with a fully contained reader. */
export function createBookLibrary(container, options = {}) {
  const { baseUrl = '/school-books/', allowRemote = false, onBookOpen } = options;
  const abort = new AbortController();
  let books = options.books || [];
  let reader;
  let disposed = false;
  let requestId = 0;
  const root = el('section', 'sb-library');
  const hero = el('header', 'sb-hero');
  hero.append(el('span', 'sb-eyebrow', 'MỖI TRANG SÁCH, MỘT KHÁM PHÁ'), el('h1', '', 'Thư viện sách của em'), el('p', '', 'Mở một cuốn sách. Khám phá cả thế giới.'));
  const filters = el('div', 'sb-filters');
  const query = el('input', 'sb-search'); query.type = 'search'; query.placeholder = 'Tìm tên sách…'; query.setAttribute('aria-label', 'Tìm sách');
  const grade = el('select', 'sb-select'); grade.setAttribute('aria-label', 'Chọn lớp');
  grade.append(new Option('Tất cả lớp', ''));
  for (let i = 1; i <= 12; i++) grade.append(new Option(`Lớp ${i}`, String(i)));
  const role = el('select', 'sb-select'); role.setAttribute('aria-label', 'Loại sách');
  role.append(new Option('Tất cả sách', ''), new Option('Sách học sinh', 'student'), new Option('Sách giáo viên', 'teacher'));
  filters.append(query, grade, role);
  const status = el('p', 'sb-results', 'Đang tải thư viện…'); status.setAttribute('aria-live', 'polite');
  const grid = el('div', 'sb-grid');
  const detail = el('div', 'sb-detail'); detail.hidden = true;
  root.append(hero, filters, status, grid, detail); container.replaceChildren(root);
  function render() {
    const visible = filterBooks(books, { query: query.value, grade: grade.value, role: role.value });
    status.textContent = visible.length ? `${visible.length} cuốn sách đang chờ bạn` : 'Chưa tìm thấy sách phù hợp.';
    grid.replaceChildren();
    for (const book of visible) {
      const card = button(`Đọc ${book.title}`, () => open(book)); card.className = 'sb-book-card'; card.replaceChildren();
      const cover = el('div', 'sb-cover');
      const url = book.cover ? assetUrl(book.cover, baseUrl) : allowRemote ? book.coverSource : '';
      if (url) {
        const img = el('img', ''); img.alt = ''; img.loading = 'lazy'; img.src = url;
        img.addEventListener('error', () => cover.replaceChildren(el('span', 'sb-cover-fallback', book.title)), { once: true });
        cover.append(img);
      } else cover.append(el('span', 'sb-cover-fallback', book.title));
      card.append(cover, el('span', 'sb-book-meta', `Lớp ${book.grade} · ${book.role === 'teacher' ? 'Giáo viên' : 'Học sinh'}`), el('strong', 'sb-book-title', book.title), el('span', 'sb-open-label', book.offlineComplete ? 'Mở sách ↗' : 'Chưa tải đủ nội dung'));
      grid.append(card);
    }
  }
  async function open(entry) {
    const id = ++requestId;
    detail.hidden = false; grid.hidden = true; filters.hidden = true; hero.hidden = true;
    reader?.destroy(); detail.replaceChildren();
    const back = button('Trở về thư viện', () => {
      ++requestId; reader?.destroy(); detail.hidden = true; grid.hidden = false; filters.hidden = false; hero.hidden = false;
      const card = [...grid.children].find(node => node.getAttribute('aria-label') === `Đọc ${entry.title}`); card?.focus();
    }, '← Thư viện');
    const mount = el('div', ''); mount.textContent = 'Đang mở sách…'; detail.append(back, mount);
    try {
      const book = entry.pages ? entry : await loadBook(entry, { baseUrl, signal: abort.signal });
      if (disposed || id !== requestId) return;
      reader = createBookReader(mount, book, { ...options, baseUrl, allowRemote });
      mount.firstElementChild?.focus(); onBookOpen?.(book);
    } catch (error) {
      if (!disposed && id === requestId) { mount.textContent = error.message; mount.append(button('Thử lại', () => open(entry))); }
    }
  }
  [query, grade, role].forEach(node => node.addEventListener(node === query ? 'input' : 'change', render));
  const ready = options.books ? Promise.resolve().then(render) : loadCatalog({ baseUrl, signal: abort.signal }).then(result => {
    if (!disposed) { books = result; render(); }
  }).catch(error => {
    if (!disposed) { status.textContent = error.message; status.append(button('Thử lại', () => {
      loadCatalog({ baseUrl, signal: abort.signal }).then(result => { if (!disposed) { books = result; render(); } }).catch(error => { if (!disposed) status.textContent = error.message; });
    })); }
  });
  return { ready, open, destroy() { disposed = true; ++requestId; abort.abort(); reader?.destroy(); root.remove(); } };
}
