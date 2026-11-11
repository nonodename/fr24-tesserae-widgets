// fr24, Spectra stat archetype. The nearest tracked aircraft from a local
// Flightradar24 feeder: a bold airplane block, the callsign as the hero
// value, then an altitude chip and a last-heard chip. When adsbdb knows
// the aircraft and flight, the airline sits above the callsign, the
// manufacturer + type below it, and an origin → destination row above
// the chips. Each is left out when its lookup came back empty. An airline
// flight swaps the airplane glyph for the airline's logo.
//
//   xs      callsign + altitude, stacked and centred, no title or icon.
//   sm      adds the title, icon block, route codes and last-heard chip.
//   md, lg  add the airline, the aircraft type and the airport cities.
//
// The altitude band picks the colour role for the icon block and the
// altitude chip: low traffic is the "now" alert, mid is a warning,
// cruising traffic reads as "up".

const ALT_BANDS = [
  { below: 3000, accent: "--accent-1" },
  { below: 10000, accent: "--accent-2" },
  { below: Infinity, accent: "--accent-3" },
];

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function bandAccent(altFt) {
  return ALT_BANDS.find((b) => altFt < b.below).accent;
}

function fmtTime(epochS, locale) {
  if (!Number.isFinite(epochS) || epochS <= 0) return "--:--";
  return new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" })
    .format(new Date(epochS * 1000));
}

// The airline's own logo when the server found one (a brand colour is the
// documented exception to token-only colour, so the block goes neutral
// and lets the logo carry it); otherwise the airplane glyph in the
// altitude band's colours.
function heroBlock(ac) {
  if (typeof ac.logo === "string" && ac.logo.startsWith("data:image/svg+xml;")) {
    const alt = ac.route?.airline || "";
    return `<div class="fr-icon fr-icon--logo"><img src="${escapeHtml(ac.logo)}" alt="${escapeHtml(alt)}"></div>`;
  }
  return `<div class="fr-icon"><i class="ph-bold ph-airplane"></i></div>`;
}

function airport(a) {
  return `
    <span class="fr-ap" title="${escapeHtml(a.name)}">
      <b>${escapeHtml(a.code)}</b>
      ${a.city ? `<small>${escapeHtml(a.city)}</small>` : ""}
    </span>`;
}

function routeRow(route) {
  return `
    <div class="fr-route">
      ${airport(route.origin)}
      <i class="ph-bold ph-arrow-right"></i>
      ${airport(route.destination)}
    </div>`;
}

const LAYOUT = `
  .fr-body {
    flex-direction: row;
    align-items: center;
    justify-content: flex-start;
    gap: var(--space-5);
    min-height: 0;
  }
  .fr-icon {
    flex: 0 0 auto;
    display: grid;
    place-items: center;
    padding: 0.18em;
    font-size: clamp(2.6em, min(34cqh, 16cqw), 12em);
    line-height: 1;
    color: var(--band);
    background: var(--band-soft);
    border-radius: var(--pill-radius, var(--radius-0));
  }
  .fr-icon--logo { background: var(--surface-sunken); }
  .fr-icon--logo img { display: block; width: 1em; height: 1em; object-fit: contain; }
  .fr-lockup {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-3);
  }
  .fr-body .fr-call {
    display: block;
    max-width: 100%;
    font-size: clamp(1.6em, min(10cqw, 16cqh), 9em);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-primary);
  }
  .fr-airline,
  .fr-model {
    max-width: 100%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: clamp(0.85em, min(3.4cqw, 6cqh), 2.2em);
    font-weight: var(--fw-bold);
    color: var(--text-secondary);
  }
  .fr-airline {
    margin-bottom: calc(-1 * var(--space-2));
    letter-spacing: var(--ls-label);
    text-transform: var(--label-transform, uppercase);
    color: var(--text-muted);
  }
  .fr-model { margin-top: calc(-1 * var(--space-2)); }
  .fr-route {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    max-width: 100%;
    font-size: clamp(0.95em, min(4cqw, 7cqh), 3em);
  }
  .fr-ap {
    display: flex;
    flex-direction: column;
    min-width: 0;
    padding: 0.2em 0.5em;
    background: var(--surface-sunken);
    border-radius: var(--pill-radius, var(--radius-0));
  }
  .fr-ap b {
    font-weight: var(--fw-black);
    line-height: 1.05;
    color: var(--text-primary);
  }
  .fr-ap small {
    font-size: 0.42em;
    font-weight: var(--fw-bold);
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .fr-route > .ph-bold { color: var(--text-muted); font-size: 0.8em; flex: 0 0 auto; }
  .fr-chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    font-size: clamp(0.9em, min(3.4cqw, 5.5cqh), 2.6em);
  }
  .fr-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35em;
    padding: 0.3em 0.65em;
    font-weight: var(--fw-bold);
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
    white-space: nowrap;
    border-radius: var(--pill-radius, var(--radius-0));
  }
  .fr-chip .unit { font-weight: var(--fw-medium); font-size: 0.75em; }
  .fr-alt { background: var(--band); color: var(--on-accent); }
  .fr-seen { background: var(--surface-sunken); color: var(--text-secondary); }
  .fr-empty .fr-call { font-size: clamp(1.1em, min(6cqw, 12cqh), 4em); white-space: normal; }

  /* sm: route codes only, no airline / type / cities. */
  .size-sm .fr-airline,
  .size-sm .fr-model,
  .size-sm .fr-ap small { display: none; }
  .size-sm .fr-lockup { gap: var(--space-2); }

  /* xs: callsign + altitude only. */
  .size-xs .fr-body {
    flex-direction: column;
    justify-content: center;
    gap: var(--space-2);
  }
  .size-xs .fr-icon,
  .size-xs .fr-airline,
  .size-xs .fr-model,
  .size-xs .fr-route,
  .size-xs .fr-seen { display: none; }
  .size-xs .fr-lockup { flex: 0 0 auto; align-items: center; gap: var(--space-2); }
  .size-xs .fr-body .fr-call { font-size: clamp(1.4em, 16cqw, 3em); }
  .size-xs .fr-chips { justify-content: center; font-size: clamp(0.85em, 8cqw, 1.4em); }
`;

export default function render(shadow, ctx) {
  const data = ctx?.data ?? {};
  const t = ctx?.t || ((key, fallback) => fallback ?? key);
  const locale = ctx?.locale || "en";
  const size = ctx?.cell?.size || "md";
  const css = `<link rel="stylesheet" href="/static/style/spectra-widgets.css">`;
  const title = escapeHtml(t("title", "Nearest aircraft"));

  if (data.error) {
    shadow.innerHTML = `
      ${css}
      <div class="w" data-widget="fr24">
        <div class="w-title"><i class="ph-bold ph-warning-circle"></i><h3>${title}</h3></div>
        <div class="w-body"><p class="u-muted">${escapeHtml(data.error)}</p></div>
      </div>`;
    return;
  }

  const ac = data.aircraft;
  const titleBar = size === "xs" ? "" : `
    <div class="w-title">
      <i class="ph-bold ph-airplane-tilt" style="color:var(--accent-4)"></i>
      <h3>${title}</h3>
    </div>`;

  let body;
  if (ac) {
    const accent = bandAccent(Number(ac.altitude_ft) || 0);
    const alt = new Intl.NumberFormat(locale).format(Number(ac.altitude_ft) || 0);
    const route = ac.route;
    const modelText = [ac.model?.manufacturer, ac.model?.type].filter(Boolean).join(" ");
    body = `
      <div class="w-body stat-body fr-body"
           style="--band:var(${accent});--band-soft:var(${accent}-soft)">
        ${heroBlock(ac)}
        <div class="fr-lockup">
          ${route?.airline ? `<div class="fr-airline">${escapeHtml(route.airline)}</div>` : ""}
          <div class="stat-value fr-call">${escapeHtml(ac.callsign)}</div>
          ${modelText ? `<div class="fr-model">${escapeHtml(modelText)}</div>` : ""}
          ${route ? routeRow(route) : ""}
          <div class="fr-chips">
            <span class="fr-chip fr-alt"><i class="ph-bold ph-arrow-line-up"></i>${escapeHtml(alt)}<span class="unit">${escapeHtml(t("unit_ft", "ft"))}</span></span>
            <span class="fr-chip fr-seen"><i class="ph-bold ph-clock"></i>${escapeHtml(fmtTime(Number(ac.seen), locale))}</span>
          </div>
        </div>
      </div>`;
  } else {
    body = `
      <div class="w-body stat-body fr-body fr-empty"
           style="--band:var(--text-muted);--band-soft:var(--surface-sunken)">
        <div class="fr-icon"><i class="ph-bold ph-airplane"></i></div>
        <div class="fr-lockup">
          <div class="stat-value fr-call">${escapeHtml(t("empty", "No aircraft in range"))}</div>
          <div class="fr-chips">
            <span class="fr-chip fr-seen"><i class="ph-bold ph-clock"></i>${escapeHtml(fmtTime(Number(data.updated), locale))}</span>
          </div>
        </div>
      </div>`;
  }

  shadow.innerHTML = `
    ${css}
    <style>${LAYOUT}</style>
    <div class="w size-${escapeHtml(size)}" data-widget="fr24">
      ${titleBar}
      ${body}
    </div>`;
}
