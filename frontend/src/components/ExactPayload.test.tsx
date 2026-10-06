import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { documentText, JiraPayload } from "./ExactPayload";

it("preserves stored document text and exposes every raw field without executing markup", () => {
  const description = { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: "Keep <script>alert(1)</script> as meeting evidence" }, { type: "hardBreak" }, { type: "text", text: "Next line" }] }] };
  expect(documentText(description)).toBe("Keep <script>alert(1)</script> as meeting evidence\nNext line\n");
  const view = render(<JiraPayload payload={{ fields: { summary: "Reviewed task", description, customfield_10: { id: "11" } } }} hash="stored-hash" />);
  expect(view.container.querySelector("script")).toBeNull();
  expect(screen.getByText(/Keep <script>/, { selector: "pre.payload-text" })).toBeInTheDocument();
  expect(screen.getByText("customfield_10")).toBeInTheDocument();
  expect(screen.getByText("stored-hash")).toBeInTheDocument();
});
