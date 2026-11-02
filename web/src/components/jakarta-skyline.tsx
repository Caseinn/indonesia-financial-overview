type JakartaSkylineProps = {
  className?: string
}

export function JakartaSkyline({ className }: JakartaSkylineProps) {
  return (
    <svg
      viewBox="0 0 900 360"
      aria-hidden="true"
      className={className}
      preserveAspectRatio="xMaxYMax slice"
    >
      <defs>
        <radialGradient id="sky-sun" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#e9965c" stopOpacity="0.95" />
          <stop offset="55%" stopColor="#d8763f" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#c26a3c" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="sky-wash" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#7fa7a0" stopOpacity="0.38" />
          <stop offset="100%" stopColor="#7fa7a0" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="sky-base" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#245456" stopOpacity="0.82" />
          <stop offset="100%" stopColor="#0e3134" stopOpacity="0.94" />
        </linearGradient>
        <filter id="sky-soft" x="-35%" y="-35%" width="170%" height="170%">
          <feGaussianBlur stdDeviation="18" />
        </filter>
        <filter id="sky-paper" x="-12%" y="-12%" width="124%" height="124%">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.012 0.024"
            numOctaves="2"
            seed="9"
          />
          <feDisplacementMap in="SourceGraphic" scale="9" />
        </filter>
      </defs>

      <ellipse cx="650" cy="132" rx="290" ry="150" fill="url(#sky-wash)" filter="url(#sky-soft)" />
      <ellipse
        cx="420"
        cy="214"
        rx="230"
        ry="92"
        fill="#b7c9c4"
        opacity="0.22"
        filter="url(#sky-soft)"
      />

      <circle cx="706" cy="94" r="76" fill="url(#sky-sun)" />
      <circle cx="706" cy="94" r="40" fill="#e08a54" opacity="0.5" filter="url(#sky-soft)" />

      <g fill="#7fa7a0" opacity="0.34" filter="url(#sky-paper)">
        <rect x="330" y="238" width="26" height="82" />
        <rect x="366" y="252" width="18" height="68" />
        <rect x="398" y="228" width="32" height="92" />
        <rect x="446" y="246" width="20" height="74" />
        <rect x="482" y="220" width="38" height="100" />
        <rect x="534" y="250" width="22" height="70" />
        <rect x="566" y="232" width="30" height="88" />
        <rect x="610" y="256" width="18" height="64" />
        <rect x="642" y="240" width="26" height="80" />
        <rect x="756" y="250" width="22" height="70" />
        <rect x="790" y="236" width="34" height="84" />
        <rect x="836" y="254" width="20" height="66" />
      </g>

      <g fill="url(#sky-base)" filter="url(#sky-paper)">
        <rect x="0" y="286" width="54" height="34" />
        <rect x="58" y="266" width="22" height="54" />

        <rect x="86" y="262" width="70" height="58" />
        <ellipse cx="121" cy="262" rx="37" ry="21" />
        <rect x="94" y="248" width="6" height="16" />

        <rect x="166" y="276" width="34" height="44" />
        <rect x="204" y="258" width="24" height="62" />

        <rect x="244" y="286" width="56" height="34" />
        <polygon points="256,286 288,286 280,196 264,196" />
        <ellipse cx="272" cy="188" rx="9" ry="15" />

        <rect x="314" y="270" width="30" height="50" />
        <rect x="350" y="246" width="24" height="74" />
        <rect x="380" y="282" width="42" height="38" />
        <rect x="430" y="258" width="20" height="62" />
        <rect x="456" y="228" width="34" height="92" />
        <rect x="496" y="272" width="28" height="48" />

        <rect x="540" y="240" width="26" height="80" />
        <polygon points="540,240 566,240 553,222" />
        <rect x="576" y="268" width="36" height="52" />
        <rect x="620" y="250" width="22" height="70" />
        <rect x="648" y="282" width="40" height="38" />

        <rect x="704" y="268" width="30" height="52" />
        <rect x="742" y="244" width="24" height="76" />
        <rect x="774" y="278" width="44" height="42" />
        <rect x="826" y="260" width="22" height="60" />
        <rect x="854" y="286" width="46" height="34" />
      </g>

      <g fill="#f6f1e5" opacity="0.28">
        <rect x="464" y="238" width="4" height="4" />
        <rect x="472" y="248" width="4" height="4" />
        <rect x="480" y="238" width="4" height="4" />
        <rect x="544" y="252" width="4" height="4" />
        <rect x="554" y="264" width="4" height="4" />
        <rect x="746" y="256" width="4" height="4" />
        <rect x="754" y="270" width="4" height="4" />
        <rect x="832" y="272" width="4" height="4" />
      </g>

      <g fill="#0e3134" opacity="0.92">
        <ellipse cx="32" cy="314" rx="26" ry="14" />
        <ellipse cx="186" cy="318" rx="22" ry="11" />
        <ellipse cx="362" cy="316" rx="18" ry="9" />
        <ellipse cx="684" cy="320" rx="26" ry="12" />
        <ellipse cx="812" cy="318" rx="20" ry="10" />
      </g>

      <path d="M0 320 H900 V360 H0 Z" fill="#0b282b" opacity="0.9" />
      <g stroke="#8fb3aa" strokeLinecap="round" opacity="0.28">
        <line x1="120" y1="334" x2="210" y2="334" strokeWidth="2" />
        <line x1="260" y1="344" x2="330" y2="344" strokeWidth="2" />
        <line x1="470" y1="336" x2="560" y2="336" strokeWidth="2" />
        <line x1="620" y1="346" x2="720" y2="346" strokeWidth="2" />
        <line x1="760" y1="332" x2="850" y2="332" strokeWidth="2" />
      </g>
    </svg>
  )
}
