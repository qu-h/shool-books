import type { CSSProperties, ReactElement } from 'react';
import type { Book, LibraryOptions, ReaderOptions } from './index.js';
interface ViewProps { className?: string; style?: CSSProperties }
export function BookLibrary(props: LibraryOptions & ViewProps): ReactElement;
export function BookReader(props: ReaderOptions & ViewProps & { book: Book }): ReactElement;
