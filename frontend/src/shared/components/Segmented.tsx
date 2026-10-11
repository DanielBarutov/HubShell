export function Segmented({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <div
      className="segmented join rounded-xl border border-primary/20! bg-base-100/55! p-0.5 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]"
      role="tablist"
      aria-label="Фильтр зоны"
    >
      {options.map((option) => (
        <button
          className={`join-item btn btn-sm ${value === option ? "selected btn-primary text-primary-content! hover:bg-primary! hover:text-primary-content!" : "btn-ghost text-base-content/70! hover:bg-primary/15! hover:text-primary!"}`}
          key={option}
          role="tab"
          aria-selected={value === option}
          onClick={() => onChange(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );
}
