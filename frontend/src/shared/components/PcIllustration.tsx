export function PcIllustration({
  compact = false,
  tiny = false,
  vip = false,
}: {
  compact?: boolean;
  tiny?: boolean;
  vip?: boolean;
}) {
  const size = tiny ? "h-16 w-32" : compact ? "h-20 w-40" : "h-24 w-48";
  const accent = vip ? "#f5c24e" : "#a8ff4d";

  return (
    <div className={`relative ${size}`} aria-hidden="true">
      <svg
        viewBox="0 0 160 80"
        className="h-full w-full"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <rect x="48" y="8" width="66" height="42" rx="4" fill="#07181b" stroke={accent} strokeOpacity=".8" />
        <rect x="53" y="13" width="56" height="32" rx="2" fill="#12343c" />
        <path d="M81 50v10m-18 4h36" stroke={accent} strokeWidth="3" strokeLinecap="round" />
        <rect x="12" y="21" width="25" height="39" rx="5" fill="#082126" stroke={accent} strokeOpacity=".65" />
        <rect x="123" y="21" width="25" height="39" rx="5" fill="#082126" stroke={accent} strokeOpacity=".65" />
        <path d="M20 31h9m-9 7h9m102-7h9m-9 7h9" stroke={accent} strokeWidth="2" strokeLinecap="round" />
        <circle cx="25" cy="51" r="3" fill={accent} />
        <circle cx="136" cy="51" r="3" fill={accent} />
        <path d="M35 66h90" stroke={accent} strokeOpacity=".35" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  );
}
