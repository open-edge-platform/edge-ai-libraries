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
import { Link, useParams } from "react-router";
import { ArrowLeft } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton.tsx";
import { formatBytes } from "@/lib/fileUtils.ts";

export function ImagesInSet() {
  const { imageSetName } = useParams<{ imageSetName: string }>();
  const {
    data: images,
    isSuccess,
    isLoading,
  } = useListImagesInSetQuery({ name: imageSetName! }, { skip: !imageSetName });

  if (isLoading) {
    return (
      <div className="container pl-16 mx-auto py-10">
        <div className="mb-6">
          <div className="flex items-center gap-4 mb-2">
            <Skeleton className="h-10 w-10" />
            <Skeleton className="h-9 w-48" />
          </div>
          <Skeleton className="h-4 w-64 ml-14" />
        </div>

        <Table>
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
            {[...Array(5)].map((_, i) => (
              <TableRow key={i}>
                <TableCell>
                  <Skeleton className="h-4 w-full" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-24" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-12" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-20" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-24 w-32" />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }

  if (!imageSetName) {
    return (
      <div className="h-full overflow-auto">
        <div className="container mx-auto py-10">
          Image set name not provided
        </div>
      </div>
    );
  }

  return (
    <div className="container pl-16 mx-auto py-10">
      <div className="mb-6">
        <div className="flex items-center gap-4 mb-2">
          <Link
            to="/images"
            className="p-2 hover:bg-accent rounded transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>

          <h1 className="text-3xl font-bold">{imageSetName}</h1>
        </div>
        <p className="text-muted-foreground ml-14">
          The list of images in this collection
        </p>
      </div>

      {isSuccess && images && images.length > 0 ? (
        <Table>
          <TableCaption>
            A list of {images.length} image{images.length !== 1 ? "s" : ""} in
            this set.
          </TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[30%] truncate">File name</TableHead>
              <TableHead>Resolution</TableHead>
              <TableHead>Extension</TableHead>
              <TableHead>Size</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {images.map((image) => (
              <TableRow key={image.filename}>
                <TableCell className="font-medium max-w-0">
                  <div className="truncate" title={image.filename}>
                    {image.filename}
                  </div>
                </TableCell>
                <TableCell>
                  {image.width && image.height
                    ? `${image.width}x${image.height}`
                    : "N/A"}
                </TableCell>
                <TableCell>{image.extension.toUpperCase()}</TableCell>
                <TableCell>{formatBytes(image.size_bytes)}</TableCell>
                <TableCell>
                  <img
                    src={`/assets/images/input/${imageSetName}/${image.filename}`}
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
