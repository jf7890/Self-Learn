/**
 * Shared icon set — plain stroke-based SVGs (no icon library dependency,
 * no emoji). Every icon used anywhere in the app should come from here so
 * weight, sizing, and line style stay consistent across screens.
 */

const base = {
  width: 16,
  height: 16,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
};

export function IconPlay(props) {
  return <svg {...base} {...props}><polygon points="6 3 20 12 6 21 6 3" /></svg>;
}
export function IconPause(props) {
  return <svg {...base} {...props}><rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" /></svg>;
}
export function IconFullscreen(props) {
  return (
    <svg {...base} {...props}>
      <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" />
    </svg>
  );
}
export function IconVolume(props) {
  return <svg {...base} {...props}><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><path d="M15.5 8.5a5 5 0 0 1 0 7M18 6a8.5 8.5 0 0 1 0 12" /></svg>;
}
export function IconVolumeMuted(props) {
  return <svg {...base} {...props}><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" /><path d="m16 9 5 6M21 9l-5 6" /></svg>;
}
export function IconReplay10(props) {
  return <svg {...base} {...props}><path d="M3 9V4l3 3a9 9 0 1 1-1.7 9" /><text x="12" y="16" textAnchor="middle" fontSize="8" stroke="none" fill="currentColor">10</text></svg>;
}
export function IconForward10(props) {
  return <svg {...base} {...props}><path d="M21 9V4l-3 3a9 9 0 1 0 1.7 9" /><text x="12" y="16" textAnchor="middle" fontSize="8" stroke="none" fill="currentColor">10</text></svg>;
}
export function IconCheck(props) {
  return <svg {...base} {...props}><polyline points="20 6 9 17 4 12" /></svg>;
}
export function IconCheckCircle(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8.5 12.5l2.5 2.5 5-5" />
    </svg>
  );
}
export function IconMusic(props) {
  return (
    <svg {...base} {...props}>
      <path d="M9 18V5l12-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="16" r="3" />
    </svg>
  );
}
export function IconFileText(props) {
  return (
    <svg {...base} {...props}>
      <path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" />
      <path d="M14 3v5h5" /><path d="M9 13h6M9 17h6" />
    </svg>
  );
}
export function IconHelpCircle(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}
export function IconPaperclip(props) {
  return (
    <svg {...base} {...props}>
      <path d="M21 11.5l-9 9a4.24 4.24 0 0 1-6-6l9-9a2.83 2.83 0 0 1 4 4l-8.5 8.5a1.4 1.4 0 0 1-2-2L16 8" />
    </svg>
  );
}
export function IconTrophy(props) {
  return (
    <svg {...base} {...props}>
      <path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z" />
      <path d="M7 5H4a1 1 0 0 0-1 1 5 5 0 0 0 4 5M17 5h3a1 1 0 0 1 1 1 5 5 0 0 1-4 5" />
    </svg>
  );
}
export function IconChevronDown(props) {
  return <svg {...base} {...props}><polyline points="6 9 12 15 18 9" /></svg>;
}
export function IconChevronRight(props) {
  return <svg {...base} {...props}><polyline points="9 6 15 12 9 18" /></svg>;
}
export function IconChevronLeft(props) {
  return <svg {...base} {...props}><polyline points="15 6 9 12 15 18" /></svg>;
}
export function IconDownload(props) {
  return (
    <svg {...base} {...props}>
      <path d="M12 3v12" /><polyline points="7 11 12 16 17 11" /><path d="M5 20h14" />
    </svg>
  );
}
export function IconLogOut(props) {
  return (
    <svg {...base} {...props}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}
export function IconShield(props) {
  return <svg {...base} {...props}><path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z" /></svg>;
}
export function IconUsers(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
      <path d="M16 5.5a3.5 3.5 0 0 1 0 6.8M21.5 20a5.8 5.8 0 0 0-4.8-6" />
    </svg>
  );
}
export function IconLibrary(props) {
  return (
    <svg {...base} {...props}>
      <path d="M4 4h4v16H4zM10 4h4v16h-4zM17 4l4 15.5-3.8 1L13.4 5z" />
    </svg>
  );
}
export function IconSettings(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}
export function IconX(props) {
  return <svg {...base} {...props}><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>;
}
export function IconRefresh(props) {
  return (
    <svg {...base} {...props}>
      <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
      <path d="M3.5 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.65 4.36A9 9 0 0 0 20.5 15" />
    </svg>
  );
}
export function IconInbox(props) {
  return (
    <svg {...base} {...props}>
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
      <path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    </svg>
  );
}

export function IconMessageCircle(props) {
  return (
    <svg {...base} {...props}>
      <path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5 8.4 8.4 0 0 1-4-1L3 20l1.1-3.9A8.4 8.4 0 0 1 3 11.5 8.5 8.5 0 0 1 11.5 3 8.5 8.5 0 0 1 21 11.5z" />
    </svg>
  );
}
export function IconTrash(props) {
  return (
    <svg {...base} {...props}>
      <polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" /><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}

export function IconStar(props) {
  return (
    <svg {...base} {...props}>
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  );
}
export function IconEyeOff(props) {
  return (
    <svg {...base} {...props}>
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

export function IconActivity(props) {
  return (
    <svg {...base} {...props}>
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

export function IconMail(props) {
  return (
    <svg {...base} {...props}>
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="M2 6l10 7 10-7" />
    </svg>
  );
}

export function IconImage(props) {
  return (
    <svg {...base} {...props}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <path d="M21 15l-5-5L5 21" />
    </svg>
  );
}

export function IconBell(props) {
  return (
    <svg {...base} {...props}>
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}

export function IconSearch(props) {
  return (
    <svg {...base} {...props}>
      <circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

/**
 * The brand mark — a section flag, echoing how the course folders
 * themselves are marked in Explorer. Single source of truth so it renders
 * identically everywhere (nav, auth screens, section headers, thumbnails)
 * instead of five near-identical CSS clip-paths drifting apart over time.
 */
export function BrandMark({ size = 16, color: _color, ...props }) {
  return <img src="/brand-logo-192.png" width={size} height={size} alt="" style={{ objectFit: "cover", borderRadius: "18%" }} {...props} />;
}

export function IconLock(props) {
  return (
    <svg {...base} {...props}>
      <rect x="4" y="10" width="16" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </svg>
  );
}
