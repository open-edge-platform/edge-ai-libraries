const SaveOutputWarning = () => {
  return (
    <div className="mt-3 inline-flex max-w-sm min-w-0 text-xs text-popover-foreground bg-popover/95 border border-border px-3 py-2 items-start gap-2">
      <p className="min-w-0 whitespace-normal break-words leading-relaxed">
        <span className="font-semibold">Note:</span> This option may negatively
        impact performance results.
      </p>
    </div>
  );
};

export default SaveOutputWarning;
