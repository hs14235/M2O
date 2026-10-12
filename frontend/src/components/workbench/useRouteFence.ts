import { useEffect, useRef } from "react";

/**
 * Async fence for work that outlives the screen that started it.
 *
 * `generation` increments whenever the route key changes. A request records the
 * generation it started in and applies its result only if that value is still
 * current, so a response that arrives after the user navigated away (even if they
 * came back to the same stage) is ignored. `mounted` guards state updates after
 * unmount. Cancellation alone is not enough: a write can succeed after its screen
 * is gone.
 */
export function useRouteFence(routeKey: string) {
  const currentRoute = useRef(routeKey),
    generation = useRef(0),
    mounted = useRef(true);
  if (currentRoute.current !== routeKey) {
    currentRoute.current = routeKey;
    generation.current += 1;
  }
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return { generation, mounted };
}
