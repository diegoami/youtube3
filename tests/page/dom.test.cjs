// How page.js turns data into elements, against a stub document that refuses
// every way of parsing markup. Found missing by the v2.2.0 review (#35).
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const SOURCE = path.join(__dirname, "../../youtube3/page_assets/page.js");
const HOSTILE = '</script><img src=x onerror="alert(1)"><svg onload=alert(2)>';

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
}

globalThis.document = {
  created: [],
  createElement(tag) {
    const node = new StubNode(tag);
    this.created.push(node);
    return node;
  },
  write() {
    throw new Error("document.write was called");
  },
};

const { card, element } = require(SOURCE);

function video(fields = {}) {
  return {
    video_id: "abc",
    title: "A title",
    channel_id: "UC1",
    channel_title: "Channel One",
    liked_at: "2026-09-01T10:00:00Z",
    published_at: "2020-01-01T00:00:00Z",
    thumbnail: "https://i.ytimg.com/vi/abc/hqdefault.jpg",
    available: true,
    ...fields,
  };
}

function all(node) {
  return [node, ...node.children.flatMap(all)];
}

test("element sets text as text", () => {
  const node = element("p", { class: "x" }, HOSTILE);
  assert.equal(node.textContent, HOSTILE);
  assert.deepEqual(node.attributes, { class: "x" });
});

test("a hostile title and channel stay text, and no element comes from them", () => {
  document.created.length = 0;
  const article = card(video({ title: HOSTILE, channel_title: HOSTILE }));
  const nodes = all(article);
  assert.deepEqual(new Set(nodes.map((n) => n.tag)), new Set(["article", "a", "img", "div", "p"]));
  assert.equal(nodes.filter((n) => n.tag === "img").length, 1);
  assert.ok(nodes.some((n) => n.textContent === HOSTILE && n.attributes.class === "title"));
  assert.ok(nodes.some((n) => n.textContent === HOSTILE && n.attributes.class === "channel"));
});

test("ids are encoded into the links", () => {
  const nodes = all(card(video({ video_id: 'x"><script>', channel_id: "U/../C" })));
  const hrefs = nodes.map((n) => n.attributes.href).filter(Boolean);
  assert.ok(hrefs.includes("https://www.youtube.com/watch?v=x%22%3E%3Cscript%3E"));
  assert.ok(hrefs.includes("https://www.youtube.com/channel/U%2F..%2FC"));
});

for (const thumbnail of ["javascript:alert(1)", "https://example.com/i.png", "http://i.ytimg.com/x.jpg", null]) {
  test(`a thumbnail that is not on i.ytimg.com over https is not loaded: ${thumbnail}`, () => {
    const nodes = all(card(video({ thumbnail })));
    assert.equal(nodes.filter((n) => n.tag === "img").length, 0);
  });
}

test("the page's code never parses markup", () => {
  const code = fs
    .readFileSync(SOURCE, "utf8")
    .split("\n")
    .filter((line) => !line.trim().startsWith("//"))
    .join("\n");
  for (const banned of ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"]) {
    assert.ok(!code.includes(banned), `page.js uses ${banned}`);
  }
});
