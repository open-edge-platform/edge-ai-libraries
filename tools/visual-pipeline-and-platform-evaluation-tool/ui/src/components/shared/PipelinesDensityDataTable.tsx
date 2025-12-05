import { useEffect, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowSelectionState,
} from "@tanstack/react-table";
import { Checkbox } from "@/components/ui/checkbox";
import { Slider } from "@/components/ui/slider";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Pipeline } from "@/api/api.generated";

function ParticipationSlider({
  pipelineId,
  storedValue,
  onCommit,
}: {
  pipelineId: string;
  storedValue: number;
  onCommit: (pipelineId: string, value: number[]) => void;
}) {
  const [localValue, setLocalValue] = useState(storedValue);

  useEffect(() => {
    setLocalValue(storedValue);
  }, [storedValue]);

  return (
    <div className="flex items-center gap-3 min-w-[200px]">
      <Slider
        value={[localValue]}
        onValueChange={(val) => setLocalValue(val[0])}
        onValueCommit={(val) => onCommit(pipelineId, val)}
        min={0}
        max={100}
        step={1}
        className="flex-1"
      />
      <span className="text-sm font-medium w-12 text-right">
        {localValue}%
      </span>
    </div>
  );
}

export interface PipelineWithParticipation extends Pipeline {
  stream_rate: number;
}

interface PipelinesDensityDataTableProps {
  data: Pipeline[];
  onSelectionChange?: (selectedPipelines: PipelineWithParticipation[]) => void;
}

export function PipelinesDensityDataTable({
  data,
  onSelectionChange,
}: PipelinesDensityDataTableProps) {
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [participationValues, setParticipationValues] = useState<
    Record<string, number>
  >(() => {
    const initial: Record<string, number> = {};
    data.forEach((pipeline) => {
      initial[pipeline.id] = 100;
    });
    return initial;
  });

  const handleParticipationChange = (pipelineId: string, value: number[]) => {
    setParticipationValues((prev) => ({
      ...prev,
      [pipelineId]: value[0],
    }));

    // Auto-select the row when slider changes
    const rowIndex = data.findIndex((pipeline) => pipeline.id === pipelineId);
    if (rowIndex !== -1) {
      setRowSelection((prev) => ({
        ...prev,
        [rowIndex]: true,
      }));
    }
  };

  const columns: ColumnDef<Pipeline>[] = [
    {
      id: "select",
      header: ({ table }) => (
        <Checkbox
          checked={
            table.getIsAllPageRowsSelected() ||
            (table.getIsSomePageRowsSelected() && "indeterminate")
          }
          onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          aria-label="Select all"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
          aria-label="Select row"
        />
      ),
      enableSorting: false,
      enableHiding: false,
    },
    {
      accessorKey: "name",
      header: "Name",
    },
    {
      accessorKey: "version",
      header: "Version",
    },
    {
      id: "participation",
      header: "Participation",
      cell: ({ row }) => {
        const pipelineId = row.original.id;
        const storedValue = participationValues[pipelineId] ?? 100;
        return (
          <ParticipationSlider
            pipelineId={pipelineId}
            storedValue={storedValue}
            onCommit={handleParticipationChange}
          />
        );
      },
    },
  ];

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    onRowSelectionChange: setRowSelection,
    state: {
      rowSelection,
    },
  });

  // Call onSelectionChange whenever selection changes
  useEffect(() => {
    if (onSelectionChange) {
      const selectedRows = table
        .getFilteredSelectedRowModel()
        .rows.map((row) => ({
          ...row.original,
          stream_rate: participationValues[row.original.id] ?? 100,
        }));
      onSelectionChange(selectedRows);
    }
  }, [rowSelection, participationValues, table, onSelectionChange]);

  return (
    <div className="space-y-4">
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && "selected"}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-24 text-center"
                >
                  No results.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className="text-sm text-muted-foreground">
        {table.getFilteredSelectedRowModel().rows.length} of{" "}
        {table.getFilteredRowModel().rows.length} row(s) selected.
      </div>
    </div>
  );
}
