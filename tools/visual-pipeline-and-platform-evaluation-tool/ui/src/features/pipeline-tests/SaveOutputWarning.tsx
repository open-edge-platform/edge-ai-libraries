const SaveOutputWarning = () => {
  return (
    <div className="text-muted-foreground dark:text-foreground/80 border border-amber-400 my-2 p-2 bg-amber-200/50 w-1/2">
      <b>Note</b>: Selecting this option will negatively impact the performance
      results.
    </div>
  );
};

export default SaveOutputWarning;
