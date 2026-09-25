"use strict";

// The pure functions come first: tests/page runs them in Node.

const SORTS = {
  "liked-desc": byDate("liked_at", -1),
  "liked-asc": byDate("liked_at", 1),
  "published-desc": byDate("published_at", -1),
  "published-asc": byDate("published_at", 1),
  title: (a, b) => displayed(a.title).localeCompare(displayed(b.title), undefined, { sensitivity: "base" }),
};

// Text as the browser shows it: runs of white space collapse to one space.
function displayed(text) {
  return (text || "").replace(/\s+/g, " ").trim();
}

// ISO dates compare as strings; missing dates sort last whichever the direction.
function byDate(field, direction) {
  return (a, b) => {
    const first = a[field];
    const second = b[field];
    if (!first && !second) return 0;
    if (!first) return 1;
    if (!second) return -1;
    return direction * (first < second ? -1 : first > second ? 1 : 0);
  };
}

// Case- and accent-insensitive text for searching.
function fold(text) {
  return (text || "").normalize("NFD").replace(/\p{Diacritic}/gu, "").toLocaleLowerCase();
}

function matchesQuery(video, query) {
  const words = fold(query).split(/\s+/).filter(Boolean);
  const haystack = fold(`${video.title} ${video.channel_title || ""}`);
  return words.every((word) => haystack.includes(word));
}

/**
 * The videos to show, in order.
 * state: {query, channel (a channel id, "" for all), sort (a key of SORTS), showUnavailable}
 */
function selectVideos(videos, state) {
  const sort = SORTS[state.sort] || SORTS["liked-desc"];
  return videos
    .filter((video) => state.showUnavailable || video.available)
    .filter((video) => !state.channel || video.channel_id === state.channel)
    .filter((video) => matchesQuery(video, state.query || ""))
    .sort(sort); // filter() made a new array: the data keeps its order
}

/** Each channel with its number of likes, most liked first, then by title. */
function channelCounts(videos) {
  const counts = new Map();
  for (const video of videos) {
    if (!video.channel_id) continue;
    const entry = counts.get(video.channel_id) || { id: video.channel_id, title: video.channel_title, count: 0 };
    entry.count += 1;
    counts.set(video.channel_id, entry);
  }
  return [...counts.values()].sort(
    (a, b) => b.count - a.count || (a.title || "").localeCompare(b.title || "", undefined, { sensitivity: "base" }),
  );
}

function day(iso) {
  return iso ? iso.slice(0, 10) : "";
}

// The page: every element is built with textContent and attributes, never innerHTML.

function element(tag, attributes = {}, text = null) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
  if (text !== null) node.textContent = text;
  return node;
}

// Thumbnails come from YouTube's image host only, whatever the data says.
const THUMBNAIL_HOST = "https://i.ytimg.com/";

function card(video) {
  const article = element("article", { class: video.available ? "card" : "card unavailable" });
  const watch = `https://www.youtube.com/watch?v=${encodeURIComponent(video.video_id)}`;
  const thumb = element("a", { class: "thumb", href: watch, target: "_blank", rel: "noopener", tabindex: "-1" });
  if (typeof video.thumbnail === "string" && video.thumbnail.startsWith(THUMBNAIL_HOST)) {
    thumb.append(element("img", { src: video.thumbnail, alt: "", loading: "lazy", decoding: "async" }));
  }
  article.append(thumb);
  const meta = element("div", { class: "meta" });
  meta.append(element("a", { class: "title", href: watch, target: "_blank", rel: "noopener" }, video.title || video.video_id));
  if (video.channel_id) {
    const channelUrl = `https://www.youtube.com/channel/${encodeURIComponent(video.channel_id)}`;
    meta.append(element("a", { class: "channel", href: channelUrl, target: "_blank", rel: "noopener" }, video.channel_title || ""));
  } else {
    meta.append(element("span", { class: "channel" }, video.title === "Deleted video" ? "Deleted" : "Unavailable"));
  }
  const dates = [`Liked ${day(video.liked_at)}`];
  if (video.published_at) dates.push(`published ${day(video.published_at)}`);
  meta.append(element("p", { class: "dates" }, dates.join(" · ")));
  article.append(meta);
  return article;
}

function init() {
  const data = JSON.parse(document.getElementById("likes-data").textContent);
  const videos = data.videos;
  const controls = {
    query: document.getElementById("query"),
    channel: document.getElementById("channel"),
    sort: document.getElementById("sort"),
    showUnavailable: document.getElementById("show-unavailable"),
  };
  const grid = document.getElementById("grid");
  const status = document.getElementById("status");
  const empty = document.getElementById("empty");
  const unavailable = videos.filter((video) => !video.available).length;

  document.getElementById("exported").textContent = `Exported ${day(data.exported_at)}`;
  document.getElementById("unavailable-count").textContent = `(${unavailable})`;
  for (const channel of channelCounts(videos)) {
    controls.channel.append(element("option", { value: channel.id }, `${channel.title} (${channel.count})`));
  }
  // Links to the other pages: only a sibling file, never another origin.
  const nav = document.getElementById("links");
  for (const [text, href] of data.links || []) {
    if (/^[\w.-]+\.html$/.test(href)) nav.append(element("a", { href }, text));
  }

  function render() {
    const shown = selectVideos(videos, {
      query: controls.query.value,
      channel: controls.channel.value,
      sort: controls.sort.value,
      showUnavailable: controls.showUnavailable.checked,
    });
    grid.replaceChildren(...shown.map(card));
    status.textContent = `${shown.length} of ${videos.length} liked videos`;
    empty.hidden = shown.length > 0;
  }

  for (const control of Object.values(controls)) {
    control.addEventListener(control.type === "search" ? "input" : "change", render);
  }
  render();
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { SORTS, byDate, displayed, fold, matchesQuery, selectVideos, channelCounts, day, element, card };
} else {
  document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("likes-data")) init();
  });
}
