import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "./api";

const BrandingContext = createContext(null);

const DEFAULT_BRANDING = { site_name: "Self Learn", accent_color: "#e8a33d", logo_url: null, favicon_url: "/favicon.png" };

function hexToRgb(hex) {
  const clean = hex.replace("#", "");
  const num = parseInt(clean, 16);
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
}

function rgbToHex([r, g, b]) {
  return "#" + [r, g, b].map((x) => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, "0")).join("");
}

// Blend the accent toward black by `amount` (0-1) — used for the "dim"
// variant (borders, hover states) so any admin-picked color still gets a
// usable darker shade without them having to pick two colors.
function darken(hex, amount) {
  const [r, g, b] = hexToRgb(hex);
  return rgbToHex([r * (1 - amount), g * (1 - amount), b * (1 - amount)]);
}

function applyAccentColor(hex) {
  if (!/^#[0-9a-fA-F]{6}$/.test(hex)) return;
  const root = document.documentElement.style;
  const [r, g, b] = hexToRgb(hex);
  root.setProperty("--accent", hex);
  root.setProperty("--accent-dim", darken(hex, 0.45));
  root.setProperty("--accent-soft", `rgba(${r}, ${g}, ${b}, 0.12)`);
}

function applyFavicon(faviconUrl) {
  const existing = document.querySelector("link[data-ulearn-favicon]");
  if (!faviconUrl) {
    // Custom favicon was removed — drop our injected tag so the browser
    // falls back to whatever's in index.html (or its own default).
    if (existing) existing.remove();
    return;
  }
  let link = existing;
  if (!link) {
    link = document.createElement("link");
    link.rel = "icon";
    link.setAttribute("data-ulearn-favicon", "1");
    document.head.appendChild(link);
  }
  link.href = faviconUrl.startsWith("/branding/") ? `/api${faviconUrl}` : faviconUrl;
}

export function BrandingProvider({ children }) {
  const [branding, setBranding] = useState(DEFAULT_BRANDING);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(() => {
    api.getBranding()
      .then((b) => {
        const effective = { ...b, site_name: b.site_name === "uLearn" ? "Self Learn" : b.site_name, favicon_url: b.favicon_url || "/favicon.png" };
        setBranding(effective);
        applyAccentColor(effective.accent_color);
        applyFavicon(effective.favicon_url);
        document.title = effective.site_name;
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <BrandingContext.Provider value={{ ...branding, loaded, refresh }}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding() {
  return useContext(BrandingContext);
}
