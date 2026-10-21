import { useEffect, useRef, useState } from "react";

/**
 * A meter for one step's progress (people confirmed, outcomes approved). It fills as
 * work lands and bursts once when it first reaches the end. `target` names the spot
 * that flyTo tokens aim for.
 */
export default function StepProgress({
  done,
  total,
  label,
  target,
}: {
  done: number;
  total: number;
  /** What is being counted, read as "{done} of {total} {label}". */
  label: string;
  target?: string;
}) {
  const complete = total > 0 && done >= total;
  const previous = useRef(complete),
    [burst, setBurst] = useState(0);
  useEffect(() => {
    if (complete && !previous.current) setBurst((value) => value + 1);
    previous.current = complete;
  }, [complete]);
  if (!total) return null;
  const percent = Math.round((Math.min(done, total) / total) * 100);
  return (
    <div className="step-progress" data-complete={complete || undefined} data-fly-target={target}>
      <div
        className="step-progress-track"
        role="progressbar"
        aria-label={label[0].toUpperCase() + label.slice(1)}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={Math.min(done, total)}
        aria-valuetext={`${done} of ${total} ${label}`}
      >
        <span style={{ width: percent + "%" }} />
      </div>
      <span className="step-progress-count" aria-hidden="true">
        {done}/{total}
      </span>
      {burst > 0 && (
        <span className="step-progress-burst" key={burst} aria-hidden="true">
          {Array.from({ length: 8 }, (_, i) => (
            <i key={i} style={{ "--a": i * 45 + "deg" } as React.CSSProperties} />
          ))}
        </span>
      )}
    </div>
  );
}
