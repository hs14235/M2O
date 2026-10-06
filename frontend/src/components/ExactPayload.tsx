/** A text view of stored provider content; raw JSON stays available for every field. */
export function documentText(value: unknown, depth = 0): string {
  if (depth > 24 || value == null) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(child => documentText(child, depth + 1)).join("");
  if (typeof value !== "object") return "";
  const node = value as { type?: string; text?: string; content?: unknown[] };
  if (node.type === "text") return node.text || "";
  if (node.type === "hardBreak") return "\n";
  const text = documentText(node.content || [], depth + 1);
  if (node.type === "listItem") return "• " + text.trimEnd() + "\n";
  if (["paragraph", "heading", "codeBlock", "blockquote"].includes(node.type || "")) return text + "\n";
  return text;
}

export function PayloadInspection({ payload, hash }: { payload: unknown; hash: string }) {
  return <details className="payload-inspection"><summary>Inspect stored payload & snapshot hash</summary><p className="muted">Snapshot hash: <code>{hash}</code></p><pre>{JSON.stringify(payload, null, 2)}</pre></details>;
}

export function JiraPayload({ payload, hash }: { payload: { fields: Record<string, unknown> }; hash: string }) {
  const fields = payload.fields;
  return <article className="exact-payload"><h3>{String(fields.summary || "Untitled issue")}</h3>{fields.description != null && <><span className="eyebrow">Description · stored document text</span><pre className="payload-text">{documentText(fields.description)}</pre></>}<dl className="payload-fields">{Object.entries(fields).filter(([key]) => !["summary", "description"].includes(key)).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{typeof value === "string" ? value : JSON.stringify(value)}</dd></div>)}</dl><PayloadInspection payload={payload} hash={hash} /></article>;
}
