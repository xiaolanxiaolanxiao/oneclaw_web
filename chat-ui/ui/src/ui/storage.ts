const KEY = "openclaw.control.settings.v1";

import type { ThemeMode } from "./theme.ts";

export type UiSettings = {
  gatewayUrl: string;
  token: string;
  sessionKey: string;
  lastActiveSessionKey: string;
  oneclawView: "chat" | "settings" | "skills";
  theme: ThemeMode;
  chatFocusMode: boolean;
  chatShowThinking: boolean;
  splitRatio: number; // Sidebar split ratio (0.4 to 0.7, default 0.6)
  navCollapsed: boolean; // Collapsible sidebar state
  navGroupsCollapsed: Record<string, boolean>; // Which nav groups are collapsed
};

// Read Vite env vars (injected at build time via .env / .env.production)
const ENV_GATEWAY_URL = (typeof import.meta !== "undefined" && (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_GATEWAY_URL) || "";
const ENV_GATEWAY_TOKEN = (typeof import.meta !== "undefined" && (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_GATEWAY_TOKEN) || "";

export function loadSettings(): UiSettings {
  const defaultUrl = (() => {
    // 1) If env var VITE_GATEWAY_URL is set (build time), use it
    if (ENV_GATEWAY_URL) {
      return ENV_GATEWAY_URL;
    }
    // 2) file:// protocol (Electron loadFile) → location.host is empty.
    //    Fall back to the default gateway loopback address.
    if (!location.host) {
      return "ws://127.0.0.1:18789";
    }
    // 3) Browser deployment: derive from current page origin
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${location.host}/__openclaw__/ws`;
  })();

  // Default token from env var (for self-hosted / private deployments)
  const defaultToken = ENV_GATEWAY_TOKEN;

  const defaults: UiSettings = {
    gatewayUrl: defaultUrl,
    token: defaultToken,
    sessionKey: "main",
    lastActiveSessionKey: "main",
    oneclawView: "chat",
    theme: "system",
    chatFocusMode: false,
    chatShowThinking: true,
    splitRatio: 0.6,
    navCollapsed: false,
    navGroupsCollapsed: {},
  };

  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) {
      return defaults;
    }
    const parsed = JSON.parse(raw) as Partial<UiSettings>;
    return {
      gatewayUrl:
        typeof parsed.gatewayUrl === "string" && parsed.gatewayUrl.trim()
          ? parsed.gatewayUrl.trim()
          : defaults.gatewayUrl,
      token: typeof parsed.token === "string" ? parsed.token : defaults.token,
      sessionKey:
        typeof parsed.sessionKey === "string" && parsed.sessionKey.trim()
          ? parsed.sessionKey.trim()
          : defaults.sessionKey,
      lastActiveSessionKey:
        typeof parsed.lastActiveSessionKey === "string" && parsed.lastActiveSessionKey.trim()
          ? parsed.lastActiveSessionKey.trim()
          : (typeof parsed.sessionKey === "string" && parsed.sessionKey.trim()) ||
            defaults.lastActiveSessionKey,
      oneclawView: defaults.oneclawView,
      theme:
        parsed.theme === "light" || parsed.theme === "dark" || parsed.theme === "system"
          ? parsed.theme
          : defaults.theme,
      chatFocusMode:
        typeof parsed.chatFocusMode === "boolean" ? parsed.chatFocusMode : defaults.chatFocusMode,
      chatShowThinking:
        typeof parsed.chatShowThinking === "boolean"
          ? parsed.chatShowThinking
          : defaults.chatShowThinking,
      splitRatio:
        typeof parsed.splitRatio === "number" &&
        parsed.splitRatio >= 0.4 &&
        parsed.splitRatio <= 0.7
          ? parsed.splitRatio
          : defaults.splitRatio,
      navCollapsed:
        typeof parsed.navCollapsed === "boolean" ? parsed.navCollapsed : defaults.navCollapsed,
      navGroupsCollapsed:
        typeof parsed.navGroupsCollapsed === "object" && parsed.navGroupsCollapsed !== null
          ? parsed.navGroupsCollapsed
          : defaults.navGroupsCollapsed,
    };
  } catch {
    return defaults;
  }
}

export function saveSettings(next: UiSettings) {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const existing = JSON.parse(raw);
      const merged = { ...existing, ...next };
      localStorage.setItem(KEY, JSON.stringify(merged));
      return;
    }
  } catch {}
  localStorage.setItem(KEY, JSON.stringify(next));
}
