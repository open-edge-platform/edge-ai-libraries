import { useState, useCallback, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
  PaginationEllipsis,
} from "@/components/ui/pagination";
import {
  useListHubModelsMutation,
  type ModelHubListResponse,
} from "@/api/api.generated";
import { Loader2, AlertCircle } from "lucide-react";
import { useAppSelector } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";

const ITEMS_PER_PAGE = 10;

export const UltralyticsBrowser = () => {
  const installedModels = useAppSelector(selectModels);
  const installedNames = useMemo(
    () =>
      new Set(
        installedModels
          .filter((model) => model.install_status === "installed")
          .map((model) => model.name),
      ),
    [installedModels],
  );
  const [inputValue, setInputValue] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [models, setModels] = useState<ModelHubListResponse["items"]>([]);
  const [totalItems, setTotalItems] = useState(0);

  const [listHubModels, { isLoading, error }] = useListHubModelsMutation();

  // Debounce search term (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchTerm(inputValue);
      setCurrentPage(1);
    }, 300);

    return () => clearTimeout(timer);
  }, [inputValue]);

  // Fetch models when search term or page changes
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const offset = (currentPage - 1) * ITEMS_PER_PAGE;
        const response = await listHubModels({
          modelHubListRequest: {
            hub: "ultralytics",
            filters: searchTerm ? { search: searchTerm } : {},
            limit: ITEMS_PER_PAGE,
            offset,
          },
        }).unwrap();

        setModels(response.items || []);
        setTotalItems(response.total || 0);
      } catch (err) {
        console.error("Failed to fetch models:", err);
        setModels([]);
        setTotalItems(0);
      }
    };

    fetchModels();
  }, [searchTerm, currentPage, listHubModels]);

  // Handle input change immediately (without debounce for UI responsiveness)
  const handleSearchChange = useCallback((value: string) => {
    setInputValue(value);
  }, []);

  const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);

  // Generate pagination items
  const getPaginationItems = () => {
    const items = [];
    const maxPagesToShow = 5;

    if (totalPages <= maxPagesToShow) {
      for (let i = 1; i <= totalPages; i++) {
        items.push(i);
      }
    } else {
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
    }

    return items;
  };

  return (
    <div className="space-y-4">
      {/* Search Input */}
      <div className="space-y-2">
        <label className="text-sm font-medium">Search Models</label>
        <Input
          type="text"
          placeholder="Search Ultralytics models..."
          value={inputValue}
          onChange={(e) => handleSearchChange(e.target.value)}
        />
      </div>

      {/* Error State */}
      {error && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          <span>Failed to load models. Please try again.</span>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty State */}
      {!isLoading && models.length === 0 && !error && (
        <div className="flex items-center justify-center py-8 text-center">
          <div>
            <p className="text-sm font-medium text-muted-foreground">
              {searchTerm ? "No models found" : "No models available"}
            </p>
            {searchTerm && (
              <p className="text-xs text-muted-foreground">
                Try adjusting your search term
              </p>
            )}
          </div>
        </div>
      )}

      {/* Models Table */}
      {!isLoading && models.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead className="w-28 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {models.map((model, idx) => (
              <TableRow key={idx} className="odd:bg-muted/30">
                <TableCell className="whitespace-normal break-words font-medium">
                  {typeof model.name === "string" ? model.name : "—"}
                </TableCell>
                <TableCell className="text-right">
                  {typeof model.name === "string" &&
                  installedNames.has(model.name) ? (
                    <span className="text-sm text-muted-foreground">
                      Installed
                    </span>
                  ) : (
                    <Button size="sm" variant="outline" disabled>
                      Install
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {/* Pagination */}
      {!isLoading && totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Showing{" "}
            {Math.min((currentPage - 1) * ITEMS_PER_PAGE + 1, totalItems)}-
            {Math.min(currentPage * ITEMS_PER_PAGE, totalItems)} of {totalItems}
          </p>
          <Pagination>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                  className={
                    currentPage === 1
                      ? "pointer-events-none opacity-50"
                      : "cursor-pointer"
                  }
                />
              </PaginationItem>

              {getPaginationItems().map((item, idx) => (
                <PaginationItem key={idx}>
                  {item === "..." ? (
                    <PaginationEllipsis />
                  ) : (
                    <PaginationLink
                      isActive={item === currentPage}
                      onClick={() => setCurrentPage(item as number)}
                      className="cursor-pointer"
                    >
                      {item}
                    </PaginationLink>
                  )}
                </PaginationItem>
              ))}

              <PaginationItem>
                <PaginationNext
                  onClick={() =>
                    setCurrentPage(Math.min(totalPages, currentPage + 1))
                  }
                  className={
                    currentPage === totalPages
                      ? "pointer-events-none opacity-50"
                      : "cursor-pointer"
                  }
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </div>
      )}

      <p className="text-xs text-muted-foreground">
        Model installation is not available yet.
      </p>
    </div>
  );
};
