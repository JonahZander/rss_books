type Props = {
  size?: number;
  className?: string;
};

/**
 * RSS Books mark: an angular open book with broadcast arcs rising from the
 * spine. The arcs carry the signature pink→blue gradient (135deg, matching
 * .brand-accent); the book is inked via currentColor so contexts can restyle it.
 */
export function LogoMark({ size = 32, className }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={className}
      aria-hidden
      focusable="false"
    >
      <defs>
        <linearGradient id="logo-signal" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ff4d9d" />
          <stop offset="1" stopColor="#3d8bff" />
        </linearGradient>
      </defs>
      <g fill="currentColor">
        <polygon points="6,26 30,38 30,58 6,50" />
        <polygon points="58,26 34,38 34,58 58,50" />
      </g>
      <g stroke="url(#logo-signal)" strokeWidth="4" fill="none">
        <path d="M26.3 25.3 A8 8 0 0 1 37.7 25.3" />
        <path d="M22.1 21.1 A14 14 0 0 1 41.9 21.1" />
      </g>
      <circle cx="32" cy="31" r="3.4" fill="url(#logo-signal)" />
    </svg>
  );
}
