// Turn a reel caption into a short "what to get" line for a place card.
//
// Captions are the first 140 characters of an Instagram caption. Most start with the dish and
// then repeat where it is: "HOT LEMON PEPPER WINGS AND PIZZA IN EMERYVILLE, CA PIZZA GALLERY
// 6613 HOLLIS ST…", "Tried apple fritters from Stans Donuts in Santa Clara…", "… 📍Falafel Stop".
// So: cut at the first sign of the location, drop words left dangling by the cut, and if the
// caption was cut off mid-word, end on a whole word with "…".

const TRUNCATED_AT = 140; // Muse's caption snippet length
const MIN_KEEP = 12; // a cut this early would leave nothing useful; look for the next one

// Words that make no sense at the end of a trimmed line ("Tried apple fritters from").
const DANGLING = new Set([
  "a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with", "here", "this", "my", "our",
  "like", "located", "back", "now", "recommend", "today", "were", "i", "is", "are", "was", // compared without apostrophes: "were" = "we’re"
]);

// Leading/trailing decoration: emoji, flags, dividers, stray punctuation ("─── ⋆⋅☆·⋆ ──", "🌙🔥", "‼️").
const EDGE_JUNK = /^[^\p{L}\p{N}$@]+|[^\p{L}\p{N}?)]+$/gu;

export interface CaptionContext {
  name: string; // place name, e.g. "Stans Donuts"
  city: string | null;
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Loose pattern for a name: case-insensitive, any apostrophe or none, flexible spaces. */
function namePattern(name: string): RegExp | null {
  const words = name
    .replace(/[’']/g, "")
    .split(/[^\p{L}\p{N}&+]+/u)
    .filter(Boolean)
    .map((w) => w.split("").map(escapeRegex).join("['’]?"));
  return words.length ? new RegExp(words.join("[\\s\\-]*"), "iu") : null;
}

/** Index of the first location marker at or after MIN_KEEP, or -1. */
function firstCut(text: string, ctx: CaptionContext): number {
  const patterns: RegExp[] = [
    /📍/u,
    /\s(?:in|at)\s+[\p{L} .'’]+,\s*(?:ca|california)\b/iu, // " in Emeryville, CA"
    /\s\d{2,6}\s+[\p{L}]+\s+(?:st|ave|rd|blvd|dr|way|pl|ln|ct|pkwy|hwy|street|avenue|road|boulevard)\b/iu, // " 6613 Hollis St"
    /@[\w.]+/u, // "@tacko_sf"
  ];
  if (ctx.city) patterns.push(new RegExp(`\\s(?:in|at)\\s+${escapeRegex(ctx.city)}\\b`, "iu"));
  const name = namePattern(ctx.name);
  if (name) patterns.push(name);

  let cut = -1;
  // End of the first sentence ("…best BBQ spot?! Smoky, tender…"): keep the punctuation.
  for (const m of text.matchAll(/[.!?‼]+(?=\s)/gu)) {
    if (m.index !== undefined && m.index >= MIN_KEEP) {
      cut = m.index + m[0].length;
      break;
    }
  }
  for (const re of patterns) {
    const global = new RegExp(re.source, re.flags.includes("g") ? re.flags : re.flags + "g");
    for (const m of text.matchAll(global)) {
      if (m.index !== undefined && m.index >= MIN_KEEP) {
        if (cut === -1 || m.index < cut) cut = m.index;
        break;
      }
    }
  }
  return cut;
}

function dropDangling(text: string): string {
  let words = text.trim().replace(/[\s,;:\-–—!.]+$/u, "").split(/\s+/);
  while (words.length > 1 && DANGLING.has(words[words.length - 1].toLowerCase().replace(/[^\p{L}]/gu, ""))) {
    words = words.slice(0, -1);
  }
  return words.join(" ").replace(/[\s,;:\-–—]+$/u, "");
}

function sentenceCaseIfShouting(text: string): string {
  const letters = text.replace(/[^\p{L}]/gu, "");
  const upper = letters.replace(/[^\p{Lu}]/gu, "");
  if (letters.length > 10 && upper.length / letters.length > 0.6) {
    const lower = text.toLowerCase();
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  }
  return text;
}

export function dishLine(caption: string | null, ctx: CaptionContext): string | null {
  if (!caption) return null;
  const wasTruncated = caption.length >= TRUNCATED_AT;
  let text = caption
    .replace(/#[\p{L}\p{N}_]+/gu, " ")
    .replace(/^\s*edit:\s*/iu, "") // "Edit: OPEN LATE…"
    .replace(/\s+/g, " ")
    .trim();
  // A caption that opens with the place's handle ("@theoldcityroastery is a…") reads better with its name.
  text = text.replace(/^@[\w.]+/u, ctx.name);

  const cut = firstCut(text, ctx);
  let ellipsis = false;
  if (cut !== -1) {
    text = text.slice(0, cut);
  } else if (wasTruncated) {
    text = text.replace(/\s+\S*$/u, ""); // drop the half-word Muse cut off
    ellipsis = true;
  }

  text = dropDangling(text.replace(/📍/gu, " ").replace(EDGE_JUNK, "").trim());
  text = text.replace(EDGE_JUNK, "").trim();
  if (text.replace(/[^\p{L}]/gu, "").length < 4) return null;
  text = sentenceCaseIfShouting(text);
  text = text.charAt(0).toUpperCase() + text.slice(1);
  return ellipsis ? `${text}…` : text;
}
