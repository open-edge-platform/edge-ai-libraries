import { useRef, useState } from "react";
import { Button } from "@/components/ui/button.tsx";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog.tsx";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs.tsx";
import { MultiFileUploader } from "@/features/upload/MultiFileUploader.tsx";
import type { PreUploadMessage } from "@/features/upload/uploaderMessages";
import { ENDPOINTS } from "@/api/apiEndpoints";
import { CATEGORY_INFO } from "@/features/models/categoryInfo.ts";
import { UltralyticsBrowser } from "@/features/models/UltralyticsBrowser.tsx";
import { HGFBrowser } from "@/features/models/HGFBrowser.tsx";

const MAX_DESCRIPTION_LENGTH = 200;

type AddModelDialogProps = {
  onPreUpload: (
    file: File,
    fields: Record<string, string>,
  ) => Promise<PreUploadMessage | null>;
  onUploadProgress: (
    jobs: Array<{ id: string; name: string; progress: number }>,
  ) => void;
  onUploadComplete: (succeeded: number, failed: number) => void;
};

export const AddModelDialog = ({
  onPreUpload,
  onUploadProgress,
  onUploadComplete,
}: AddModelDialogProps) => {
  const [open, setOpen] = useState(false);
  const dialogContentRef = useRef<HTMLDivElement | null>(null);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          Add new model
        </Button>
      </DialogTrigger>
      <DialogContent
        ref={dialogContentRef}
        className="h-[85vh] max-h-[85vh] w-[60vw] max-w-[60vw] items-start content-start overflow-y-auto sm:max-w-[60vw]"
        onInteractOutside={(event) => {
          if (
            (event.target as HTMLElement).closest(
              '[data-slot="combobox-content"]',
            )
          ) {
            event.preventDefault();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>Add New Model</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="custom" className="mt-2">
          <TabsList className="w-full">
            <TabsTrigger value="custom">Custom Model</TabsTrigger>
            <TabsTrigger value="ultralytics">Ultralytics Model</TabsTrigger>
            <TabsTrigger value="huggingface">HuggingFace Model</TabsTrigger>
          </TabsList>
          <TabsContent value="custom" className="mt-4 space-y-4">
            <p className="text-sm text-muted-foreground">
              Not every uploaded model will work in ViPPET. Check supported
              models:{" "}
              <a
                href="https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dlstreamer/supported_models.html"
                target="_blank"
                rel="noreferrer"
                className="font-medium underline underline-offset-2"
              >
                DL Streamer supported models
              </a>
              .
            </p>
            <MultiFileUploader
              accept=".zip,application/zip"
              uploadEndpoint={ENDPOINTS.UPLOAD_MODEL}
              multiple={false}
              maxSize={500 * 1024 * 1024}
              preUpload={onPreUpload}
              preUploadImmediate
              portalContainer={dialogContentRef}
              onUploadProgress={onUploadProgress}
              onUploadComplete={(succeeded, failed) => {
                onUploadComplete(succeeded, failed);
                if (succeeded > 0) setOpen(false);
              }}
              formFields={[
                {
                  name: "model_name",
                  label: "Model name",
                  placeholder: "Enter model name",
                  required: true,
                  regex: /^[a-zA-Z0-9_\s-]+$/,
                  regexMessage:
                    "Only alphanumeric characters, spaces, underscores, and hyphens are allowed.",
                },
                {
                  name: "category",
                  label: "Category",
                  placeholder: "Select a category",
                  required: true,
                  type: "combobox" as const,
                  options: Object.entries(CATEGORY_INFO).map(
                    ([value, { label }]) => ({ label, value }),
                  ),
                },
                {
                  name: "description",
                  label: "Description",
                  placeholder: "Optional description of what the model does",
                  required: false,
                  maxLength: MAX_DESCRIPTION_LENGTH,
                },
              ]}
            />
          </TabsContent>
          <TabsContent value="ultralytics" className="mt-4">
            <UltralyticsBrowser onInstalled={() => setOpen(false)} />
          </TabsContent>
          <TabsContent value="huggingface" className="mt-4">
            <HGFBrowser onInstalled={() => setOpen(false)} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
};
