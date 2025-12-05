import { useAppSelector } from "@/store/hooks";
import { selectDevices } from "@/store/reducers/devices";

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
            {formattedName}
          </option>
        );
      })}
    </select>
  );
};

export default DeviceSelect;
