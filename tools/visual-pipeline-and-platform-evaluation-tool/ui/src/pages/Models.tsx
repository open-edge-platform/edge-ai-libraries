import { useGetModelsQuery } from "@/api/api.generated.ts";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";

const Models = () => {
  const { data: models, isSuccess } = useGetModelsQuery();

  if (isSuccess && models.length > 0) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10">
          <h1 className="text-3xl font-bold mb-6">Models</h1>
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
      </div>
    );
  }
  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">Loading models</div>
    </div>
  );
};

export default Models;
