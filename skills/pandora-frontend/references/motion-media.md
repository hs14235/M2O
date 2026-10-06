# Motion, original graphics and packaged media

## Smallest useful mechanism

Use CSS for modest state transitions, original SVG for scalable relational artwork, and clips when video improves the requested experience. Add WebGL/timeline libraries only for a requirement the existing stack cannot reasonably meet.

Keep essential controls/evidence stationary enough to use. Prefer bounded transforms/opacity to continuous layout work. Decoration must not delay navigation, save, retry or approval.

## Motion states

Automatic sequences need a static presentation and applicable pause behavior. Check system reduced motion, user calm mode, intentional pause across scene remounts, offscreen/background pause, data-saver opt-in, rejected autoplay/decode failure and resetting a failed scene when another is chosen.

No motion triggers writes. Finite celebration follows a corresponding acknowledged save/state. Hover, tentative date selection or queue acceptance is not completion.

## Loading and layout

Reserve dimensions before loading. Use a real poster and suitable preload/source attachment. Optimize actual dimensions, codec and bytes; a tiny file does not establish quality.

Inspect playback/loop endpoints in a browser and measure cost when performance matters. Encoder success/build size is not proof of seamlessness, low CPU or Core Web Vitals.

Stable filenames need revalidation; immutable caching suits content-hashed names. Missing media should return an error rather than successful app HTML.

## Layers and overlays

Keep native actionable HTML over decorative SVG with clear focus/hit targets. `aria-hidden` is for decoration, not information lacking a textual equivalent.

Fixed elements inside transformed/animated ancestors can become positioned relative to that ancestor and cover work. Reserve a rail, reflow or select an appropriate containing block; verify breakpoint boundaries and expanded panels.

Hover disclosure must be dismissible, hoverable, persistent as appropriate, and touch/keyboard usable. Use ordinary navigation semantics unless the widget really implements a menu pattern.

## Packaging

A native build can copy `public/` while Docker omits it. Inspect build context/ignore/copy rules, static root, MIME, cache and fallback routing.

Use the read-only asset checker for served bytes/hash/type/missing-file behavior, then verify playback under actual CSP. Do not weaken CSP to make decoration work.

Sources: [pause/stop/hide](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html), [hover/focus](https://www.w3.org/WAI/WCAG22/Understanding/content-on-hover-or-focus.html), [video loading](https://web.dev/articles/lazy-loading-video), [reduced motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion).
