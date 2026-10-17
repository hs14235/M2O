// What each design token is for. catalog.test.ts fails when theme.css or
// motion.css declares a token missing here, or this lists one they dropped.

export type Group =
  | "Surfaces"
  | "Text"
  | "Accent"
  | "Signal"
  | "Danger"
  | "Success"
  | "Brand"
  | "Outcome kinds"
  | "Departments"
  | "Effects"
  | "Fonts"
  | "Radius"
  | "Durations"
  | "Curves"
  | "Sequencing"
  | "Deprecated aliases";

export interface TokenInfo {
  group: Group;
  note: string;
  /** The Tailwind utility that reads this token, when there is one. */
  utility?: string;
  /** For deprecated aliases: the token to use instead. */
  replacement?: string;
}

export const colorGroups: Group[] = [
  "Surfaces",
  "Text",
  "Accent",
  "Signal",
  "Danger",
  "Success",
  "Brand",
  "Outcome kinds",
  "Departments",
];

export const catalog: Record<string, TokenInfo> = {
  bg: { group: "Surfaces", note: "Page background behind every panel.", utility: "bg-bg" },
  surface: { group: "Surfaces", note: "Panels, cards, inputs and default buttons.", utility: "bg-surface" },
  "surface-2": {
    group: "Surfaces",
    note: "Recessed areas: notices, empty states, the selected segment.",
    utility: "bg-surface-2",
  },
  hover: { group: "Surfaces", note: "Hovered rows and quiet controls.", utility: "bg-hover" },
  border: { group: "Surfaces", note: "Hairlines between and around surfaces.", utility: "border-border" },
  "border-strong": {
    group: "Surfaces",
    note: "Button outlines and dashed empty states.",
    utility: "border-border-strong",
  },
  "border-control": {
    group: "Surfaces",
    note: "Form field outlines; at least 3:1 on every background.",
    utility: "border-border-control",
  },
  text: { group: "Text", note: "Headings and body copy.", utility: "text-text" },
  "text-2": { group: "Text", note: "Secondary copy, descriptions and metadata.", utility: "text-text-2" },
  "text-3": { group: "Text", note: "Tertiary labels; still 4.5:1 on every surface.", utility: "text-text-3" },
  accent: { group: "Accent", note: "Primary actions, links, focus rings, eyebrows.", utility: "bg-accent" },
  "accent-hover": { group: "Accent", note: "Primary action on hover.", utility: "bg-accent-hover" },
  "accent-fg": { group: "Accent", note: "Text on an accent fill.", utility: "text-accent-fg" },
  "accent-soft": {
    group: "Accent",
    note: "Tinted fill: badges and hovered default buttons.",
    utility: "bg-accent-soft",
  },
  signal: {
    group: "Signal",
    note: "The logo's orange, for attention that is not an error.",
    utility: "text-signal",
  },
  "signal-soft": { group: "Signal", note: "Tinted fill behind signal content.", utility: "bg-signal-soft" },
  danger: { group: "Danger", note: "Errors and destructive actions.", utility: "bg-danger" },
  "danger-hover": { group: "Danger", note: "Destructive action on hover.", utility: "bg-danger-hover" },
  "danger-fg": { group: "Danger", note: "Text on a danger fill.", utility: "text-danger-fg" },
  "danger-soft": { group: "Danger", note: "Error notice background.", utility: "bg-danger-soft" },
  success: { group: "Success", note: "Completed and healthy states.", utility: "text-success" },
  "success-soft": { group: "Success", note: "Tinted fill behind success text.", utility: "bg-success-soft" },
  navy: { group: "Brand", note: "The logo's navy, for brand marks.", utility: "text-navy" },
  "k-action": { group: "Outcome kinds", note: "Action outcomes.", utility: "border-k-action" },
  "k-decision": { group: "Outcome kinds", note: "Decision outcomes.", utility: "border-k-decision" },
  "k-blocker": { group: "Outcome kinds", note: "Blocker outcomes.", utility: "border-k-blocker" },
  "k-follow": { group: "Outcome kinds", note: "Follow-up outcomes.", utility: "border-k-follow" },
  "k-risk": { group: "Outcome kinds", note: "Risk outcomes.", utility: "border-k-risk" },
  "dept-engineering": {
    group: "Departments",
    note: "Engineering workspace tint.",
    utility: "bg-dept-engineering",
  },
  "dept-hr": { group: "Departments", note: "People Operations workspace tint.", utility: "bg-dept-hr" },
  "dept-finance": { group: "Departments", note: "Finance workspace tint.", utility: "bg-dept-finance" },
  dept: {
    group: "Departments",
    note: "The active department's tint, set by html[data-department].",
    utility: "bg-dept",
  },
  overlay: { group: "Effects", note: "Scrim behind dialogs and drawers.", utility: "bg-overlay" },
  "shadow-sm": { group: "Effects", note: "Resting panels.", utility: "shadow-sm" },
  "shadow-md": { group: "Effects", note: "Raised cards and menus.", utility: "shadow-md" },
  "shadow-lg": { group: "Effects", note: "Dialogs and popovers.", utility: "shadow-lg" },
  font: { group: "Fonts", note: "Geist, for all interface text.", utility: "font-sans" },
  mono: { group: "Fonts", note: "Geist Mono, for identifiers and payloads.", utility: "font-mono" },
  "r-sm": { group: "Radius", note: "Buttons, inputs, notices.", utility: "rounded-sm" },
  "r-md": { group: "Radius", note: "Panels and outcome cards.", utility: "rounded-md" },
  "r-lg": { group: "Radius", note: "Badges and calendar cards.", utility: "rounded-lg" },
  "ease-out": { group: "Curves", note: "Default for anything arriving or answering.", utility: "ease-out" },
  "ease-in-out": { group: "Curves", note: "Cross-fades, such as the theme change.", utility: "ease-in-out" },
  "ease-press": {
    group: "Curves",
    note: "Slight overshoot as a pressed button returns.",
    utility: "ease-press",
  },
  "ease-emphasized": {
    group: "Curves",
    note: "Larger moves that should feel deliberate.",
    utility: "ease-emphasized",
  },
  "dur-1": { group: "Durations", note: "Colour and opacity on hover and focus." },
  "dur-2": { group: "Durations", note: "Shadows, press, expanding content's fade." },
  "dur-3": { group: "Durations", note: "Cards settling, sections opening, theme cross-fade." },
  "dur-reveal": { group: "Durations", note: "A screen's content arriving (.reveal, .reveal-seq)." },
  "dur-4": { group: "Durations", note: "Reserved for the signature moment (transcript to outcome)." },
  "stagger-section": { group: "Sequencing", note: "Delay between sections in a .reveal-seq group." },
  "stagger-item": { group: "Sequencing", note: "Delay between items in a .stagger list." },
  i: {
    group: "Sequencing",
    note: "An element's position in a group; set with stagger() from motion.ts past the sixth.",
  },
  ink: { group: "Deprecated aliases", note: "Older name in the hand-written CSS.", replacement: "text" },
  muted: { group: "Deprecated aliases", note: "Older name in the hand-written CSS.", replacement: "text-2" },
  line: { group: "Deprecated aliases", note: "Older name in the hand-written CSS.", replacement: "border" },
  green: { group: "Deprecated aliases", note: "Older name in the hand-written CSS.", replacement: "accent" },
  soft: {
    group: "Deprecated aliases",
    note: "Older name in the hand-written CSS.",
    replacement: "accent-soft",
  },
  white: { group: "Deprecated aliases", note: "Older name in the hand-written CSS.", replacement: "surface" },
};

/** Token names in one group, in catalog order. */
export function tokensIn(group: Group) {
  return Object.keys(catalog).filter((name) => catalog[name].group === group);
}
