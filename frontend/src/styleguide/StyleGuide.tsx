import { useEffect, useState, type ReactNode } from "react";
import themeCss from "../theme.css?raw";
import motionCss from "../motion.css?raw";
import { contrast, pairs, themes, tokenValue } from "../design-tokens";
import { departmentExperience, useMotionPreference } from "../components/DepartmentExperience";
import { ErrorNotice, Empty } from "../components/Feedback";
import MeetingList from "../components/MeetingList";
import { OutcomeCard, kindNames } from "../components/OutcomeCard";
import { ThemeSwitch } from "../components/ThemeSwitch";
import { JobStatus } from "../components/workbench/JobStatus";
import type { Department, Kind } from "../types";
import { catalog, colorGroups, tokensIn, type Group } from "./catalog";
import { apiError, jobs, meetings, outcomes, participants } from "./fixtures";

// The living reference for tokens and components. Values are read from the
// shipped stylesheets, and components are the real ones fed synthetic records.

const { light, dark } = themes(themeCss);
const value = (name: string) => tokenValue(themeCss, name) ?? tokenValue(motionCss, name) ?? "";
const noop = () => {};

const sections = [
  ["colors", "Colors"],
  ["type", "Type"],
  ["shape", "Shape"],
  ["motion", "Motion"],
  ["components", "Components"],
  ["deprecated", "Deprecated aliases"],
  ["rules", "Rules"],
] as const;

// Literal class names so Tailwind generates them.
const radius: Record<string, string> = { "r-sm": "rounded-sm", "r-md": "rounded-md", "r-lg": "rounded-lg" };
const shadow: Record<string, string> = {
  "shadow-sm": "shadow-sm",
  "shadow-md": "shadow-md",
  "shadow-lg": "shadow-lg",
};
const spacing = ["w-1", "w-2", "w-3", "w-4", "w-5", "w-6", "w-7", "w-8", "w-9", "w-10", "w-11", "w-12"];
const kindBorder: Record<Kind, string> = {
  action: "border-t-k-action",
  decision: "border-t-k-decision",
  blocker: "border-t-k-blocker",
  follow_up: "border-t-k-follow",
  risk: "border-t-k-risk",
};

const cell = "border-b border-border px-3 py-2 text-left align-top";
const head = cell + " font-semibold text-text-2";

function Section({
  id,
  title,
  lead,
  children,
}: {
  id: string;
  title: string;
  lead: string;
  children: ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={id + "-heading"} className="scroll-mt-6 border-t border-border py-10">
      <h2 id={id + "-heading"}>{title}</h2>
      <p className="mb-6 max-w-2xl text-text-2">{lead}</p>
      {children}
    </section>
  );
}

function Token({ name }: { name: string }) {
  return <code className="font-mono text-sm text-text">{"--" + name}</code>;
}

function Table({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    // Focusable so keyboard users can scroll a table that is wider than a phone.
    <div
      role="region"
      aria-label={caption}
      tabIndex={0}
      className="mb-8 overflow-x-auto rounded-md border border-border bg-surface"
    >
      <table className="w-full border-collapse text-sm">
        <caption className="px-3 py-2 text-left font-semibold">{caption}</caption>
        {children}
      </table>
    </div>
  );
}

function Swatch({ name }: { name: string }) {
  const info = catalog[name];
  return (
    <li className="flex gap-3 rounded-md border border-border bg-surface p-3">
      <span
        aria-hidden="true"
        className="size-12 shrink-0 rounded-sm border border-border"
        style={{ background: "var(--" + name + ")" }}
      />
      <span className="min-w-0 text-sm">
        <Token name={name} />
        <span className="block text-text-2">{info.note}</span>
        <span className="block font-mono text-xs text-text-3">
          {light[name] ? "light " + light[name] + " · dark " + dark[name] : value(name)}
          {info.utility && " · " + info.utility}
        </span>
      </span>
    </li>
  );
}

function ColorGroup({ group }: { group: Group }) {
  return (
    <>
      <h3>{group}</h3>
      <ul className="mb-8 grid list-none gap-3 p-0 sm:grid-cols-2 lg:grid-cols-3">
        {tokensIn(group).map((name) => (
          <Swatch key={name} name={name} />
        ))}
      </ul>
    </>
  );
}

function TokenTable({
  caption,
  group,
  sample,
}: {
  caption: string;
  group: Group;
  sample?: (name: string) => ReactNode;
}) {
  return (
    <Table caption={caption}>
      <thead>
        <tr>
          <th scope="col" className={head}>
            Token
          </th>
          <th scope="col" className={head}>
            Value
          </th>
          <th scope="col" className={head}>
            Use
          </th>
          {sample && (
            <th scope="col" className={head}>
              Example
            </th>
          )}
        </tr>
      </thead>
      <tbody>
        {tokensIn(group).map((name) => (
          <tr key={name}>
            <th scope="row" className={cell + " font-normal"}>
              <Token name={name} />
            </th>
            <td className={cell + " font-mono text-xs"}>{value(name)}</td>
            <td className={cell + " text-text-2"}>
              {catalog[name].note}
              {catalog[name].utility && (
                <span className="block font-mono text-xs">{catalog[name].utility}</span>
              )}
            </td>
            {sample && <td className={cell}>{sample(name)}</td>}
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

function Colors() {
  return (
    <Section
      id="colors"
      title="Colors"
      lead="Swatches follow the theme you pick above. Every value comes from theme.css; the contrast table is computed from the same values the contrast test checks."
    >
      {colorGroups.map((group) => (
        <ColorGroup key={group} group={group} />
      ))}
      <Table caption="Contrast of the checked pairs (WCAG 2.1)">
        <thead>
          <tr>
            {["Foreground", "Background", "Minimum", "Light", "Dark", "Result"].map((label) => (
              <th key={label} scope="col" className={head}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {pairs.map(([fg, bg, minimum]) => {
            const ratios = [contrast(light[fg], light[bg]), contrast(dark[fg], dark[bg])];
            const pass = ratios.every((ratio) => ratio >= minimum);
            return (
              <tr key={fg + bg}>
                <th scope="row" className={cell + " font-normal"}>
                  <Token name={fg} />
                </th>
                <td className={cell}>
                  <Token name={bg} />
                </td>
                <td className={cell}>{minimum}:1</td>
                {ratios.map((ratio, i) => (
                  <td key={i} className={cell + " font-mono text-xs"}>
                    {ratio.toFixed(2)}:1
                  </td>
                ))}
                <td className={cell + " font-semibold " + (pass ? "text-success" : "text-danger")}>
                  {pass ? "Pass" : "Fail"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </Table>
    </Section>
  );
}

const typeScale: { label: string; spec: string; sample: ReactNode }[] = [
  {
    label: "h1",
    spec: "clamp(1.75rem, 2.8vw, 2.4rem) · 600",
    sample: <h1 role="none">Review what matters.</h1>,
  },
  { label: "h2", spec: "1.35rem · 600", sample: <h2 role="none">Your meetings</h2> },
  { label: "h3", spec: "1.1rem · 600", sample: <h3 role="none">Publish the release checklist</h3> },
  {
    label: "Body",
    spec: "1rem · line height 1.6",
    sample: <p className="mb-0">Each outcome links to its source.</p>,
  },
  {
    label: ".muted",
    spec: "0.84rem · --text-2",
    sample: <p className="muted mb-0">Suggested owner: Priya</p>,
  },
  { label: ".eyebrow", spec: "0.74rem · 750 · uppercase", sample: <span className="eyebrow">Decision</span> },
  { label: ".badge", spec: "0.72rem · 650", sample: <span className="badge">draft · v1</span> },
  { label: "Mono", spec: "--mono", sample: <code>styleguide-meeting-1</code> },
];

function Type() {
  return (
    <Section
      id="type"
      title="Type"
      lead="There are no type-scale tokens yet: sizes come from the element and class rules in styles.css. The two font tokens are below."
    >
      <TokenTable
        caption="Font tokens"
        group="Fonts"
        sample={(name) => <span style={{ fontFamily: "var(--" + name + ")" }}>Meeting 2 Outcomes 0123</span>}
      />
      <Table caption="Element scale">
        <thead>
          <tr>
            {["Element", "Size and weight", "Sample"].map((label) => (
              <th key={label} scope="col" className={head}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {typeScale.map((row) => (
            <tr key={row.label}>
              <th scope="row" className={cell + " font-mono text-xs font-normal"}>
                {row.label}
              </th>
              <td className={cell + " text-text-2"}>{row.spec}</td>
              <td className={cell}>{row.sample}</td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Section>
  );
}

function Shape() {
  return (
    <Section
      id="shape"
      title="Shape"
      lead="Corner radius, elevation and the overlay are tokens. Spacing uses Tailwind's default scale (0.25rem steps), which is not an M2O token."
    >
      <TokenTable
        caption="Radius"
        group="Radius"
        sample={(name) => (
          <span className={"block h-10 w-20 border border-border-strong bg-surface-2 " + radius[name]} />
        )}
      />
      <TokenTable
        caption="Elevation and overlay"
        group="Effects"
        sample={(name) =>
          name === "overlay" ? (
            <span className="block h-10 w-20 rounded-sm bg-overlay" />
          ) : (
            <span className={"block h-10 w-20 rounded-md bg-surface " + shadow[name]} />
          )
        }
      />
      <h3>Spacing (Tailwind 1–12)</h3>
      <ul className="mb-8 list-none space-y-2 p-0">
        {spacing.map((width, i) => (
          <li key={width} className="flex items-center gap-3 text-sm">
            <code className="w-24 font-mono text-xs">
              {width.replace("w-", "")} · {(i + 1) * 0.25}rem
            </code>
            <span className={"block h-3 rounded-sm bg-accent " + width} />
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Demo({ title, children }: { title: string; children: ReactNode }) {
  return (
    <figure className="m-0 rounded-md border border-border bg-surface p-4">
      <figcaption className="mb-3 text-sm font-semibold">{title}</figcaption>
      {children}
    </figure>
  );
}

function Motion({ calm }: { calm: boolean }) {
  const [replay, setReplay] = useState(0);
  return (
    <Section
      id="motion"
      title="Motion"
      lead="All motion comes from motion.css: 120–280 ms on shared curves, plus --dur-4 for the signature moment. Calm mode and the system reduced-motion setting turn it all off."
    >
      <TokenTable caption="Durations" group="Durations" />
      <TokenTable
        caption="Curves"
        group="Curves"
        sample={(name) => <span className="font-mono text-xs">{"var(--" + name + ")"}</span>}
      />
      <TokenTable caption="Sequencing" group="Sequencing" />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => setReplay((count) => count + 1)}>
          Replay demos
        </button>
        <p role="status" className="mb-0 text-sm text-text-2">
          {calm
            ? "Motion is off. The demos show their end state."
            : "Demos play once when they appear; replay to see them again."}
        </p>
      </div>
      <div key={replay} className="grid gap-4 md:grid-cols-2">
        <Demo title=".reveal: content arriving">
          <div className="reveal rounded-sm bg-surface-2 p-3 text-sm">A screen's main content.</div>
        </Demo>
        <Demo title=".reveal-seq: heading, lead, body in order">
          <div className="reveal-seq space-y-2 text-sm">
            <p className="mb-0 font-semibold">Heading</p>
            <p className="mb-0 text-text-2">Lead text</p>
            <p className="mb-0 rounded-sm bg-surface-2 p-2">Body</p>
          </div>
        </Demo>
        <Demo title=".stagger: list items">
          <ul className="stagger m-0 list-none space-y-1 p-0 text-sm">
            {["First", "Second", "Third", "Fourth", "Fifth"].map((item) => (
              <li key={item} className="rounded-sm bg-surface-2 px-2 py-1">
                {item}
              </li>
            ))}
          </ul>
        </Demo>
        <Demo title="Button press and expandable section">
          <button type="button">Press and hold</button>
          <details className="mt-3 text-sm">
            <summary>Show details</summary>
            <p className="mb-0">Sections open and close instead of jumping.</p>
          </details>
        </Demo>
      </div>
    </Section>
  );
}

// Hover and focus shown at rest; utilities beat the legacy rules because of layer order.
const buttonRows: { label: string; className: string; hover: string }[] = [
  { label: "Default", className: "", hover: "bg-accent-soft border-accent" },
  { label: ".primary", className: "primary", hover: "bg-accent-hover" },
  { label: ".quiet", className: "quiet", hover: "bg-accent-soft border-accent" },
  { label: ".danger", className: "danger", hover: "bg-danger-hover" },
];

function Components() {
  const field = "mb-0";
  return (
    <Section
      id="components"
      title="Components"
      lead="The app's own components with synthetic records. Nothing here is connected to a workspace, so actions that would save show an error."
    >
      <h3>Buttons</h3>
      <Table caption="Button variants and states (hover and focus are shown at rest)">
        <thead>
          <tr>
            {["Variant", "Default", "Hover", "Focus", "Disabled", "Busy"].map((label) => (
              <th key={label} scope="col" className={head}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {buttonRows.map((row) => (
            <tr key={row.label}>
              <th scope="row" className={cell + " font-mono text-xs font-normal"}>
                {row.label}
              </th>
              <td className={cell}>
                <button type="button" className={row.className}>
                  Save
                </button>
              </td>
              <td className={cell}>
                <button type="button" className={row.className + " " + row.hover}>
                  Save
                </button>
              </td>
              <td className={cell}>
                <button
                  type="button"
                  className={row.className + " outline-2 outline-offset-2 outline-accent"}
                >
                  Save
                </button>
              </td>
              <td className={cell}>
                <button type="button" className={row.className} disabled>
                  Save
                </button>
              </td>
              <td className={cell}>
                <button type="button" className={row.className} disabled aria-busy="true">
                  Saving…
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </Table>

      <h3>Inputs</h3>
      <div className="mb-8 grid gap-4 rounded-md border border-border bg-surface p-4 sm:grid-cols-2">
        <label className={field}>
          Empty
          <input placeholder="Meeting title" />
        </label>
        <label className={field}>
          Filled
          <input defaultValue="Release readiness" />
        </label>
        <div>
          <label className={field}>
            Invalid
            <input
              defaultValue="20261022"
              aria-invalid="true"
              aria-describedby="styleguide-invalid-hint"
              className="border-danger"
            />
          </label>
          <p id="styleguide-invalid-hint" className="mt-1 mb-0 text-sm text-danger">
            Enter a date as YYYY-MM-DD.
          </p>
        </div>
        <label className={field}>
          Disabled
          <input defaultValue="Read only for viewers" disabled />
        </label>
      </div>

      <h3>Badges and kind tags</h3>
      <div className="mb-4 flex flex-wrap gap-2">
        {["draft · v1", "approved · v2", "done · v3", "dismissed · v2"].map((text) => (
          <span key={text} className="badge">
            {text}
          </span>
        ))}
      </div>
      <ul className="mb-8 grid list-none gap-3 p-0 sm:grid-cols-3 lg:grid-cols-5">
        {(Object.keys(kindNames) as Kind[]).map((kind) => (
          <li
            key={kind}
            className={"rounded-md border border-t-3 border-border bg-surface p-3 " + kindBorder[kind]}
          >
            <span className="eyebrow mb-0">{kindNames[kind]}</span>
          </li>
        ))}
      </ul>

      <h3>Outcome card</h3>
      <div className="mb-8 grid items-start gap-4 lg:grid-cols-2">
        {outcomes.map(({ label, item, workspace }) => (
          <figure key={item.id} className="m-0">
            <figcaption className="mb-2 text-sm font-semibold text-text-2">{label}</figcaption>
            <OutcomeCard
              item={item}
              participants={participants}
              workspace={workspace}
              meetingId="styleguide-meeting-1"
              onSaved={noop}
              onDirty={noop}
              selected={false}
              onSelect={noop}
            />
          </figure>
        ))}
      </div>

      <h3>Error and empty states</h3>
      <ErrorNotice error={apiError} />
      <Empty>No permitted meetings match this title or identifier.</Empty>

      <h3>Job status</h3>
      <div className="mb-8">
        {jobs.map((job) => (
          <JobStatus key={job.id} job={job} role="owner" onReconcile={noop} />
        ))}
      </div>

      <h3>Meeting list</h3>
      <div className="grid items-start gap-4 lg:grid-cols-3">
        {[
          { label: "Empty", rows: [], loading: false, more: false },
          { label: "Loading", rows: [], loading: true, more: false },
          { label: "With meetings", rows: meetings, loading: false, more: true },
        ].map((state) => (
          <figure key={state.label} className="m-0 min-w-0">
            <figcaption className="mb-2 text-sm font-semibold text-text-2">{state.label}</figcaption>
            <MeetingList
              meetings={state.rows}
              query=""
              onQuery={noop}
              loading={state.loading}
              hasMore={state.more}
              onMore={noop}
              onOpen={noop}
              visitor={false}
            />
          </figure>
        ))}
      </div>
    </Section>
  );
}

function Deprecated() {
  return (
    <Section
      id="deprecated"
      title="Deprecated aliases"
      lead="Older names the hand-written stylesheets still use, mapped onto the tokens. They are not retired in this phase; new code uses the replacement."
    >
      <Table caption="Aliases and their replacements">
        <thead>
          <tr>
            {["Alias", "Use instead", "Swatch"].map((label) => (
              <th key={label} scope="col" className={head}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tokensIn("Deprecated aliases").map((name) => (
            <tr key={name}>
              <th scope="row" className={cell + " font-normal"}>
                <Token name={name} />
              </th>
              <td className={cell}>
                <Token name={catalog[name].replacement!} />
              </td>
              <td className={cell}>
                <span
                  aria-hidden="true"
                  className="block size-6 rounded-sm border border-border"
                  style={{ background: "var(--" + name + ")" }}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </Table>
    </Section>
  );
}

function Rules() {
  return (
    <Section id="rules" title="Rules" lead="How new interface code uses this system.">
      <ul className="max-w-2xl space-y-2 pl-5 leading-relaxed">
        <li>
          Write new components with Tailwind utilities on the theme tokens (bg-surface, text-text-2,
          border-border).
        </li>
        <li>
          Utilities beat the legacy stylesheets through layer order (theme, legacy, motion, utilities), so a
          utility on a new component always wins over an older element rule such as button {"{}"}.
        </li>
        <li>
          No hex values in components: add or change a token in theme.css, where the contrast test checks it.
        </li>
        <li>
          Motion only through motion.css and its tokens, so calm mode and reduced motion can turn every
          animation off.
        </li>
        <li>Light and dark are both first-class: check a change in both before shipping it.</li>
      </ul>
    </Section>
  );
}

const departments = Object.keys(departmentExperience) as Department[];

export default function StyleGuide() {
  const motion = useMotionPreference();
  const [department, setDepartment] = useState<Department>("engineering");
  useEffect(() => {
    document.documentElement.dataset.department = department;
  }, [department]);
  return (
    <div className="min-h-screen bg-bg text-text">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2">
        Skip to content
      </a>
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-4 px-4 py-6">
          <div>
            <p className="eyebrow">M2O design system</p>
            <h1 className="mb-1">Style guide</h1>
            <p className="mb-0 text-text-2">
              Tokens and components in every state. <a href="/">Back to the app</a>
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <ThemeSwitch />
            <button
              type="button"
              aria-pressed={motion.calm}
              disabled={motion.reduced}
              onClick={motion.toggle}
            >
              Calm motion
            </button>
            <label className="mb-0 flex items-center gap-2">
              Department
              <select
                className="mt-0 w-auto"
                value={department}
                onChange={(event) => setDepartment(event.target.value as Department)}
              >
                {departments.map((key) => (
                  <option key={key} value={key}>
                    {departmentExperience[key].name}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <nav aria-label="Sections" className="mx-auto max-w-6xl px-4 pb-3">
          <ul className="m-0 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-sm">
            {sections.map(([id, label]) => (
              <li key={id}>
                <a href={"#" + id}>{label}</a>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4">
        <Colors />
        <Type />
        <Shape />
        <Motion calm={motion.calm} />
        <Components />
        <Deprecated />
        <Rules />
      </main>
    </div>
  );
}
