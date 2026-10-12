import { useCallback, useEffect, useRef, useState } from "react";
import { api, scoped } from "../../api";
import type { MeetingSummary } from "../../types";

/**
 * Server-side meeting search with a 220 ms debounce and offset pagination.
 * A response is applied only if the query it was made for is still current, and
 * pages are merged by meeting ID (never by title).
 */
export function useMeetingSearch(workspaceId: string) {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([]),
    [nextOffset, setNextOffset] = useState<number | null>(null);
  const [search, setSearch] = useState(""),
    [query, setQuery] = useState("");
  const currentQuery = useRef(query);
  currentQuery.current = query;
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 220);
    return () => clearTimeout(timer);
  }, [search]);

  const list = useCallback(
    async (offset = 0, signal?: AbortSignal) => {
      const snapshot = query;
      const params = new URLSearchParams({
        offset: String(offset),
        limit: "20",
        ...(query ? { q: query } : {}),
      });
      const result = await api<{ meetings: MeetingSummary[]; next_offset: number | null }>(
        scoped(workspaceId, "/meetings?" + params),
        { signal },
      );
      if (signal?.aborted || currentQuery.current !== snapshot) return;
      setMeetings((previous) =>
        offset
          ? [...new Map([...previous, ...result.meetings].map((row) => [row.id, row])).values()]
          : result.meetings,
      );
      setNextOffset(result.next_offset);
    },
    [workspaceId, query],
  );

  const reset = useCallback(() => {
    setMeetings([]);
    setNextOffset(null);
  }, []);

  return { meetings, nextOffset, search, setSearch, list, reset };
}
