import { useEffect, useRef } from "react";

/**
 * Opens a provider's consent page in a new tab, so this page and any other tool being
 * set up stay where they are. The tab opens inside the click (popup blockers allow
 * that) and is pointed at the URL once the server returns it; its opener is cleared
 * first. If the browser refuses new tabs, consent opens here as before.
 */
export async function openConsent(load: () => Promise<string | undefined>) {
  const tab = window.open("about:blank", "_blank");
  try {
    const url = await load();
    if (!url) {
      tab?.close();
      return;
    }
    if (tab && !tab.closed) {
      tab.opener = null;
      tab.location.href = url;
    } else window.location.assign(url);
  } catch (error) {
    tab?.close();
    throw error;
  }
}

/**
 * Calls back when the person comes back to this tab, for example after finishing
 * consent in another one, so connection status can be read again. Read-only callers
 * only: it never cancels a request in flight.
 */
export function useOnReturn(callback: () => void) {
  const latest = useRef(callback);
  latest.current = callback;
  useEffect(() => {
    const returned = () => {
      if (!document.hidden) latest.current();
    };
    window.addEventListener("focus", returned);
    document.addEventListener("visibilitychange", returned);
    return () => {
      window.removeEventListener("focus", returned);
      document.removeEventListener("visibilitychange", returned);
    };
  }, []);
}
