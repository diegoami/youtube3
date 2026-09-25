"use strict";

// The history page. It runs after page.js, whose helpers (element, fold,
// matchesQuery, day) it shares; in Node, tests/page loads them with require.
const shared = typeof module !== "undefined" && module.exports ? require("./page.js") : globalThis;

// How many entries are drawn at a time: a history can hold tens of thousands.
const PAGE_SIZE = 200;

const MANAGE_LINKS = [
  ["YouTube history: search, pause or clear it", "https://www.youtube.com/feed/history"],
  ["My Activity: delete by date or one by one", "https://myactivity.google.com/product/youtube"],
  ["History settings: pause, auto-delete after 3, 18 or 36 months", "https://myactivity.google.com/activitycontrols/youtube"],
  ["Google Takeout: export the history again", "https://takeout.google.com/settings/takeout/custom/youtube"],
];

/** YYYY-MM-DD of an instant, in a time zone (the viewer's when not given). */
function dayKey(iso, timeZone) {
  if (!iso) return "";
  const options = { timeZone, year: "numeric", month: "2-digit", day: "2-digit" };
  return new Intl.DateTimeFormat("en-CA", options).format(new Date(iso));
}

/** How many times each video id was watched. */
function viewCounts(entries) {
  const counts = new Map();
  for (const entry of entries) {
    if (entry.video_id) counts.set(entry.video_id, (counts.get(entry.video_id) || 0) + 1);
  }
  return counts;
}

/**
 * The entries to show, newest first as given.
 * state: {query, channel, from, to (YYYY-MM-DD, inclusive), rewatchedOnly, showRemoved, timeZone}
 */
function selectEntries(entries, state, views) {
  return entries.filter((entry) => {
    if (entry.removed && !state.showRemoved) return false;
    if (state.channel && entry.channel_id !== state.channel) return false;
    if (state.rewatchedOnly && !((views.get(entry.video_id) || 0) > 1)) return false;
    if (state.from || state.to) {
      const key = dayKey(entry.watched_at, state.timeZone);
      if (state.from && key < state.from) return false;
      if (state.to && key > state.to) return false;
    }
    return shared.matchesQuery(entry, state.query || "");
  });
}

/** Consecutive entries grouped under the day they were watched. */
function groupByDay(entries, timeZone) {
  const groups = [];
  for (const entry of entries) {
    const key = dayKey(entry.watched_at, timeZone);
    if (!groups.length || groups[groups.length - 1].day !== key) groups.push({ day: key, entries: [] });
    groups[groups.length - 1].entries.push(entry);
  }
  return groups;
}

/** My Activity, searched for this video's title, where it can be deleted. */
function myActivityUrl(entry) {
  const base = "https://myactivity.google.com/product/youtube";
  return entry.removed || !entry.title ? base : `${base}?q=${encodeURIComponent(entry.title)}`;
}

function thumbnailUrl(videoId) {
  return `https://i.ytimg.com/vi/${encodeURIComponent(videoId)}/mqdefault.jpg`;
}

function timeOfDay(iso, timeZone) {
  if (!iso) return "";
  return new Intl.DateTimeFormat(undefined, { timeZone, hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
}

function link(text, href, className) {
  return shared.element("a", { class: className, href, target: "_blank", rel: "noopener" }, text);
}

function entryRow(entry, context) {
  const { element } = shared;
  const row = element("article", { class: entry.removed ? "entry removed" : "entry" });
  if (entry.video_id) {
    const watch = `https://www.youtube.com/watch?v=${encodeURIComponent(entry.video_id)}`;
    const thumb = element("a", { class: "thumb", href: watch, target: "_blank", rel: "noopener", tabindex: "-1" });
    const image = element("img", { src: thumbnailUrl(entry.video_id), alt: "", loading: "lazy", decoding: "async" });
    // A video deleted since has no thumbnail: show the empty frame, not a broken image.
    image.addEventListener("error", () => image.remove());
    thumb.append(image);
    row.append(thumb);
  } else {
    row.append(element("span", { class: "thumb" }));
  }
  const meta = element("div", { class: "meta" });
  if (entry.video_id) {
    const text = entry.title || (entry.removed ? "A video that is no longer available" : entry.video_id);
    meta.append(link(text, `https://www.youtube.com/watch?v=${encodeURIComponent(entry.video_id)}`, "title"));
  } else {
    meta.append(element("span", { class: "title" }, entry.title || "A video that has been removed"));
  }
  if (entry.channel_id) {
    meta.append(link(entry.channel_title || "", `https://www.youtube.com/channel/${encodeURIComponent(entry.channel_id)}`, "channel"));
  }
  const facts = element("p", { class: "facts" });
  facts.append(element("span", {}, timeOfDay(entry.watched_at, context.timeZone)));
  const views = context.views.get(entry.video_id) || 0;
  if (views > 1) facts.append(element("span", { class: "badge" }, `watched ${views} times`));
  if (entry.video_id && context.liked.has(entry.video_id)) facts.append(element("span", { class: "badge liked" }, "liked"));
  if (entry.removed) facts.append(element("span", { class: "badge" }, "removed"));
  facts.append(link("Find in My Activity", myActivityUrl(entry), "activity"));
  meta.append(facts);
  row.append(meta);
  return row;
}

// Not "init": page.js has one, and both run in the same page.
function initHistory() {
  const { element, channelCounts, day } = shared;
  const data = JSON.parse(document.getElementById("history-data").textContent);
  const entries = data.videos;
  const views = viewCounts(entries);
  const context = { views, liked: new Set(data.liked || []), timeZone: undefined };
  const controls = {
    query: document.getElementById("query"),
    channel: document.getElementById("channel"),
    from: document.getElementById("from"),
    to: document.getElementById("to"),
    rewatchedOnly: document.getElementById("rewatched"),
    showRemoved: document.getElementById("show-removed"),
  };
  const list = document.getElementById("list");
  const status = document.getElementById("status");
  const empty = document.getElementById("empty");
  const more = document.getElementById("more");
  let limit = PAGE_SIZE;
  let shown = [];

  const summary = data.summary || {};
  document.getElementById("span").textContent = `${day(summary.first)} to ${day(summary.last)}`;
  for (const channel of channelCounts(entries).slice(0, 300)) {
    controls.channel.append(element("option", { value: channel.id }, `${channel.title} (${channel.count})`));
  }
  const manage = document.getElementById("manage-links");
  for (const [text, href] of MANAGE_LINKS) {
    const item = element("li");
    item.append(link(text, href, ""));
    manage.append(item);
  }
  const nav = document.getElementById("links");
  for (const [text, href] of data.links || []) {
    if (/^[\w.-]+\.html$/.test(href)) nav.append(element("a", { href }, text));
  }

  function draw() {
    const groups = groupByDay(shown.slice(0, limit), context.timeZone);
    list.replaceChildren(
      ...groups.map((group) => {
        const section = element("section", { class: "day" });
        section.append(element("h2", {}, group.day));
        section.append(...group.entries.map((entry) => entryRow(entry, context)));
        return section;
      }),
    );
    status.textContent = `${shown.length} of ${entries.length} watches`;
    empty.hidden = shown.length > 0;
    more.hidden = shown.length <= limit;
    more.textContent = `Show ${Math.max(0, Math.min(PAGE_SIZE, shown.length - limit))} more`;
  }

  function filter() {
    shown = selectEntries(
      entries,
      {
        query: controls.query.value,
        channel: controls.channel.value,
        from: controls.from.value,
        to: controls.to.value,
        rewatchedOnly: controls.rewatchedOnly.checked,
        showRemoved: controls.showRemoved.checked,
        timeZone: context.timeZone,
      },
      views,
    );
    limit = PAGE_SIZE;
    draw();
  }

  for (const control of Object.values(controls)) {
    control.addEventListener(control.type === "search" ? "input" : "change", filter);
  }
  more.addEventListener("click", () => {
    limit += PAGE_SIZE;
    draw();
  });
  filter();
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { PAGE_SIZE, MANAGE_LINKS, dayKey, viewCounts, selectEntries, groupByDay, myActivityUrl, thumbnailUrl, entryRow };
} else {
  document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("history-data")) initHistory();
  });
}
