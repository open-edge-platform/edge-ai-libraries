import { useState } from "react";
import { useForm } from "react-hook-form";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog.tsx";
import { Button } from "@/components/ui/button.tsx";
import { Input } from "@/components/ui/input.tsx";
import { Field, FieldError, FieldLabel } from "@/components/ui/field.tsx";
import { useLoadCameraProfilesMutation } from "@/api/api.generated.ts";
import { toast } from "sonner";
import { handleApiError } from "@/lib/apiUtils";

type CameraAuthFormData = {
  username: string;
  password: string;
};

type CameraAuthDialogProps = {
  cameraId: string;
  cameraName: string;
  onSuccess?: () => void;
};

export const CameraAuthDialog = ({
  cameraId,
  cameraName,
  onSuccess,
}: CameraAuthDialogProps) => {
  const [open, setOpen] = useState(false);
  const [loadCameraProfiles, { isLoading }] = useLoadCameraProfilesMutation();

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<CameraAuthFormData>({
    defaultValues: {
      username: "",
      password: "",
    },
  });

  const onSubmit = async (data: CameraAuthFormData) => {
    try {
      await loadCameraProfiles({
        cameraId,
        cameraProfilesRequest: {
          username: data.username,
          password: data.password,
        },
      }).unwrap();

      toast.success("Camera authorized", {
        description: "Camera authorized successfully",
      });

      setOpen(false);
      reset();
      onSuccess?.();
    } catch (error) {
      handleApiError(error, "Camera authorization failed");
    }
  };

  const handleOpenChange = (newOpen: boolean) => {
    setOpen(newOpen);
    if (!newOpen) {
      reset();
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm">Authorize</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Authorize Camera</DialogTitle>
          <DialogDescription>
            Enter credentials to authorize {cameraName}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="space-y-4 py-4">
            <Field>
              <FieldLabel htmlFor="username">Username</FieldLabel>
              <Input
                id="username"
                type="text"
                autoComplete="username"
                placeholder="Enter username"
                {...register("username", {
                  required: "Username is required",
                })}
              />
              {errors.username && (
                <FieldError>{errors.username.message}</FieldError>
              )}
            </Field>

            <Field>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder="Enter password"
                {...register("password", {
                  required: "Password is required",
                })}
              />
              {errors.password && (
                <FieldError>{errors.password.message}</FieldError>
              )}
            </Field>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? "Authorizing..." : "Authorize"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
