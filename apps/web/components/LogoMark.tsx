type Props = {
  size?: number;
  className?: string;
};

/**
 * RSS Books mark: a dog-eared folio carrying the RSS quarter-wave and dot.
 * The wave/dot wear the signature pink→blue gradient (135deg, matching
 * .brand-accent); the folio is inked via currentColor so contexts can
 * restyle it. Geometry lives on a 64 grid: A4-ish body (36×52), solid fold
 * flap, signal glyph optically centered in the body. The viewBox hugs the
 * drawn content (41×57 incl. stroke) so `size` is the visual height —
 * contexts can match it to a neighboring cap height exactly.
 */
const RATIO = 41 / 57;

export function LogoMark({ size = 32, className }: Props) {
  return (
    <svg
      width={size * RATIO}
      height={size}
      viewBox="11.5 3.5 41 57"
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
      <path
        d="M14 6 H38 L50 18 V58 H14 Z"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinejoin="miter"
        fill="none"
      />
      <polygon points="38,6 38,18 50,18" fill="currentColor" />
      <path
        d="M26 31 A14 14 0 0 1 40 45"
        stroke="url(#logo-signal)"
        strokeWidth="5"
        fill="none"
      />
      <circle cx="26" cy="45" r="4" fill="url(#logo-signal)" />
    </svg>
  );
}
