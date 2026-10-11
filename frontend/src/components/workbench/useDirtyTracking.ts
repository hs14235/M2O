import { useCallback, useEffect, useRef } from "react";

/**
 * Tracks unsaved work: the transcript form plus any outcome editors that report
 * through `notifyDirty`. The shell is told whenever either kind is dirty so it can
 * guard navigation.
 */
export function useDirtyTracking(onDirty: (dirty: boolean) => void, transcriptIsDirty: boolean) {
  const dirtyItems = useRef(new Map<string, boolean>()),
    transcriptDirty = useRef(false);
  const hasDirtyItems = useCallback(() => [...dirtyItems.current.values()].some(Boolean), []);
  const notifyDirty = useCallback(
    (id: string, dirty: boolean) => {
      dirtyItems.current.set(id, dirty);
      onDirty(transcriptDirty.current || hasDirtyItems());
    },
    [onDirty, hasDirtyItems],
  );
  useEffect(() => {
    transcriptDirty.current = transcriptIsDirty;
    onDirty(transcriptIsDirty || hasDirtyItems());
  }, [transcriptIsDirty, onDirty, hasDirtyItems]);
  return { dirtyItems, transcriptDirty, notifyDirty, hasDirtyItems };
}
