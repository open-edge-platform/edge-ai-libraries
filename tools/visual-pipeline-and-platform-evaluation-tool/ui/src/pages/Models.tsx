import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { useAppSelector } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import { MultiFileUploader } from "@/features/upload/MultiFileUploader.tsx";
import {
  PRE_UPLOAD_MESSAGES,
  type PreUploadMessage as PRE_UPLOAD_MESSAGES_TYPE,
} from "@/features/upload/uploaderMessages";
import { ENDPOINTS } from "@/api/apiEndpoints";
import JSZip from "jszip";

const REQUIRED_MODEL_FILES = ["model.bin", "model.xml"];

const validateModelArchive = async (
  file: File,
  _fields: Record<string, string>,
): Promise<PRE_UPLOAD_MESSAGES_TYPE | null> => {
  try {
    const zip = await JSZip.loadAsync(file);
    const fileNames = Object.keys(zip.files).map(
      (name) => name.split("/").pop()!,
    );
    const missing = REQUIRED_MODEL_FILES.filter(
      (required) => !fileNames.includes(required),
    );
    if (missing.length > 0) {
      return PRE_UPLOAD_MESSAGES.MISSING_REQUIRED_FILES;
    }
  } catch {
    return PRE_UPLOAD_MESSAGES.INVALID_ARCHIVE;
  }

  return null; //PRE_UPLOAD_MESSAGES.FILE_EXISTS;
};

export const Models = () => {
  const models = useAppSelector(selectModels);

  if (models.length > 0) {
    return (
      <div className="container pl-16 mx-auto py-10">
        <div>
          <h1 className="text-3xl font-bold">Models</h1>
          <p className="text-muted-foreground mt-2">
            Ready-to-use models available in the platform
          </p>
        </div>

        <MultiFileUploader
          accept=".zip,application/zip"
          uploadEndpoint={ENDPOINTS.UPLOAD_MODEL}
          multiple={false}
          preUpload={validateModelArchive}
          formFields={[
            {
              name: "name",
              label: "Model name",
              placeholder: "Enter model name",
              required: true,
            },
          ]}
          className="mb-8"
        />

        <Table className="mb-10">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[33%] truncate">Name</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Precision</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {models.map((model) => (
              <TableRow key={model.name}>
                <TableCell className="font-medium max-w-0">
                  <div className="truncate" title={model.display_name}>
                    {model.display_name}
                  </div>
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
