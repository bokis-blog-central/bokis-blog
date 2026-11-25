const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = readFileSync(join(__dirname, "..", "static", "app.js"), "utf8");
const initializer = script.slice(script.indexOf("function initializeHiddenBok()"),
  script.indexOf("function initializeLikeButtons()"));

function setup(response) {
  const primary = { hidden: false };
  const alternate = { hidden: true };
  const button = { disabled: false, textContent: "Show alternate hint" };
  const status = { textContent: "" };
  const choice = { value: "1" };
  let handler;
  let request;
  const form = {
    action: "/hidden-bok/hint",
    elements: { enabled: choice },
    querySelector: (selector) => selector === "button" ? button : status,
    addEventListener: (_, listener) => { handler = listener; },
  };
  const document = {
    querySelector: (selector) => ({
      "[data-hidden-hint-form]": form,
      "[data-primary-hint]": primary,
      "[data-alternate-hint]": alternate,
    })[selector] || null,
  };
  vm.runInNewContext(`${initializer}\ninitializeHiddenBok();`, {
    document, URLSearchParams, FormData: class {
      constructor() { return [["enabled", choice.value], ["version", "1"]]; }
    },
    fetch: async (url, options) => { request = { url, options }; return response; },
  });
  return { primary, alternate, button, status, choice, handler, request: () => request };
}

test("switching the hint updates the display after saving the choice", async () => {
  const page = setup({ ok: true, json: async () => ({ enabled: true }) });
  await page.handler({ preventDefault() {} });
  assert.equal(page.request().options.body.get("enabled"), "1");
  assert.equal(page.primary.hidden, true);
  assert.equal(page.alternate.hidden, false);
  assert.equal(page.choice.value, "0");
  assert.equal(page.button.textContent, "Show primary hint");
  assert.equal(page.button.disabled, false);
});

test("an unavailable hint leaves the display unchanged and reports the error", async () => {
  const page = setup({ ok: false, json: async () => ({ error: "Hint unavailable." }) });
  await page.handler({ preventDefault() {} });
  assert.equal(page.primary.hidden, false);
  assert.equal(page.alternate.hidden, true);
  assert.equal(page.choice.value, "1");
  assert.equal(page.status.textContent, "Hint unavailable.");
  assert.equal(page.button.disabled, false);
});
