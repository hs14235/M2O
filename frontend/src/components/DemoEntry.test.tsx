import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as client from "../api";
import DemoEntry from "./DemoEntry";

afterEach(() => vi.restoreAllMocks());
it("starts a separate visitor session only on explicit action, then loads its authenticated account", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValue({ enabled: true, scenarios: [] }), onStarted = vi.fn().mockResolvedValue(undefined);
  render(<DemoEntry onStarted={onStarted} />);
  const start = await screen.findByRole("button", { name: "Explore the isolated demo" });
  expect(request.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(0);
  await userEvent.click(start);
  await waitFor(() => expect(onStarted).toHaveBeenCalledOnce());
  expect(request).toHaveBeenCalledWith("/demo/start", { method: "POST" });
});
it("does not expose demo start when the server disables visitor access", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValue({ enabled: false, scenarios: [] });
  render(<DemoEntry onStarted={vi.fn()} />);
  await screen.findByText(/Visitor demos are disabled/);
  expect(screen.queryByRole("button", { name: "Explore the isolated demo" })).toBeNull();
  expect(request).toHaveBeenCalledTimes(1);
});
it("retains a recoverable error if session start is rejected", async () => {
  const request = vi.spyOn(client, "api").mockResolvedValueOnce({ enabled: true, scenarios: [] }).mockRejectedValueOnce(new client.ApiError(429, "Demo quota reached"));
  const onStarted = vi.fn(); render(<DemoEntry onStarted={onStarted} />);
  await userEvent.click(await screen.findByRole("button", { name: "Explore the isolated demo" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Demo quota reached");
  expect(onStarted).not.toHaveBeenCalled();
  expect(request).toHaveBeenCalledTimes(2);
});
