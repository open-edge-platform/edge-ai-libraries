export const getPaginationItems = (
  currentPage: number,
  totalPages: number,
  maxPagesToShow = 5,
): (number | "...")[] => {
  const items: (number | "...")[] = [];

  if (totalPages <= maxPagesToShow) {
    for (let i = 1; i <= totalPages; i++) {
      items.push(i);
    }
    return items;
  }

  items.push(1);
  if (currentPage > 3) {
    items.push("...");
  }

  const start = Math.max(2, currentPage - 1);
  const end = Math.min(totalPages - 1, currentPage + 1);
  for (let i = start; i <= end; i++) {
    if (!items.includes(i)) {
      items.push(i);
    }
  }

  if (currentPage < totalPages - 2) {
    items.push("...");
  }
  if (!items.includes(totalPages)) {
    items.push(totalPages);
  }

  return items;
};
