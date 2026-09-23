// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { Label } from "@/components/ui/label";
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
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(event) =>
          onChange(event.target.value as VoiceInferenceDevice | "")
        }
        className="border-input h-10 w-full rounded-md border bg-background px-3 text-sm"
      >
        <option value="">Service default</option>
        {availableFamilies.map((family) => (
          <option key={family} value={family}>
            {family}
          </option>
        ))}
      </select>
    </div>
  );
}
