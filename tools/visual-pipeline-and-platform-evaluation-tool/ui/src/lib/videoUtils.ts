export const isSupportedVideoFilename = (filename: string): boolean =>
  !filename.toLowerCase().endsWith(".ts");

export const filterOutTransportStreams = <T extends { filename: string }>(
  files: T[],
): T[] => files.filter((file) => isSupportedVideoFilename(file.filename));
