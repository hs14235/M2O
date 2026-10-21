import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import StepProgress from "./StepProgress";

it("reports progress accessibly and bursts only when it first completes", () => {
  const { container, rerender } = render(<StepProgress done={1} total={3} label="outcomes approved" />);
  const bar = screen.getByRole("progressbar", { name: "Outcomes approved" });
  expect(bar).toHaveAttribute("aria-valuetext", "1 of 3 outcomes approved");
  expect(container.querySelector(".step-progress-burst")).toBeNull();
  rerender(<StepProgress done={3} total={3} label="outcomes approved" />);
  expect(container.querySelector(".step-progress-burst")).not.toBeNull();
  expect(container.querySelector("[data-complete]")).not.toBeNull();
});

it("starts complete without a burst and renders nothing with no work", () => {
  const { container, rerender } = render(<StepProgress done={2} total={2} label="people confirmed" />);
  expect(container.querySelector(".step-progress-burst")).toBeNull();
  rerender(<StepProgress done={0} total={0} label="people confirmed" />);
  expect(container).toBeEmptyDOMElement();
});
