/**
 * The app's icons: one drawn set, 24px grid, 1.75 stroke, round joins. Food emoji stay on pins
 * and list rows (they're content: the kind of food), but controls use these, never emoji.
 */
type Props = { size?: number; className?: string };

function Svg({ size = 20, className, children, filled = false }: Props & { children: React.ReactNode; filled?: boolean }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {children}
    </svg>
  );
}

export const PlusIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export const SearchIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m20 20-4.2-4.2" />
  </Svg>
);

export const FilterIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
    <circle cx="15" cy="7" r="2" />
    <circle cx="9" cy="17" r="2" />
  </Svg>
);

export const DiceIcon = (p: Props) => (
  <Svg {...p}>
    <rect x="4" y="4" width="16" height="16" rx="3.5" />
    <circle cx="9" cy="9" r="1.1" fill="currentColor" stroke="none" />
    <circle cx="15" cy="15" r="1.1" fill="currentColor" stroke="none" />
    <circle cx="12" cy="12" r="1.1" fill="currentColor" stroke="none" />
  </Svg>
);

const STAR = "M12 3.6l2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z";
export const StarIcon = ({ filled = false, ...p }: Props & { filled?: boolean }) => (
  <Svg {...p} filled={filled}>
    <path d={STAR} />
  </Svg>
);
/** The star as markup, for Leaflet's HTML pin icons. */
export const STAR_SVG = `<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="${STAR}" fill="currentColor" stroke="#121212" stroke-width="1.5" stroke-linejoin="round"/></svg>`;

export const CheckIcon = (p: Props) => (
  <Svg {...p}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Svg>
);

export const ChevronLeftIcon = (p: Props) => (
  <Svg {...p}>
    <path d="m14.5 18-6-6 6-6" />
  </Svg>
);

export const CloseIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M6.5 6.5l11 11M17.5 6.5l-11 11" />
  </Svg>
);

export const DirectionsIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M4.5 11.2 19.5 4.5l-6.7 15-2.1-6.4z" />
  </Svg>
);

export const LocateIcon = (p: Props) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="6.5" />
    <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none" />
    <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" />
  </Svg>
);

export const ExternalIcon = (p: Props) => (
  <Svg {...p}>
    <path d="M14 5h5v5M19 5l-8 8M18 14v4.5A1.5 1.5 0 0 1 16.5 20h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10" />
  </Svg>
);
