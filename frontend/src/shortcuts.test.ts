import { afterEach, describe, expect, it } from "vitest";
import { isApplePlatform, isTypingTarget, menuShortcutLabel, shortcutFor } from "./shortcuts";

afterEach(() => {
  document.body.innerHTML = "";
});

function press(target: Element, init: KeyboardEventInit) {
  let event!: KeyboardEvent;
  target.addEventListener("keydown", (e) => (event = e as KeyboardEvent), { once: true });
  target.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init }));
  return event;
}
function field(html: string) {
  document.body.innerHTML = html;
  return document.body.firstElementChild!;
}

describe("single-key shortcuts never fire while typing", () => {
  const targets = [
    "<input />",
    "<textarea></textarea>",
    "<select><option>One</option></select>",
    "<div contenteditable='true'>Notes</div>",
  ];
  for (const html of targets)
    it("ignores ? and / in " + html, () => {
      const element = field(html);
      expect(isTypingTarget(element)).toBe(true);
      expect(shortcutFor(press(element, { key: "?", shiftKey: true }), false)).toBeNull();
      expect(shortcutFor(press(element, { key: "/" }), false)).toBeNull();
    });

  it("fires ? and / outside fields", () => {
    const button = field("<button>Open</button>");
    expect(isTypingTarget(button)).toBe(false);
    expect(shortcutFor(press(button, { key: "?", shiftKey: true }), false)).toBe("help");
    expect(shortcutFor(press(button, { key: "/" }), false)).toBe("search");
  });

  it("ignores repeats, modifiers, composition and keys another handler used", () => {
    const body = document.body;
    expect(shortcutFor(press(body, { key: "/", repeat: true }), false)).toBeNull();
    expect(shortcutFor(press(body, { key: "/", ctrlKey: true }), false)).toBeNull();
    expect(shortcutFor(press(body, { key: "/", altKey: true }), false)).toBeNull();
    expect(shortcutFor(press(body, { key: "/", isComposing: true }), false)).toBeNull();
    const handled = new KeyboardEvent("keydown", { key: "/", cancelable: true });
    handled.preventDefault();
    expect(shortcutFor(handled, false)).toBeNull();
  });

  it("ignores single keys while a dialog is open", () => {
    field("<div role='dialog'><button>Inside</button></div>");
    expect(shortcutFor(press(document.querySelector("button")!, { key: "?" }), false)).toBeNull();
  });

  it("ignores single keys while a native modal dialog is open, and not once it closes", () => {
    // The menu and shortcut list stay in the page as closed <dialog> elements.
    field("<div><dialog open><button>Inside</button></dialog><button>Outside</button></div>");
    expect(shortcutFor(press(document.querySelectorAll("button")[1], { key: "?" }), false)).toBeNull();
    document.querySelector("dialog")!.removeAttribute("open");
    expect(shortcutFor(press(document.querySelectorAll("button")[1], { key: "?" }), false)).toBe("help");
  });

  it("fires again while a closed third-party dialog is still animating out", () => {
    field("<div><div role='dialog' data-state='closed'></div><button>Outside</button></div>");
    expect(shortcutFor(press(document.querySelector("button")!, { key: "?" }), false)).toBe("help");
  });
});

describe("the menu shortcut", () => {
  it("works everywhere, including in fields and contenteditable", () => {
    for (const html of ["<input />", "<textarea></textarea>", "<div contenteditable='true'></div>"]) {
      const element = field(html);
      expect(shortcutFor(press(element, { key: "k", ctrlKey: true }), false)).toBe("menu");
      expect(shortcutFor(press(element, { key: "k", metaKey: true }), true)).toBe("menu");
    }
  });

  it("uses ⌘K on Apple platforms and Ctrl+K elsewhere, never the other", () => {
    const body = document.body;
    expect(shortcutFor(press(body, { key: "K", metaKey: true }), true)).toBe("menu");
    expect(shortcutFor(press(body, { key: "k", ctrlKey: true }), true)).toBeNull();
    expect(shortcutFor(press(body, { key: "k", ctrlKey: true }), false)).toBe("menu");
    expect(shortcutFor(press(body, { key: "k", metaKey: true }), false)).toBeNull();
    expect(shortcutFor(press(body, { key: "k" }), false)).toBeNull();
    expect(shortcutFor(press(body, { key: "k", ctrlKey: true, shiftKey: true }), false)).toBeNull();
  });

  it("detects the platform and labels the shortcut to match", () => {
    expect(isApplePlatform({ platform: "MacIntel", userAgent: "" })).toBe(true);
    expect(isApplePlatform({ platform: "Win32", userAgent: "" })).toBe(false);
    expect(isApplePlatform({ platform: "", userAgent: "Mozilla/5.0 (iPhone)" })).toBe(true);
    expect(menuShortcutLabel(true)).toBe("⌘K");
    expect(menuShortcutLabel(false)).toBe("Ctrl K");
  });
});
