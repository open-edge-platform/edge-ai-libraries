import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";

export const Models = () => {
  const models = useAppSelector(selectModels);

  if (models.length > 0) {
    return (
      <div className="container mx-auto py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Models</h1>
          <p className="text-muted-foreground mt-2">
            Ready-to-use models available in the platform
          </p>
        </div>
        <Table>
          <TableCaption>A list of loaded models.</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[33%]">Name</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Precision</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {models.map((model) => (
              <TableRow key={model.name}>
                <TableCell className="font-medium">
                  {model.display_name}
                </TableCell>
                <TableCell>{model.category}</TableCell>
                <TableCell>{model.precision}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }
  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">Loading models</div>
    </div>
  );
};
