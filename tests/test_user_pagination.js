const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = readFileSync(join(__dirname, "..", "static", "app.js"), "utf8");

function openPage(url, storage, linkUrl) {
  const handlers = {};
  const scrolls = [];
  const link = {
    href: linkUrl,
    target: "",
    hasAttribute: () => false,
    addEventListener: (type, handler) => { handlers[`link:${type}`] = handler; },
  };
  const window = {
    location: { href: url },
    scrollX: 0,
    scrollY: 0,
    scrollTo: (x, y) => scrolls.push([x, y]),
    addEventListener: (type, handler) => { handlers[`window:${type}`] = handler; },
  };
  const document = {
    addEventListener: () => {},
    querySelector: () => null,
    querySelectorAll: (selector) =>
      selector === "[data-user-pagination] .pagination a" && linkUrl ? [link] : [],
  };
  const sessionStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  };
  vm.runInNewContext(script, {
    document, window, sessionStorage, localStorage: { removeItem: () => {} }, console,
  });
  return { handlers, window, scrolls };
}

test("user pagination restores the original position once on its destination", () => {
  const storage = new Map();
  const firstUrl = "https://example.test/explore?type=users";
  const secondUrl = "https://example.test/explore?type=users&user_page=2";
  const first = openPage(firstUrl, storage, secondUrl);
  first.window.scrollX = 12;
  first.window.scrollY = 500;
  first.handlers["link:click"]({ button: 0 });

  const second = openPage(secondUrl, storage, firstUrl);
  second.handlers["window:pageshow"]();
  assert.deepEqual(second.scrolls, [[12, 500]]);
  second.handlers["window:pageshow"]();
  assert.equal(second.scrolls.length, 1);
});

test("modified clicks and unrelated destinations do not restore a position", () => {
  const storage = new Map();
  const first = openPage("https://example.test/explore", storage, "https://example.test/explore?user_page=2");
  first.handlers["link:click"]({ button: 0, ctrlKey: true });
  assert.equal(storage.size, 0);

  first.handlers["link:click"]({ button: 0 });
  const other = openPage("https://example.test/explore?user_page=3", storage);
  other.handlers["window:pageshow"]();
  assert.deepEqual(other.scrolls, []);
  assert.equal(storage.size, 0);
});
