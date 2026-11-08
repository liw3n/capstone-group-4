export interface ChatPanelSize {
  width: number;
  height: number;
}

export const DEFAULT_CHAT_PANEL_SIZE: ChatPanelSize = { width: 460, height: 640 };
export const MIN_CHAT_PANEL_SIZE: ChatPanelSize = { width: 360, height: 420 };
// Space kept between the panel and the viewport edges (bottom/right offset plus a top/left gutter).
export const CHAT_PANEL_VIEWPORT_MARGIN = 40;
export const CHAT_PANEL_SIZE_STORAGE_KEY = 'pulse.chatPanelSize';

export function clampChatPanelSize(
  size: ChatPanelSize,
  viewport: ChatPanelSize,
): ChatPanelSize {
  const maxWidth = Math.max(MIN_CHAT_PANEL_SIZE.width, viewport.width - CHAT_PANEL_VIEWPORT_MARGIN);
  const maxHeight = Math.max(
    MIN_CHAT_PANEL_SIZE.height,
    viewport.height - CHAT_PANEL_VIEWPORT_MARGIN,
  );
  return {
    width: Math.round(Math.min(Math.max(size.width, MIN_CHAT_PANEL_SIZE.width), maxWidth)),
    height: Math.round(Math.min(Math.max(size.height, MIN_CHAT_PANEL_SIZE.height), maxHeight)),
  };
}

/**
 * The panel is anchored to the bottom-right corner, so dragging its top-left
 * handle left/up grows it and right/down shrinks it.
 */
export function resizeFromTopLeft(
  start: ChatPanelSize,
  deltaX: number,
  deltaY: number,
  viewport: ChatPanelSize,
): ChatPanelSize {
  return clampChatPanelSize(
    { width: start.width - deltaX, height: start.height - deltaY },
    viewport,
  );
}

export function parseStoredChatPanelSize(raw: string | null): ChatPanelSize | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (
      typeof value === 'object' &&
      value !== null &&
      Number.isFinite((value as ChatPanelSize).width) &&
      Number.isFinite((value as ChatPanelSize).height)
    ) {
      return { width: (value as ChatPanelSize).width, height: (value as ChatPanelSize).height };
    }
  } catch {
    // Ignore malformed stored values and fall back to the default size.
  }
  return null;
}
