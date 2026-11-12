// src/components/ui/DataTable.tsx
import React, { useState, useMemo } from "react";
import { ChevronUp, ChevronDown, ArrowUpDown, ChevronLeft, ChevronRight, Search } from "lucide-react";

export interface ColumnDef<T> {
  key: string;
  header: string;
  accessor?: (item: T) => any;
  render?: (item: T) => React.ReactNode;
  sortable?: boolean;
  align?: "left" | "center" | "right";
  className?: string;
  width?: string;
}

export interface DataTableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
  keyExtractor: (item: T, index: number) => string;
  searchable?: boolean;
  searchPlaceholder?: string;
  searchFilter?: (item: T, query: string) => boolean;
  emptyMessage?: string;
  pageSize?: number;
  loading?: boolean;
  className?: string;
  onRowClick?: (item: T) => void;
}

export function DataTable<T>({
  data,
  columns,
  keyExtractor,
  searchable = true,
  searchPlaceholder = "Search records...",
  searchFilter,
  emptyMessage = "No records found",
  pageSize = 10,
  loading = false,
  className = "",
  onRowClick,
}: DataTableProps<T>) {
  const [searchQuery, setSearchQuery] = useState("");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const [currentPage, setCurrentPage] = useState(1);

  // Search Filtering
  const filteredData = useMemo(() => {
    if (!searchQuery.trim()) return data;
    const query = searchQuery.toLowerCase();

    if (searchFilter) {
      return data.filter((item) => searchFilter(item, query));
    }

    return data.filter((item) => {
      return columns.some((col) => {
        const val = col.accessor ? col.accessor(item) : (item as any)[col.key];
        if (val == null) return false;
        return String(val).toLowerCase().includes(query);
      });
    });
  }, [data, searchQuery, searchFilter, columns]);

  // Sorting
  const sortedData = useMemo(() => {
    if (!sortKey) return filteredData;
    const col = columns.find((c) => c.key === sortKey);
    if (!col) return filteredData;

    return [...filteredData].sort((a, b) => {
      const valA = col.accessor ? col.accessor(a) : (a as any)[col.key];
      const valB = col.accessor ? col.accessor(b) : (b as any)[col.key];

      if (valA == null && valB == null) return 0;
      if (valA == null) return 1;
      if (valB == null) return -1;

      if (typeof valA === "number" && typeof valB === "number") {
        return sortDirection === "asc" ? valA - valB : valB - valA;
      }

      const strA = String(valA).toLowerCase();
      const strB = String(valB).toLowerCase();
      if (strA < strB) return sortDirection === "asc" ? -1 : 1;
      if (strA > strB) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });
  }, [filteredData, sortKey, sortDirection, columns]);

  // Pagination
  const totalPages = Math.max(1, Math.ceil(sortedData.length / pageSize));
  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return sortedData.slice(start, start + pageSize);
  }, [sortedData, currentPage, pageSize]);

  const handleSort = (key: string, sortable?: boolean) => {
    if (sortable === false) return;
    if (sortKey === key) {
      if (sortDirection === "asc") {
        setSortDirection("desc");
      } else {
        setSortKey(null);
        setSortDirection("asc");
      }
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  };

  return (
    <div className={`bg-canvas-card border border-canvas-border rounded-xl shadow-card overflow-hidden ${className}`}>
      {searchable && (
        <div className="p-4 border-b border-canvas-border flex items-center justify-between gap-4 bg-canvas-card">
          <div className="relative w-full max-w-sm">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              placeholder={searchPlaceholder}
              className="w-full bg-canvas-dark border border-canvas-border rounded-lg pl-9 pr-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition-colors"
            />
          </div>
          <div className="text-xs text-text-muted font-mono whitespace-nowrap">
            {filteredData.length} {filteredData.length === 1 ? "record" : "records"}
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-canvas-border bg-canvas-elevated/50 text-text-secondary uppercase tracking-wider font-semibold">
              {columns.map((col) => {
                const isSorted = sortKey === col.key;
                const alignClass =
                  col.align === "center"
                    ? "text-center"
                    : col.align === "right"
                    ? "text-right"
                    : "text-left";

                return (
                  <th
                    key={col.key}
                    onClick={() => handleSort(col.key, col.sortable)}
                    style={{ width: col.width }}
                    className={`px-4 py-3 text-[11px] select-none ${alignClass} ${
                      col.sortable !== false ? "cursor-pointer hover:text-text-primary" : ""
                    } ${col.className || ""}`}
                  >
                    <div
                      className={`inline-flex items-center space-x-1.5 ${
                        col.align === "right"
                          ? "justify-end"
                          : col.align === "center"
                          ? "justify-center"
                          : "justify-start"
                      }`}
                    >
                      <span>{col.header}</span>
                      {col.sortable !== false && (
                        <span className="text-text-muted">
                          {isSorted ? (
                            sortDirection === "asc" ? (
                              <ChevronUp size={13} className="text-cyan-400" />
                            ) : (
                              <ChevronDown size={13} className="text-cyan-400" />
                            )
                          ) : (
                            <ArrowUpDown size={12} className="opacity-40" />
                          )}
                        </span>
                      )}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-canvas-border divide-opacity-60 bg-canvas-card">
            {loading ? (
              Array.from({ length: 5 }).map((_, idx) => (
                <tr key={idx} className="animate-pulse">
                  {columns.map((col) => (
                    <td key={col.key} className="px-4 py-3">
                      <div className="h-4 bg-slate-800 rounded w-3/4"></div>
                    </td>
                  ))}
                </tr>
              ))
            ) : paginatedData.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-8 text-center text-xs text-text-muted italic"
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              paginatedData.map((item, index) => (
                <tr
                  key={keyExtractor(item, index)}
                  onClick={() => onRowClick && onRowClick(item)}
                  className={`transition-colors duration-100 ${
                    onRowClick ? "cursor-pointer hover:bg-canvas-hover/70" : "hover:bg-canvas-hover/40"
                  }`}
                >
                  {columns.map((col) => {
                    const content = col.render
                      ? col.render(item)
                      : col.accessor
                      ? col.accessor(item)
                      : (item as any)[col.key];

                    const alignClass =
                      col.align === "center"
                        ? "text-center"
                        : col.align === "right"
                        ? "text-right"
                        : "text-left";

                    return (
                      <td
                        key={col.key}
                        className={`px-4 py-3 ${alignClass} ${col.className || ""}`}
                      >
                        {content}
                      </td>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="p-3 border-t border-canvas-border bg-canvas-card flex items-center justify-between text-xs text-text-muted">
          <span>
            Page <span className="font-mono text-text-primary">{currentPage}</span> of{" "}
            <span className="font-mono text-text-primary">{totalPages}</span>
          </span>
          <div className="flex items-center space-x-1.5">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="p-1.5 rounded border border-canvas-border bg-canvas-dark text-text-secondary hover:text-text-primary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="p-1.5 rounded border border-canvas-border bg-canvas-dark text-text-secondary hover:text-text-primary disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

