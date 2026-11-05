export interface BookAsset { sourceUrl: string; path?: string; bytes?: number; sha256?: string; number?: number }
export interface BookEntry {
  id: string; title: string; grade: number; role: 'student' | 'teacher'; sourceUrl: string;
  coverSource?: string; cover?: string; manifest?: string; totalPages: number;
  metadataComplete: boolean; offlineComplete: boolean;
}
export interface Book extends BookEntry { pages: BookAsset[]; covers: Record<string, BookAsset>; downloadEnabled?: boolean }
export interface DataOptions { baseUrl?: string; signal?: AbortSignal }
export interface ReaderOptions {
  baseUrl?: string; allowRemote?: boolean; initialPage?: number; remember?: boolean;
  onPageChange?: (pageIndex: number, book: Book) => void;
}
export interface LibraryOptions extends ReaderOptions { books?: BookEntry[]; onBookOpen?: (book: Book) => void }
export interface ReaderController { goTo(pageIndex: number): void; getPage(): number; destroy(): void }
export interface LibraryController { ready: Promise<void>; open(book: BookEntry | Book): Promise<void>; destroy(): void }
export function filterBooks(books: BookEntry[], filters?: { query?: string; grade?: number | string; role?: string }): BookEntry[];
export function assetUrl(path: string, baseUrl?: string): string;
export function clampPage(page: number, count: number): number;
export function loadCatalog(options?: DataOptions): Promise<BookEntry[]>;
export function loadBook(entry: BookEntry, options?: DataOptions): Promise<Book>;
export function createBookReader(container: HTMLElement, book: Book, options?: ReaderOptions): ReaderController;
export function createBookLibrary(container: HTMLElement, options?: LibraryOptions): LibraryController;
