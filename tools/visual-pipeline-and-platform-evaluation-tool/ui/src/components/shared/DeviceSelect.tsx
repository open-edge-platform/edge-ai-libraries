import { useAppSelector } from "@/store/hooks";
import { selectDevices } from "@/store/reducers/devices";
import type { Device } from "@/api/api.generated.ts";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

interface DeviceSelectProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

const DeviceSelect = ({ value, onChange, className }: DeviceSelectProps) => {
  const devices = useAppSelector(selectDevices);

  const formatDeviceName = (deviceName: string): string => {
    // Remove .0 suffix for cleaner display in UI
    return deviceName.replace(/\.0$/, "");
  };

  const formatDeviceDisplayName = (device: Device): string =>
    `${device.device_name}: ${device.full_device_name}`;

  return (
    <Select value={formatDeviceName(value)} onValueChange={onChange}>
      <SelectTrigger
        size="sm"
        className={cn("w-full bg-background text-xs md:text-xs", className)}
      >
        <SelectValue placeholder="Select device" />
      </SelectTrigger>
      <SelectContent>
        {devices.map((device) => {
          const formattedName = formatDeviceName(device.device_name);
          return (
            <SelectItem
              key={device.device_name}
              value={formattedName}
              className="text-xs"
            >
              {formatDeviceDisplayName(device)}
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
};

export default DeviceSelect;
