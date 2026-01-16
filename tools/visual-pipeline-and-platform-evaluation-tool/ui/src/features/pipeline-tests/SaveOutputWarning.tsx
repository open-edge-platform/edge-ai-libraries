const SaveOutputWarning = () => {
  return (
    <div className="mt-3 text-xs text-neutral-300 bg-neutral-900/30 border border-neutral-700/50 rounded-lg px-4 py-2.5 flex items-start gap-2">
      <p>
        <span className="font-semibold">Note:</span> This option may negatively
        impact performance results.
      </p>
    </div>
  );
};

export default SaveOutputWarning;
