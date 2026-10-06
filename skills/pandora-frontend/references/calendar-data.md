# Celestial calendars and graphical data views

## Which dates mean what?

Identify the domain source before placing anything on a day. Reviewed deadline, meeting occurrence, record creation, observed provider timestamp and personal scheduled day are different facts.

Do not convert Monday/Friday hints without explicit review rules. Keep an undated cluster, literal hints, and a route to review. Missing dates are useful information, not gaps to decorate away.

Show the requested approved kinds/current revision rather than silently limiting a view to personal actions. Visibility and aggregate counts must respect restricted records. Display confirmed names only when the contract supports confirmation; otherwise retain honest unassigned state.

## Date-only values

Treat ISO date-only values as calendar days. `new Date("YYYY-MM-DD")` interprets UTC midnight and can display the previous day in western timezones.

For local labels, split year/month/day and construct a local date at noon. Use calendar arithmetic or UTC day ordinals for ranges rather than fixed 24-hour local increments across daylight-saving changes. Respect actual API range/pagination limits.

Do not invent clock times for date-only outcomes. Explain the governing timezone for timestamped events when relevant.

## Constellation grammar

Use chronological date groups, original crescent geometry, restrained glow and connecting arcs as decoration, with native buttons/cards as interaction. Connectors must not imply unsupported causality or astronomical prediction.

Group crowded days and bound/paginate details. Make partial date windows/truncated feeds explicit. Keep an agenda with actual dates, names, kinds and source/version context. Personal execution can appear separately without completing/reopening shared/provider work.

## Keyboard and touch

Use native controls/selection state. If using an ARIA date grid, implement its full keyboard/focus pattern; do not apply `grid` to a freeform star field just because it resembles a calendar. A chronological button/list is often better.

Editing dates needs explicit save/current versions. Selecting a date point is navigation, not save. Support touch without hover and calm mode without animation.

[W3C's date-picker example](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/examples/datepicker-dialog/) provides applicable patterns, not production code or a compliance certificate; relevant browser/assistive-technology testing remains necessary.

## Meaningful cases

- all requested kinds, current approval and old-revision exclusion;
- restricted/foreign scope denial and correct aggregate counts;
- literal undated hints, explicit placement and timezone boundaries;
- personal planned day differing from shared deadline;
- confirmed/suggested/unassigned owner;
- pagination, empty/error response and late scope results;
- keyboard/touch/agenda operation and crowded-day reflow.
