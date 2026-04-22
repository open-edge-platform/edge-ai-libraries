import { useListImagesInSetQuery } from "@/api/api.generated.ts";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { useParams, Link } from "react-router";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button.tsx";

export function ImagesInSet() {
  const { id } = useParams<{ id: string }>();
  const {
    data: images,
    isSuccess,
    isLoading,
  } = useListImagesInSetQuery({ name: id! }, { skip: !id });

  if (isLoading) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10">Loading images...</div>
      </div>
    );
  }

  if (!id) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10">
          Image set name not provided
        </div>
      </div>
    );
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
  };

  return (
    <div className="container pl-16 mx-auto py-10">
      <div className="mb-6">
        <div className="flex items-center gap-4 mb-2">
          <Button variant="ghost" size="icon" asChild>
            <Link to="/images">
              <ArrowLeft className="w-5 h-5" />
            </Link>
          </Button>
          <h1 className="text-3xl font-bold">{id}</h1>
        </div>
        <p className="text-muted-foreground ml-14">Images in this collection</p>
      </div>

      {isSuccess && images && images.length > 0 ? (
        <Table>
          <TableCaption>
            A list of {images.length} image{images.length !== 1 ? "s" : ""} in
            this set.
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[30%]">File name</TableHead>
              <TableHead>Resolution</TableHead>
              <TableHead>Extension</TableHead>
              <TableHead>Size</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {images.map((image) => (
              <TableRow key={image.filename}>
                <TableCell className="font-medium">{image.filename}</TableCell>
                <TableCell>
                  {image.width && image.height
                    ? `${image.width}x${image.height}`
                    : "N/A"}
                </TableCell>
                <TableCell>{image.extension.toUpperCase()}</TableCell>
                <TableCell>{formatBytes(image.size_bytes)}</TableCell>
                <TableCell>
                  <img
                    src={`/assets/images/input/${id}/${image.filename}`}
                    alt={image.filename}
                    className="w-32 h-auto object-contain"
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <div className="text-center py-10 text-muted-foreground">
          No images found in this set.
        </div>
      )}
    </div>
  );
}
