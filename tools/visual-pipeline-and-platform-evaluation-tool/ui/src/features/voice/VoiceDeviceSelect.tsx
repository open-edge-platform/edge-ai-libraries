// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAppSelector } from "@/store/hooks";
import { selectDevices } from "@/store/reducers/devices";

export type VoiceInferenceDevice = "CPU" | "GPU" | "NPU";

interface VoiceDeviceSelectProps {
  id: string;
  label: string;
  value: VoiceInferenceDevice | "";
  disabled: boolean;
  onChange: (value: VoiceInferenceDevice | "") => void;
}

const DEVICE_FAMILIES: VoiceInferenceDevice[] = ["CPU", "GPU", "NPU"];
const SERVICE_DEFAULT_VALUE = "service-default";

export function VoiceDeviceSelect({
  id,
  label,
  value,
  disabled,
  onChange,
}: VoiceDeviceSelectProps) {
  const devices = useAppSelector(selectDevices);
  const availableFamilies = DEVICE_FAMILIES.filter((family) =>
    devices.some((device) => device.device_family === family),
  );

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Select
        value={value || SERVICE_DEFAULT_VALUE}
        disabled={disabled}
        onValueChange={(nextValue) =>
          onChange(
            nextValue === SERVICE_DEFAULT_VALUE
              ? ""
              : (nextValue as VoiceInferenceDevice),
          )
        }
      >
        <SelectTrigger id={id} className="h-10 w-full bg-background">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={SERVICE_DEFAULT_VALUE}>Service default</SelectItem>
          {availableFamilies.map((family) => (
            <SelectItem key={family} value={family}>
              {family}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
