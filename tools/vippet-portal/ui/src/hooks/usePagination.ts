import { useState } from "react";

export const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];
export const DEFAULT_PAGE_SIZE = 10;

export type PaginationControls = {
  page: number;
  pageSize: number;
  pageCount: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
};

export const usePagination = <T>(items: T[]) => {
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [page, setPage] = useState(1);

  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  // Filters can shrink the list while a later page is active.
  const currentPage = Math.min(page, pageCount);
  const start = (currentPage - 1) * pageSize;

  const controls: PaginationControls = {
    page: currentPage,
    pageSize,
    pageCount,
    totalItems: items.length,
    onPageChange: setPage,
    onPageSizeChange: (size) => {
      setPageSize(size);
      setPage(1);
    },
  };

  return { pageItems: items.slice(start, start + pageSize), controls };
};
