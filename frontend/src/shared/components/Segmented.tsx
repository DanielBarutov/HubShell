export function Segmented({ value, onChange, options }: { value: string; onChange: (value: string) => void; options: string[] }) {
  return <div className="segmented" role="group" aria-label="Фильтр зоны">{options.map((option) => <button className={value === option ? "selected" : ""} key={option} aria-pressed={value === option} onClick={() => onChange(option)}>{option}</button>)}</div>;
}
