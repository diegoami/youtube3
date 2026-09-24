// The history page's logic and its DOM building, run with: node --test "tests/page/*.test.cjs"
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const HOSTILE = '</script><img src=x onerror="alert(1)">';

// The same refusing stub document as dom.test.cjs.
class StubNode {
  constructor(tag) {
    this.tag = tag;
    this.attributes = {};
    this.children = [];
    this.text = null;
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
  append(...nodes) {
    this.children.push(...nodes);
  }
  set textContent(value) {
    this.text = value;
  }
  get textContent() {
    return this.text;
  }
  set innerHTML(value) {
    throw new Error(`innerHTML was assigned: ${value}`);
  }
  set outerHTML(value) {
    throw new Error(`outerHTML was assigned: ${value}`);
  }
  insertAdjacentHTML() {
    throw new Error("insertAdjacentHTML was called");
  }
  addEventListener(type, listener) {
    this.listeners = { ...this.listeners, [type]: listener };
  }
  remove() {
    this.removed = true;
  }
}
globalThis.document = { createElement: (tag) => new StubNode(tag) };

const SOURCE = path.join(__dirname, "../../youtube3/page_assets/history.js");
const h = require(SOURCE);

function watch(id, watchedAt, fields = {}) {
  return {
    video_id: id,
    title: `title ${id}`,
    channel_id: "UC1",
    channel_title: "Channel One",
    watched_at: watchedAt,
    removed: false,
    ...fields,
  };
}

// Newest first, as history.json stores them.
const ENTRIES = [
  watch("a", "2026-09-21T22:30:00Z"), // 2026-09-22 in Berlin, 2026-09-21 in UTC
  watch("b", "2026-09-21T10:00:00Z", { channel_id: "UC2", channel_title: "Déjà Vu Channel" }),
  watch("a", "2026-09-20T08:00:00Z"),
  watch(null, "2026-09-19T08:00:00Z", { title: "A video that has been removed", channel_id: null, channel_title: null, removed: true }),
  watch("c", "2026-09-01T00:00:00Z"),
];
const VIEWS = h.viewCounts(ENTRIES);
const ALL = { query: "", channel: "", from: "", to: "", rewatchedOnly: false, showRemoved: false, timeZone: "UTC" };
const ids = (entries) => entries.map((e) => e.video_id);

test("days follow the time zone", () => {
  assert.equal(h.dayKey("2026-09-21T22:30:00Z", "UTC"), "2026-09-21");
  assert.equal(h.dayKey("2026-09-21T22:30:00Z", "Europe/Berlin"), "2026-09-22");
  assert.equal(h.dayKey(null, "UTC"), "");
});

test("views are counted per video", () => {
  assert.equal(VIEWS.get("a"), 2);
  assert.equal(VIEWS.get("b"), 1);
  assert.equal(VIEWS.has(null), false);
});

test("removed videos are hidden unless asked for", () => {
  assert.deepEqual(ids(h.selectEntries(ENTRIES, ALL, VIEWS)), ["a", "b", "a", "c"]);
  assert.deepEqual(ids(h.selectEntries(ENTRIES, { ...ALL, showRemoved: true }, VIEWS)), ["a", "b", "a", null, "c"]);
});

test("search, channel and rewatched filters", () => {
  assert.deepEqual(ids(h.selectEntries(ENTRIES, { ...ALL, query: "deja vu" }, VIEWS)), ["b"]);
  assert.deepEqual(ids(h.selectEntries(ENTRIES, { ...ALL, channel: "UC2" }, VIEWS)), ["b"]);
  assert.deepEqual(ids(h.selectEntries(ENTRIES, { ...ALL, rewatchedOnly: true }, VIEWS)), ["a", "a"]);
});

test("a date range includes both ends, in the page's time zone", () => {
  const range = { ...ALL, from: "2026-09-20", to: "2026-09-21" };
  assert.deepEqual(ids(h.selectEntries(ENTRIES, range, VIEWS)), ["a", "b", "a"]);
  assert.deepEqual(ids(h.selectEntries(ENTRIES, { ...range, timeZone: "Europe/Berlin" }, VIEWS)), ["b", "a"]);
  assert.deepEqual(ids(h.selectEntries(ENTRIES, { ...ALL, from: "2026-09-21" }, VIEWS)), ["a", "b"]);
  assert.deepEqual(ids(h.selectEntries(ENTRIES, { ...ALL, to: "2026-09-01" }, VIEWS)), ["c"]);
});

test("entries are grouped by day, in order", () => {
  const groups = h.groupByDay(ENTRIES, "UTC");
  assert.deepEqual(
    groups.map((g) => [g.day, ids(g.entries)]),
    [
      ["2026-09-21", ["a", "b"]],
      ["2026-09-20", ["a"]],
      ["2026-09-19", [null]],
      ["2026-09-01", ["c"]],
    ],
  );
});

test("My Activity is searched for the title, encoded", () => {
  assert.equal(
    h.myActivityUrl(watch("x", "2026-09-01T00:00:00Z", { title: "Rock & Roll #1?" })),
    "https://myactivity.google.com/product/youtube?q=Rock%20%26%20Roll%20%231%3F",
  );
  assert.equal(h.myActivityUrl(ENTRIES[3]), "https://myactivity.google.com/product/youtube");
});

test("thumbnails come from i.ytimg.com, the id encoded", () => {
  assert.equal(h.thumbnailUrl("a/../b"), "https://i.ytimg.com/vi/a%2F..%2Fb/mqdefault.jpg");
});

test("every management link goes to Google over https", () => {
  for (const [, href] of h.MANAGE_LINKS) {
    assert.match(href, /^https:\/\/(www\.youtube\.com|myactivity\.google\.com|takeout\.google\.com)\//);
  }
});

function all(node) {
  return [node, ...node.children.flatMap(all)];
}

test("a hostile entry stays text, with every link where it belongs", () => {
  const context = { views: VIEWS, liked: new Set(["a"]), timeZone: "UTC" };
  const nodes = all(h.entryRow(watch("a", "2026-09-21T10:00:00Z", { title: HOSTILE, channel_title: HOSTILE }), context));
  assert.ok(nodes.some((n) => n.attributes.class === "title" && n.textContent === HOSTILE));
  assert.ok(nodes.some((n) => n.attributes.class === "channel" && n.textContent === HOSTILE));
  assert.ok(nodes.some((n) => n.textContent === "watched 2 times"));
  assert.ok(nodes.some((n) => n.textContent === "liked"));
  const hrefs = nodes.map((n) => n.attributes.href).filter(Boolean);
  assert.ok(hrefs.includes("https://www.youtube.com/watch?v=a"));
  assert.ok(hrefs.includes("https://www.youtube.com/channel/UC1"));
  assert.ok(hrefs.some((href) => href.startsWith("https://myactivity.google.com/product/youtube?q=")));
  assert.deepEqual(new Set(nodes.map((n) => n.tag)), new Set(["article", "a", "img", "div", "p", "span"]));
});

test("a removed video has no link to watch it, but one to My Activity", () => {
  const nodes = all(h.entryRow(ENTRIES[3], { views: VIEWS, liked: new Set(), timeZone: "UTC" }));
  const hrefs = nodes.map((n) => n.attributes.href).filter(Boolean);
  assert.deepEqual(hrefs, ["https://myactivity.google.com/product/youtube"]);
  assert.ok(nodes.some((n) => n.textContent === "removed"));
});

test("the history page's code never parses markup", () => {
  const code = fs
    .readFileSync(SOURCE, "utf8")
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
  for (const banned of ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"]) {
    assert.ok(!code.includes(banned), `history.js uses ${banned}`);
  }
});

test("a hostile video id is encoded into every link", () => {
  const nodes = all(h.entryRow(watch('x"><s', "2026-09-21T10:00:00Z"), { views: VIEWS, liked: new Set(), timeZone: "UTC" }));
  const hrefs = nodes.map((n) => n.attributes.href || n.attributes.src).filter(Boolean);
  assert.ok(hrefs.includes("https://www.youtube.com/watch?v=x%22%3E%3Cs"));
  assert.ok(hrefs.every((href) => !href.includes('"')));
});

test("a thumbnail that fails to load is removed, not shown broken", () => {
  const nodes = all(h.entryRow(watch("gone", "2026-09-21T10:00:00Z"), { views: VIEWS, liked: new Set(), timeZone: "UTC" }));
  const [image] = nodes.filter((n) => n.tag === "img");
  image.listeners.error();
  assert.equal(image.removed, true);
});
