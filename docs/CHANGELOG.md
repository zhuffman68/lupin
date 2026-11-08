# Change notes

The [GitHub releases page](https://github.com/zhuffman68/lupin/releases) is the
source for published downloads. A local version note or successful build does not
mean that version has been published. Current test results and platform limits
remain in [VERIFICATION.md](../VERIFICATION.md).

## 1.0.5

See [the patch record](PATCH_1.0.5.md) for installation and verification details.

- Shop prices can use a complete first read immediately, including when a
  description touches unused space beside a listing.
- Inventory prices can appear before shop repair finishes. Repeated tooltip
  checks and alternate readings reuse unchanged pixels to reduce delay and CPU
  work, while changed items, scrolling and NPC shops retain their checks.
- Database maps show verified portals with destination names and links to other
  released maps. A separate Spawns toggle keeps portal views uncluttered.
- Map previews support zoom controls, mouse-wheel zoom and drag panning. Back
  restores the previous map view, and Fit resets it.
- Quest cards link to follow-up steps, including Rowen's Cursed Dolls chain,
  using completed-quest requirements as well as explicit next-step links.
- Korean reading detects complete chat-history rows without including scenery
  behind the text. Lupin beside the game and moving chat backgrounds no longer
  restart or mask those reads. Difficult rows yield to other messages;
  timestamps and channel badges stay out of translations, and interrupted reads
  can retry.
- Market-status ages roll their changing numbers while the surrounding text
  stays steady, including when the source has not published newer prices.

## 1.0.4

See [the patch record](PATCH_1.0.4.md) for downloads, installation and verification.

- Meso pickups keep counting while EXP values are being confirmed. Briefly
  unreadable character text holds the affected reading without restarting the
  session; a different character still pauses it safely. Waiting messages now
  distinguish a covered log from a delayed or unreadable reading.
- Shop prices reuse verified unchanged pages and avoid redundant reading.
  Newly opened or scrolled shops receive earlier reader time, and complete rows
  can appear while missing rows are still being checked.
- Inventory prices stay steady while a new item's orange highlight animates,
  including the blended border beside a weapon's icon.
- Shop labels fade more reliably when the add-item price form opens or moves
  over them, including when labels hide part of the form. Only overlapping
  labels fade. Moving the pointer over a verified form's controls no longer
  incorrectly ends the fade while other native form evidence remains visible.
- Settings pulses and shimmers while an application update is available.
  Reduce motion keeps a static update indicator.
- Settings uses compact General, Prices, Tracking, Translation and Updates
  pages, with matching cards and sliding navigation. Translation controls stay
  in sync with the main page, and the main window remains usable while editing.
- Shop rows touched by item descriptions recover more reliably after scrolling.
  A missed row no longer holds back other new prices or keeps the previous
  page's labels in place.
- NPC buy, Buy Back and sell lists stay excluded when changing inventory tabs,
  including empty Set-up pages. Separate inventory and equipped-item descriptions
  can still show prices, including when they overlap the NPC shop.

## 1.0.3

See [the patch record](PATCH_1.0.3.md) for installation and verification details.

- Shop prices and comparisons stay visible while hovering and scrolling,
  including orange-selected rows and pages with sold-out listings. Covered
  currency text and characters moving behind a shop no longer interrupt labels.
- Inventory and equipped-item prices appear with less delay and flicker, including
  personalized equipment, equipped comparisons and items near the window’s edges
  while shops are open. Animated hand cursors no longer make inventory prices
  repeatedly disappear and return; new-item highlights and scenery behind
  descriptions no longer interrupt an otherwise verified item. Inventory price
  cards prefer the space directly above the hovered description.
- Only shop labels overlapped by the add-item price form fade, then brighten when
  it closes, even when labels initially cover its inputs and buttons. Other
  labels stay visible while the listings are checked again.
- Recent-item history updates more smoothly as items are added.
- Animated card changes use safer cleanup to prevent native crashes.
- Sold Items windows no longer replace active shop listings.
- Market status shows when the source's prices are old and when Lupin will check again.

## 1.0.2

See [the patch record](PATCH_1.0.2.md) for validation and platform checks.

- Shop sales-summary panels, including “Total Sales / Total Received,” are
  excluded from item pricing so the actual shop listings can be read.
- Shop browsing prioritizes newly visible listings for 1.5 seconds after scrolling,
  including labels over an item description. Previous-page references cannot
  move onto new listings, and normal hover behavior returns after browsing stops.
- Duplicate item names require visible item evidence before receiving a market
  reference. An unpriced Blue Moon top cannot inherit the earrings' price.
- Late OCR and covered-row recovery cannot restore an asking price or item ID
  after its visible source changes or the shop disappears.
- Re-reading changed shop pixels preserves an active OCR request's timeout.
  Search by exact item ID works even when market data is missing or old.
- Clipped non-scroll names ignore hypothetical scroll-color hints, including
  Ink-and-Wash Painting Name Tag Ring. Quotation typography and missing spacing
  around quoted names receive conservative normalization.
- Inventory descriptions and comparison panels are associated with the hovered
  slot across supported window positions instead of choosing the nearest title.
- Price status distinguishes unidentified items, unverified variants and missing
  sales data. Combined-variant references remain withheld until verified.
- Windows staging requires its reader and runtime resources. Package checks
  select an explicit release and report missing migration coverage.
- Retired provider-selection and overlay paths are removed while saved settings
  and upgrade compatibility are preserved.

## 1.0.1

- Tracking automatically holds when Classic World can no longer be recognized,
  including manually selected capture areas. Timers, gains and pace are preserved,
  and returning to another character cannot silently replace the current run.
  Stop and a new Start release the previous character binding, including after
  a paused session. A tracking-hotkey pause stays manual during recognition loss.
- Meso tracking follows pickup lines through scrolling and fading, recognizes
  EXP, party and item messages as scrolling evidence, and preserves uncertain
  reads without treating them as an empty log. Pickup reading has its own bounded
  worker so shop OCR cannot delay it.
- Market refreshes follow the actual snapshot expiry, removing the gap between
  expired prices and the next scheduled fetch. Old source data uses bounded
  retries; refreshed shop labels update without hovering or rereading the shop.
- Periodic update checks catch up after a busy reader, cooldown or server retry
  deadline. Disabling launch checks cancels a pending launch request. Native
  notifications open a compact review with release notes, Later and Download &
  install; the same version is announced only once.

## 1.0.0

The first stable release brings together Prices, EXP/Meso Tracking, Translation
and Database, with the refinements below.

- Prices search results and their match count return together when cleared,
  preserving the existing shop/item cards without a second layout jump.
- Database sorting uses a compact popup in the existing breadcrumb row.
- Page-footer shortcuts use brighter, larger, bolder text in the same position
  on every tab, including both translation modes.
- Enter dismisses the Korean writer without a late preview resizing it. The
  translating/copied notice follows it into the same corner with a short
  transition and an independent expiry timer.
- Outgoing Korean uses verified game terminology for MapleStory, party quests,
  towns and common market shorthand while preserving exact item names. Scoped
  checks reject lost names, numeric roles, questions or negation.
- Source-preview desktop launchers refresh their own stale runtime paths;
  existing installed shortcut identities and custom assignments are preserved.
- Linux restarts retain desktop authentication and schema settings; a new
  launch can recover missing settings left by an older updater.
- Overlay startup uses a versioned handshake, bounded retries and a visible
  recovery action. Update success waits for the new app and its overlay helper.
- Windows update helpers run outside the installation directory and require a
  matching live-child startup receipt before reporting success.
- Gloves Attack Scroll: Chaos has user-confirmed availability. Verified,
  reachable catalyst recipes establish 14 further scroll outcomes. Fresh,
  exact native item observations can establish circulation independently of a
  recorded market sale; availability never supplies a missing price.

Package and publication verification is recorded in [VERIFICATION.md](../VERIFICATION.md).

## 0.17.10

- Clearer Database browsing, remembered sections and compact breadcrumb links.
- Broader Korean message coverage and bounded continuous-scan scheduling.
- Developer documentation consolidated; retired portable helpers removed.
- README header image markup adjusted to preserve the transparent presentation.
- Compact clipboard-only Korean writer beside the game HUD, with shared draft
  state, bounded preview expansion, OCR exclusions and native-focus fallback.

## Historical patch notes

These records preserve the behavior, local artifacts and acceptance limits at
the time. Follow current development and installation guides for current commands.

| Version | Main changes | Record |
| --- | --- | --- |
| 0.17.9 | Native-installer-only distribution; Korean reading and README revisions. | [Notes](archive/patches/PATCH_0.17.9.md) |
| 0.17.8 | Korean phrase handling, rescan reuse and translation history. | [Notes](archive/patches/PATCH_0.17.8.md) |
| 0.17.7 | Signed GitHub updates and steadier price-card transitions. | [Notes](archive/patches/PATCH_0.17.7.md) |
| 0.17.6 | Price-history transitions and hovered-description cards. | [Notes](archive/patches/PATCH_0.17.6.md) |
| 0.17.5 | Price-card grace, history animation and shop-label stability. | [Notes](archive/patches/PATCH_0.17.5.md) |
| 0.17.4 | Five-minute rates, retained pause pace and stable identity. | [Notes](archive/patches/PATCH_0.17.4.md) |
| 0.17.3 | EXP validation recovery and clearer reading states. | [Notes](archive/patches/PATCH_0.17.3.md) |
| 0.17.2 | Compact tracking cards, independent clocks and NPC-hover fixes. | [Notes](archive/patches/PATCH_0.17.2.md) |
| 0.17.1 | Tracking placement and separate overlay visibility controls. | [Notes](archive/patches/PATCH_0.17.1.md) |
| 0.17.0 | Pickup-based meso tracking, separate cards and clipboard writer. | [Notes](archive/patches/PATCH_0.17.0.md) |

<br>

<h3 align="center">Buy monkey a beer</h3>
<!-- Balance the artwork's transparent padding so its visible centers align. -->
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="9" alt=""><a href="https://www.paypal.me/zhuffman68"><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/donate.png" width="190" align="middle" alt="Donate with PayPal"></a>
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="32" alt=""><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/lupin-beer.gif" width="96" alt="Lupin drinking a beer">
</p>
