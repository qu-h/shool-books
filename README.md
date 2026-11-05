# @nhat-minh/school-books

Package thư viện sách và trình đọc có hiệu ứng lật trang 3D, dùng được với JavaScript thuần, React và Next.js. Toàn bộ giao diện, CSS và bộ nhập dữ liệu nằm trong package; không phụ thuộc Tailwind, jQuery hay dịch vụ đọc sách bên ngoài.

Nguồn: [Thư viện sách giáo khoa OLM](https://olm.vn/thu-vien-so/sach-giao-khoa?grade=2&role=student). Theo phạm vi đã chọn, tải đầy đủ sách học sinh và sách giáo viên **lớp 2 trước**; danh mục lớp 1–12 vẫn được lưu để tải tiếp. `data/sync-report.json` ghi kết quả lần đồng bộ gần nhất. Không coi sách chỉ có metadata là đã tải đủ nội dung.

Bản dữ liệu hiện tại: **23 cuốn lớp 2** (14 sách học sinh, 9 sách giáo viên), **2.602 trang nội dung**, đầy đủ bìa và ảnh trang ngoại tuyến. Danh mục giữ **552 cuốn lớp 1–12**; các lớp còn lại mới có metadata và bìa, chưa tải đầy đủ trang sách. Tổng ảnh hiện lưu khoảng 2,1 GiB.

## Chạy thử

```sh
npm install
npm run demo
```

Mở `http://localhost:4187/examples/`. Demo dùng dữ liệu tại chỗ và không gọi OLM khi đọc sách. Chọn Lớp 2 để đọc các sách đã tải đầy đủ.

Trình đọc có chế độ hai trang trên máy tính, một trang trên điện thoại, chuyển trang bằng nút, phím mũi tên hoặc vuốt, nhập vị trí trang, Home/End, phóng to/thu nhỏ, toàn màn hình và ghi nhớ vị trí đọc theo sách. Hiệu ứng tự tắt khi hệ điều hành bật giảm chuyển động. Bìa trùng ảnh trang đầu/cuối được bỏ trùng. Ảnh trang được tải khi cần, không đưa cả cuốn vào DOM.

## Publish dữ liệu và ảnh lên GitHub Pages

Workflow `.github/workflows/pages.yml` tự build và deploy khi push thay đổi dữ liệu, source hoặc cấu hình lên `main`; có thể chạy tay bằng **Actions → Deploy book library to GitHub Pages → Run workflow**.

Thiết lập một lần trên repository `qu-h/shool-books`:

1. Push cấu hình mới và đầy đủ dữ liệu `data/` lên GitHub.
2. Vào **Settings → Pages → Build and deployment → Source**, chọn **GitHub Actions**.
3. Chạy workflow và chờ job `deploy` thành công. URL chính xác nằm trong environment `github-pages` của lần chạy.

Với repository hiện tại, URL dự kiến sau deploy:

- Thư viện đọc thử: `https://qu-h.github.io/shool-books/`
- Danh mục: `https://qu-h.github.io/shool-books/data/catalog.json`
- Nội dung sách: `https://qu-h.github.io/shool-books/data/books/<id>.json`
- Ảnh: ghép URL `https://qu-h.github.io/shool-books/data/` với trường `cover` hoặc `path` lấy từ JSON đã publish.

Site khác có thể dùng trực tiếp dữ liệu, không cần chép vào thư mục public:

```tsx
<BookLibrary baseUrl="https://qu-h.github.io/shool-books/data/" />
```

Hoặc lấy JSON trong JavaScript:

```js
const baseUrl = 'https://qu-h.github.io/shool-books/data/';
const catalog = await fetch(`${baseUrl}catalog.json`).then(response => response.json());
const book = await fetch(new URL(catalog[0].manifest, baseUrl)).then(response => response.json());
const coverUrl = new URL(catalog[0].cover, baseUrl).href;
```

Bản publish đổi ảnh sang **WebP chất lượng 85**, giữ kích thước ảnh, và cập nhật `path`, `cover`, `bytes`, `sha256` theo ảnh đã chuyển. Đây là nén có mất dữ liệu; luôn đọc đường dẫn từ JSON trên Pages thay vì dùng đường dẫn PNG/JPEG của dữ liệu gốc. Dữ liệu gốc không bị thay đổi. Chỉ những ảnh được tham chiếu trong danh mục/manifest được xuất bản; trạng thái sách chưa tải đủ vẫn được giữ nguyên.

GitHub Pages giới hạn site ở 1 GB ([GitHub Docs](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)). Script kiểm tra artifact dưới 900 MiB và dừng build nếu vượt ngưỡng, trước khi deploy. Nếu dữ liệu tăng vượt mức này, cần giảm chất lượng ảnh, chia thư viện hoặc chuyển ảnh sang dịch vụ lưu trữ khác. Không tải ảnh mới từ OLM trong workflow; dữ liệu phải có sẵn trong Git.

Build và xem bản publish tại máy:

```sh
python3 -m pip install -r scripts/requirements-pages.txt
npm run build:pages
python3 -m http.server 4188 --directory dist
```

Mở `http://localhost:4188/`. `dist/` chỉ chứa bản publish và được bỏ qua trong Git. Thư mục HTML nguồn `data/sources/`, báo cáo đồng bộ và công cụ nhập dữ liệu không được đưa lên Pages.

## Tích hợp React / Next.js

Cài từ thư mục package:

```sh
npm install /mnt/data/Node.js/packages/shool-books
```

Chép dữ liệu sang thư mục public của **project sử dụng** (chạy tại project đó):

```sh
mkdir -p public/school-books
cp node_modules/@nhat-minh/school-books/data/catalog.json public/school-books/
cp -R node_modules/@nhat-minh/school-books/data/books public/school-books/
cp -R node_modules/@nhat-minh/school-books/data/assets public/school-books/
```

Import CSS ở layout hoặc entry của ứng dụng:

```tsx
import '@nhat-minh/school-books/styles.css';
```

Component trang:

```tsx
'use client';

import { BookLibrary } from '@nhat-minh/school-books/react';

export default function BooksPage() {
  return <BookLibrary baseUrl="/school-books/" />;
}
```

Chỉ đọc một cuốn:

```tsx
'use client';

import { BookReader } from '@nhat-minh/school-books/react';
import type { Book } from '@nhat-minh/school-books';

export function Reader({ book }: { book: Book }) {
  return <BookReader book={book} baseUrl="/school-books/" />;
}
```

`book` là nội dung JSON trong `data/books/<id>.json`. Có thể lấy bằng `loadBook(entry, { baseUrl })`. Không import toàn bộ thư mục sách vào bundle. Adapter React có chỉ thị `use client`; core an toàn khi import ở server vì chỉ truy cập DOM lúc mount.

## JavaScript thuần

Dùng bundler:

```js
import { createBookLibrary } from '@nhat-minh/school-books';
import '@nhat-minh/school-books/styles.css';

const library = createBookLibrary(document.getElementById('books'), {
  baseUrl: '/school-books/',
  onBookOpen(book) { console.log(book.title); },
});
await library.ready;
// Khi tháo giao diện:
library.destroy();
```

Hoặc phục vụ `src/index.js` và `src/styles.css` trực tiếp dưới dạng ES module như trong `examples/index.html`. Runtime core không cần cài dependency nào.

Các hàm export: `createBookLibrary`, `createBookReader`, `loadCatalog`, `loadBook`, `filterBooks`, `assetUrl`, `clampPage`. TypeScript declarations nằm cạnh source.

Tùy chọn chung:

| Tùy chọn | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `baseUrl` | `/school-books/` | URL HTTP phục vụ nội dung thư mục data; hỗ trợ CDN và ứng dụng nằm ở đường dẫn con |
| `allowRemote` | `false` | Cho phép dùng URL nguồn khi ảnh chưa được tải về; cần kết nối mạng |
| `remember` | `true` | Lưu vị trí đọc trong localStorage khi trình duyệt cho phép |
| `initialPage` | vị trí đã lưu hoặc `0` | Chỉ số vị trí trong trình đọc, bắt đầu từ 0, gồm bìa nếu có |
| `onPageChange` | — | Callback `(pageIndex, book)` |
| `books` | tải `catalog.json` | Danh mục tự truyền cho thư viện |
| `onBookOpen` | — | Callback khi mở sách thành công |

`createBookReader()` trả `{ goTo, getPage, destroy }`; `createBookLibrary()` trả `{ ready, open, destroy }`. Mỗi instance có trạng thái riêng, hủy request khi tháo thư viện và bỏ qua phản hồi mở sách cũ khi người đọc đổi lựa chọn.

## Dữ liệu và đồng bộ

```text
data/
  catalog.json           Danh mục nhẹ: tên, lớp, loại sách, bìa, trạng thái
  books/<id>.json        Metadata và danh sách trang của từng cuốn
  assets/<id>/           Bìa và ảnh trang gốc, tách khỏi source
  sources/<id>.html.gz   Bản HTML nguồn nén phục vụ nhập lại, không đóng vào npm
  sync-report.json       Phạm vi, thời điểm, số lượng và lỗi đồng bộ
```

Mỗi ảnh lưu đường dẫn tương đối `path`, URL nguồn `sourceUrl`, dung lượng `bytes` và checksum `sha256`. `metadataComplete` yêu cầu số URL trang khớp số trang nguồn và lớn hơn 0. `offlineComplete` chỉ đúng khi metadata đủ và tất cả trang/bìa đã tải về. Đường dẫn không phụ thuộc máy cài package.

Bộ nhập dùng Python 3.10+ và thư viện chuẩn, không yêu cầu pip. Nó đọc API danh mục công khai, phân tích JSON trong cấu hình reader, giữ kết nối HTTPS giữa các lần tải, khóa thư mục để tránh chạy hai lượt đồng bộ cùng lúc, tải có giới hạn luồng, thử lại lỗi mạng, xác nhận định dạng ảnh và ghi file nguyên tử. Không thực thi JavaScript nguồn hay suy đoán URL trang.

```sh
# Metadata và bìa của cả 12 lớp; ảnh trang ưu tiên lớp 2:
python3 scripts/sync_olm.py --grades 2 1 3 4 5 6 7 8 9 10 11 12 --asset-grades 2 --workers 8

# Chỉ cập nhật metadata, giữ thông tin ảnh đã tải:
npm run sync -- --metadata-only

# Tải toàn bộ lớp 1–12 khi đã có đủ dung lượng:
npm run sync -- --workers 4

# Lưu bộ dữ liệu vào ổ khác:
npm run sync -- --output /duong-dan-o-lon/school-books-data

# Kiểm tra sự tồn tại và SHA-256 của toàn bộ dữ liệu lớp 2:
npm run verify:data

# Kiểm tra toàn bộ 12 lớp (báo thiếu nếu chưa tải hết):
python3 scripts/sync_olm.py --verify
```

Mặc định giữ ít nhất 1.024 MiB dung lượng trống, điều chỉnh bằng `--min-free-mb`. Chạy lại cùng lệnh sẽ dùng các file đã tải; thêm `--refresh` để đọc lại HTML sách từ nguồn. Khi dừng bằng Ctrl+C, bộ tải hoàn thành các request đang chạy, lưu trạng thái và báo phần chưa hoàn tất. Phạm vi `--grades` quyết định danh mục đầu ra; `--asset-grades` chỉ giới hạn tải **ảnh trang**, vẫn tải bìa và giữ metadata của toàn danh mục.

Nguồn hiện có một mục “Tiếng Nhật” lớp 8 không cung cấp trang nào; manifest giữ `metadataComplete: false`. Nó không ảnh hưởng phạm vi tải lớp 2. Bộ dữ liệu là ảnh trang được nguồn công bố, không tự tạo PDF hoặc gọi là có PDF khi nguồn không cung cấp file đó. Bản quyền nội dung sách thuộc các chủ sở hữu được nguồn công bố; package không thay đổi quyền đối với nội dung.

## Kiểm thử

Các test build Pages cần Pillow: `python3 -m pip install -r scripts/requirements-pages.txt`.

```sh
npm test
npm run check
npm run typecheck
npm run verify:data

# Mở demo trong một terminal trước, rồi chạy Chrome:
npm run demo
npm run test:browser
```

Browser test dùng Playwright và Chrome tại `/usr/bin/google-chrome`; đặt `CHROME_BIN` nếu Chrome nằm nơi khác, `BOOKS_DEMO_URL` nếu demo không chạy ở `http://127.0.0.1:4187`. Kiểm thử bao gồm danh mục thực, tìm không dấu, lọc lớp/loại sách, giới hạn trang, nút trước/sau, bàn phím, zoom, mobile, giảm chuyển động và tháo instance. Fixture chuyển trang không phụ thuộc CDN.

Chạy `npm pack` để tạo gói phân phối. Package chứa dữ liệu ảnh nên dung lượng đáng kể; các HTML nguồn nén chỉ dùng khi phát triển, không đóng gói. Không có bước build cần chạy trước khi sử dụng.
