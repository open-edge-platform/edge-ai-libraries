const SaveOutputWarning = () => {
  return (
    <div className="text-muted-foreground border border-amber-400 my-2 p-2 bg-amber-200/50 w-1/2">
      <b>Note 1</b>: The current implementation does not automatically infer the
      best encoding device from the existing pipeline. Select the same device
      that is already used by other blocks in your pipeline. To learn more,
      refer to our documentation:{" "}
      <a
        href="https://docs.openedgeplatform.intel.com/2025.2/edge-ai-libraries/visual-pipeline-and-platform-evaluation-tool/index.html"
        target="_blank"
        rel="noopener noreferrer"
        className="hover:text-classic-blue transition-colors underline"
      >
        link
      </a>
      .
      <br />
      <b>Note 2</b>: Selecting this option will negatively impact the
      performance results.
    </div>
  );
};

export default SaveOutputWarning;
