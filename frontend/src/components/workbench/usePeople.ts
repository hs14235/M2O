import { useCallback, useEffect, useState } from "react";
import { api, scoped } from "../../api";
import type { Participant } from "../../types";

/** The workspace participant directory, reloaded when the workspace changes. */
export function usePeople(workspaceId: string, onError: (error: unknown) => void) {
  const [people, setPeople] = useState<Participant[]>([]);
  const loadPeople = useCallback(
    async (signal?: AbortSignal) => {
      const result = await api<Participant[]>(scoped(workspaceId, "/participants"), { signal });
      if (!signal?.aborted) setPeople(result);
    },
    [workspaceId],
  );
  useEffect(() => {
    const controller = new AbortController();
    loadPeople(controller.signal).catch((e) => {
      if (!controller.signal.aborted) onError(e);
    });
    return () => controller.abort();
    // onError is a state setter, which React keeps stable, so it is not a dependency.
  }, [loadPeople]);
  return { people, loadPeople };
}
