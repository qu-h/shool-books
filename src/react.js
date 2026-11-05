'use client';
import { createElement, useEffect, useRef } from 'react';
import { createBookLibrary, createBookReader } from './index.js';

export function BookLibrary({ className, style, ...options }) {
  const ref = useRef(null);
  const { baseUrl, allowRemote, books, onBookOpen, initialPage, onPageChange, remember } = options;
  useEffect(() => {
    const controller = createBookLibrary(ref.current, { baseUrl, allowRemote, books, onBookOpen, initialPage, onPageChange, remember });
    return () => controller.destroy();
  }, [baseUrl, allowRemote, books, onBookOpen, initialPage, onPageChange, remember]);
  return createElement('div', { ref, className, style });
}

export function BookReader({ book, className, style, baseUrl, allowRemote, initialPage, onPageChange, remember }) {
  const ref = useRef(null);
  useEffect(() => {
    const controller = createBookReader(ref.current, book, { baseUrl, allowRemote, initialPage, onPageChange, remember });
    return () => controller.destroy();
  }, [book, baseUrl, allowRemote, initialPage, onPageChange, remember]);
  return createElement('div', { ref, className, style });
}
