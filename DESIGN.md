---
name: Chinese Etymology & Story Guide (HanyuBuTaiNan)
description: Modern Lexicographic Atelier ("Cinnabar & Inkstone") design system for HSK 1-9 etymology and vocabulary mastery.
colors:
  cinnabar-seal: "#b8332a"
  cinnabar-deep: "#9e2820"
  cinnabar-wash: "#fbeae8"
  bamboo-paper: "#f6f4ef"
  archival-leaf: "#fcfbf8"
  parchment-alt: "#f2efe8"
  parchment-muted: "#ede9e0"
  pine-soot-ink: "#16191d"
  warm-stone: "#5c5852"
  hairline-rule: "#dcd6ca"
  control-rule: "#c6beb0"
  mineral-jade: "#1b6b52"
  classic-indigo: "#284b7a"
  bronze-ochre: "#9a5b13"
  inkstone-dark: "#111317"
  lacquer-card: "#181b21"
  luminous-cinnabar: "#e05347"
typography:
  display:
    fontFamily: "\"Songti SC\", \"STSong\", \"Noto Serif CJK SC\", \"Source Han Serif SC\", Georgia, serif"
    fontSize: "1.58rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  hanzi:
    fontFamily: "\"Songti SC\", \"STSong\", \"Noto Serif CJK SC\", \"Source Han Serif SC\", \"PingFang SC\", serif"
    fontSize: "1.8rem"
    fontWeight: 700
    lineHeight: 1.15
  title:
    fontFamily: "\"Songti SC\", \"STSong\", \"Noto Serif CJK SC\", Georgia, serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.35
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, \"Helvetica Neue\", \"PingFang SC\", sans-serif"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif"
    fontSize: "0.78rem"
    fontWeight: 600
    lineHeight: 1.4
rounded:
  xs: "3px"
  sm: "4px"
  md: "6px"
  lg: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "14px"
  lg: "20px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.cinnabar-seal}"
    textColor: "{colors.archival-leaf}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "38px"
  button-primary-hover:
    backgroundColor: "{colors.cinnabar-deep}"
  button-secondary:
    backgroundColor: "{colors.archival-leaf}"
    textColor: "{colors.pine-soot-ink}"
    rounded: "{rounded.sm}"
    padding: "0 14px"
    height: "36px"
  badge-hsk-seal:
    backgroundColor: "{colors.cinnabar-wash}"
    textColor: "{colors.cinnabar-seal}"
    rounded: "{rounded.xs}"
    padding: "2px 9px"
  card-lexicon:
    backgroundColor: "{colors.archival-leaf}"
    textColor: "{colors.pine-soot-ink}"
    rounded: "{rounded.md}"
    padding: "16px"
---

# Design System: Chinese Etymology & Story Guide

## Overview

**Creative North Star: "Modern Lexicographic Atelier (Cinnabar & Inkstone)"**

The interface draws from authoritative bilingual scholarly dictionaries (such as *Cihai* and classical sinological press editions), pairing tactile warm bamboo-pulp paper surfaces (`#f6f4ef`) and elevated cream leaves (`#fcfbf8`) with deep pine-soot ink (`#16191d`) and archival seal-vermilion accents (`#b8332a`). Every surface prioritizes high-density scanability, immediate radical/phonetic legibility, and calm reading ergonomics during long study sessions.

In Dark Mode ("Inkstone Lacquer & Luminous Vermilion"), the workspace shifts to a low-glare inkstone slate (`#111317`) and lacquer card surface (`#181b21`) with rice-paper typography (`#f3f0e8`) and luminous vermilion (`#e05347`).

**Key Characteristics:**
- Archival paper ground (`#f6f4ef`) with crisp editorial hairlines (`#dcd6ca`) and full-perimeter framed callout boxes.
- Square-cornered Cinnabar Seal Stamp badges (`3px` radius) for HSK levels that echo traditional carved collector seals (印章).
- High-contrast Songti/Serif CJK character lockups paired with clean system sans-serif UI labels and tabular numerals (`tabular-nums`).
- Split-screen resilience: filter bars reflow into a balanced 2-column grid at `<= 980px` with strict `min-width: 0` and single-line ellipsis truncation on all picker triggers and HSK level headings.

## Colors

The palette contrasts warm archival paper neutrals against decisive cinnabar seal-red and mineral scholarly accents.

### Primary
- **Cinnabar Seal** (`#b8332a`): Primary interactive accent, masthead top rule, active mode tab underline, mastery progress bar, and HSK seal stamp border/text.
- **Cinnabar Deep** (`#9e2820`): Hover and active state for primary actions.
- **Cinnabar Wash** (`#fbeae8`): Soft vermilion tint for HSK seal badge grounds and control hover states.

### Secondary
- **Mineral Jade** (`#1b6b52` / dark `#3cc499`): Positive feedback, verified etymology trust cards, valid radical-phonetic combinations, and SRS "Easy" ratings.
- **Classic Indigo** (`#284b7a` / dark `#8aa8e6`): Compound-word classification badges and Tone 1 indicators.
- **Bronze Ochre** (`#9a5b13` / dark `#eab854`): Phonetic-semantic (`形声`) badges, bilingual tags, and warning notices.

### Neutral
- **Bamboo Paper** (`#f6f4ef` / dark `#111317`): Page canvas background.
- **Archival Leaf** (`#fcfbf8` / dark `#181b21`): Elevated card, masthead, modal, and input surfaces.
- **Parchment Alt** (`#f2efe8` / dark `#1d2129`): Secondary wells, character lockup boxes, and breakdown key-value blocks.
- **Pine-Soot Ink** (`#16191d` / dark `#f3f0e8`): Primary reading and Hanzi glyph color.
- **Warm Stone** (`#5c5852` / dark `#a8a39a`): Secondary metadata, Pinyin ruby annotations, and labels.
- **Hairline Rule & Control Rule** (`#dcd6ca` / `#c6beb0`): Structural card borders and interactive input strokes.

### Named Rules
**The Seal Stamp Rule.** Cinnabar red (`#b8332a`) is reserved for primary actions, active wayfinding indicators, and HSK seal stamps — never washed across whole cards or large reading backgrounds.

## Typography

**Display & HSK Section Font:** `"Songti SC", "STSong", "Noto Serif CJK SC", "Source Han Serif SC", Georgia, serif`
**Hanzi Lockup Font:** `"Songti SC", "STSong", "Noto Serif CJK SC", "Source Han Serif SC", "PingFang SC", serif`
**Body & UI Font:** `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "PingFang SC", sans-serif`

**Character:** Scholarly, calligraphic Songti serifs give Chinese glyphs and section headers the authority of a printed dictionary, while the modern system UI stack keeps bilingual definitions, Pinyin diacritics, and controls effortless to scan at small sizes.

### Hierarchy
- **Display** (`700`, `1.58rem`, `1.25` line-height, `-0.02em` tracking): Masthead title (`header.hero h1`).
- **Hanzi Ruby Lockup** (`700`, `1.14rem–2.25rem` scaled by character count, `1.15` line-height): Primary character display with `0.58rem–0.76rem` Pinyin `<rt>` annotations above each character.
- **Title** (`700`, `1rem`, `1.35` line-height): HSK level section headers (`.hsk-level-heading h3`) and deep-dive card titles.
- **Body** (`400–500`, `0.88rem–0.94rem`, `1.6` line-height): Etymology narratives, component breakdowns, and example sentences.
- **Label** (`600`, `0.74rem–0.82rem`, `tabular-nums`): Filter labels, stat chips, SRS counters, and HSK seal badges.

### Named Rules
**The Tabular Count Rule.** Every counter, HSK level badge, mastery percentage, and SRS interval uses `font-variant-numeric: tabular-nums` so numbers align cleanly and never jitter when filters update.

## Layout

- **Container**: Centered max-width `1180px` container with `24px 20px 72px` desktop padding (`14px 12px 60px` at `<= 980px`, `10px 10px 52px` at `<= 640px`).
- **Half-Screen (700–960px) Filter Grid**: At `@media (max-width: 980px)`, `.dropdown-row` switches from a single flex row to a 2-column CSS grid (`grid-template-columns: repeat(2, minmax(0, 1fr))`), ensuring the 4 HSK filter boxes (`Standard`, `HSK Level`, `Category`, `Sort`) have ample horizontal breathing room when the browser is snapped to half-screen.
- **Strict Flex/Grid Truncation**: Every `.select-group`, `.custom-picker`, `.picker-trigger`, `.scroll-select`, `.hsk-level-heading`, and `.vocab-char-lockup` enforces `min-width: 0` on flex/grid children and `overflow: hidden; text-overflow: ellipsis; white-space: nowrap` on its label span.

## Elevation & Depth

Surfaces sit on a warm paper plane with restrained ink-wash shadows and crisp `1px` structural borders. Depth increases on hover or modal focus rather than relying on heavy drop shadows at rest.

### Shadow Vocabulary
- **Resting Card (`--shadow`)** (`0 2px 5px -1px rgba(22, 25, 29, 0.06), 0 1px 2px -1px rgba(22, 25, 29, 0.04)`): Applied to cards, inputs, and dropdown triggers.
- **Elevated / Hover (`--shadow-lg`)** (`0 12px 26px -6px rgba(22, 25, 29, 0.11), 0 4px 10px -3px rgba(22, 25, 29, 0.06)`): Applied to hovered vocabulary cards, active flashcards, open popover menus, and the character inspector dialog.

### Named Rules
**The Full-Frame Callout Rule.** Callouts, classical quotes, word-logic boxes, and HSK level headings use full-perimeter `1px` borders (`var(--border-strong)`) rather than decorative one-sided left border bars.

## Shapes

- **Cards & Panels**: `6px` (`--radius: 0.375rem`) for a crisp, bookish silhouette.
- **Inputs, Buttons & Triggers**: `4px` (`calc(var(--radius) - 2px)`).
- **HSK Seal Badges (`.badge-hsk`)**: `3px` square-stamped corners echoing traditional carved stone seals.

## Components

### Buttons
- **Shape:** Gently squared corners (`4px` radius).
- **Primary (`.btn-primary`):** Cinnabar Seal background (`#b8332a`), Archival Leaf text (`#fcfbf8`), `38px` height, `0 16px` padding.
- **Secondary (`.btn-secondary`, `.hero-btn`):** Archival Leaf background (`#fcfbf8`), Control Rule border (`#c6beb0`), Pine-Soot Ink text (`#16191d`), shifting to Cinnabar Wash (`#fbeae8`) on hover.

### Chips & Badges
- **HSK Seal Badge (`.badge-hsk`):** Square-cornered (`3px`) stamp with Cinnabar Wash background (`#fbeae8`), `1px` translucent Cinnabar border, and bold Cinnabar text (`#b8332a`).
- **Classification Badges:** Tinted mineral washes (Jade for `会意`, Ochre for `形声`, Indigo for compounds, Plum for pictographs).

### Cards / Containers
- **Masthead (`header.hero`):** Framed with a `1px` strong border, an inset `3px` top Cinnabar seal bar, and a `3px double` editorial divider above the stats row.
- **Vocabulary Cards (`.vocab-card`):** Archival Leaf surface (`#fcfbf8`), `16px` padding, bordered character ruby lockup box (`.vocab-char-lockup`), and structured breakdown well (`.kv`).

### Inputs / Fields & Custom Pickers
- **Picker Trigger (`.picker-trigger`):** `38px` height, flex layout with `min-width: 0`, left label span truncated with `text-overflow: ellipsis`, and right action hint pinned with `flex: 0 0 auto`.
- **Focus:** `2px` background offset ring plus `4px` Cinnabar ring (`--focus-ring`).

### Navigation
- **Mode Ribbon (`.mode-nav`):** Sticky frosted parchment bar (`backdrop-filter: blur(8px)`) where the active tab elevates to Archival Leaf (`#fcfbf8`) with an inset `2px` bottom Cinnabar bar.

## Do's and Don'ts

### Do:
- **Do** enforce `min-width: 0` on all flex and grid children containing dynamic text or dropdown triggers (`.select-group`, `.custom-picker`, `.picker-trigger > span:first-child`, `.hsk-level-heading h3`).
- **Do** normalize both user input and stored Pinyin answers by stripping tone marks, tone digits (`1–5`), and extra whitespace before comparison in flashcard practice.
- **Do** maintain `>= 40px` touch targets on mobile viewports (`<= 640px`).

### Don't:
- **Don't** use one-sided `border-left` bars on rounded containers; use full-perimeter borders (`1px solid var(--border-strong)`).
- **Don't** allow 4 filter dropdowns to crowd a single row at half-screen widths (`700–960px`); use the 2-column grid at `<= 980px`.
- **Don't** exceed the `500 KB` size budget for `hanyubutainan.html`.
