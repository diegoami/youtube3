// The page's pure logic, run with: node --test tests/page
const test = require("node:test");
const assert = require("node:assert/strict");
const { selectVideos, channelCounts, fold, day } = require("../../youtube3/page_assets/page.js");

function video(id, fields = {}) {
  return {
    video_id: id,
    title: `title ${id}`,
    channel_id: "UC1",
    channel_title: "Channel One",
    liked_at: "2026-09-01T10:00:00Z",
    published_at: "2020-01-01T00:00:00Z",
    thumbnail: null,
    available: true,
    ...fields,
  };
}

const VIDEOS = [
  video("a", { title: "Анна Плетнёва - Зима", channel_id: "UC2", channel_title: "Anna", liked_at: "2026-09-05T00:00:00Z", published_at: "2019-01-01T00:00:00Z" }),
  video("b", { title: "Déjà Vu", liked_at: "2026-09-03T00:00:00Z", published_at: "2024-01-01T00:00:00Z" }),
  video("c", { title: "zebra song", liked_at: "2026-09-04T00:00:00Z", published_at: null }),
  video("gone", { title: "Deleted video", channel_id: null, channel_title: null, available: false, liked_at: "2026-09-06T00:00:00Z", published_at: null }),
];

const ALL = { query: "", channel: "", sort: "liked-desc", showUnavailable: false };
const ids = (videos) => videos.map((v) => v.video_id);

test("unavailable videos are hidden unless asked for", () => {
  assert.deepEqual(ids(selectVideos(VIDEOS, ALL)), ["a", "c", "b"]);
  assert.deepEqual(ids(selectVideos(VIDEOS, { ...ALL, showUnavailable: true })), ["gone", "a", "c", "b"]);
});

test("search ignores case and accents, in any script", () => {
  assert.deepEqual(ids(selectVideos(VIDEOS, { ...ALL, query: "DEJA vu" })), ["b"]);
  assert.deepEqual(ids(selectVideos(VIDEOS, { ...ALL, query: "плетнева" })), ["a"]);
});

test("search covers the channel and needs every word", () => {
  assert.deepEqual(ids(selectVideos(VIDEOS, { ...ALL, query: "anna" })), ["a"]);
  assert.deepEqual(ids(selectVideos(VIDEOS, { ...ALL, query: "channel zebra" })), ["c"]);
  assert.deepEqual(ids(selectVideos(VIDEOS, { ...ALL, query: "channel nothing" })), []);
});

test("the channel filter keeps one channel", () => {
  assert.deepEqual(ids(selectVideos(VIDEOS, { ...ALL, channel: "UC1" })), ["c", "b"]);
});

test("each sort orders as named, missing dates last", () => {
  const order = (sort) => ids(selectVideos(VIDEOS, { ...ALL, sort }));
  assert.deepEqual(order("liked-desc"), ["a", "c", "b"]);
  assert.deepEqual(order("liked-asc"), ["b", "c", "a"]);
  assert.deepEqual(order("published-desc"), ["b", "a", "c"]);
  assert.deepEqual(order("published-asc"), ["a", "b", "c"]);
  assert.deepEqual(order("title"), ["b", "c", "a"]);
});

test("an unknown sort falls back to newest liked", () => {
  assert.deepEqual(ids(selectVideos(VIDEOS, { ...ALL, sort: "nonsense" })), ["a", "c", "b"]);
});

test("selecting does not reorder the data it was given", () => {
  const before = ids(VIDEOS);
  selectVideos(VIDEOS, { ...ALL, sort: "title" });
  assert.deepEqual(ids(VIDEOS), before);
});

test("channels are counted, most liked first, without unavailable videos", () => {
  assert.deepEqual(channelCounts(VIDEOS), [
    { id: "UC1", title: "Channel One", count: 2 },
    { id: "UC2", title: "Anna", count: 1 },
  ]);
});

test("helpers", () => {
  assert.equal(fold("Ünïcödé"), "unicode");
  assert.equal(day("2026-09-01T10:00:00Z"), "2026-09-01");
  assert.equal(day(null), "");
});

test("titles sort as the browser shows them, with runs of spaces collapsed", () => {
  // Found on the owner's likes: "NiziU  『Make you happy』" has two spaces.
  const videos = [video("x", { title: "NiziU  『Make you happy』" }), video("y", { title: "NiziU 「Chopstick」" })];
  const shown = selectVideos(videos, { ...ALL, sort: "title" }).map((v) => v.title.replace(/\s+/g, " "));
  const inOrder = [...shown].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  assert.deepEqual(shown, inOrder);
});

test("videos without a date come last in both directions, wherever they start", () => {
  const videos = [video("undated", { published_at: null }), video("old", { published_at: "2001-01-01T00:00:00Z" }), video("new", { published_at: "2024-01-01T00:00:00Z" })];
  assert.deepEqual(ids(selectVideos(videos, { ...ALL, sort: "published-desc" })), ["new", "old", "undated"]);
  assert.deepEqual(ids(selectVideos(videos, { ...ALL, sort: "published-asc" })), ["old", "new", "undated"]);
});
