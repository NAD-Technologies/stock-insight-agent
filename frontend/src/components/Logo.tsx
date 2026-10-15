/** NAD Technologies mark: globe + orbit + dot. The orbit uses currentColor so it flips with the theme. */
export function LogoMark({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 150 130" fill="none" strokeWidth={7} strokeLinecap="round" role="img" aria-label="NAD Technologies">
      <defs>
        <linearGradient id="nad-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2b7be4" /><stop offset="1" stopColor="#1fb5c0" />
        </linearGradient>
      </defs>
      <g transform="translate(72 66)">
        <g stroke="url(#nad-g)"><circle r="52" /><ellipse rx="21" ry="52" /><line x1="-52" y1="0" x2="52" y2="0" /></g>
        <ellipse rx="68" ry="20" transform="rotate(-22)" stroke="currentColor" />
        <circle cx="60" cy="-34" r="8.5" fill="#14c9b0" stroke="none" />
      </g>
    </svg>
  );
}

/** Mark + "NAD / TECHNOLOGIES" wordmark. */
export function Logo({ size = 40, tagline = false }: { size?: number; tagline?: boolean }) {
  return (
    <div className="inline-flex flex-col">
      <div className="flex items-center gap-2">
        <LogoMark size={size} />
        <div className="leading-none">
          <div className="font-extrabold tracking-tight" style={{ fontSize: size * 0.9 }}>NAD</div>
          <div className="font-semibold text-[#2563eb] dark:text-[#60a5fa]" style={{ fontSize: size * 0.27, letterSpacing: "0.32em", marginTop: size * 0.08 }}>TECHNOLOGIES</div>
        </div>
      </div>
      {tagline && <div className="mt-3 border-t border-line pt-2 text-sm font-semibold">Intelligence, Delivered.</div>}
    </div>
  );
}
