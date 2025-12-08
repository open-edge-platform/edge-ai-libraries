import { useAppSelector } from "@/store/hooks";
import { selectDevices } from "@/store/reducers/devices";
import type { Device } from "@/api/api.generated.ts";

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
    <select
      value={formatDeviceName(value)}
      onChange={(e) => onChange(e.target.value)}
      className={className ?? "w-full text-xs border border-gray-300 px-2 py-1"}
    >
      {devices.map((device) => {
        const formattedName = formatDeviceName(device.device_name);
        return (
          <option key={device.device_name} value={formattedName}>
            {formatDeviceDisplayName(device)}
          </option>
        );
      })}
    </select>
  );
};

export default DeviceSelect;
