# Lupin 1.0.2

This record describes the 1.0.2 changes and source/native preflight. Final package
and publication checks accompany the release. The installed host application and
its approved screen-sharing session are preserved during release preparation.

## Changes

- Reject the separate “Total Sales / Total Received” ledger as a player shop and
  read the actual shop listings instead. Summary labels never become priced
  items, while the original pixels remain available to inventory descriptions.
- Prioritize current shop listings for 1.5 seconds after a verified scroll, while
  preserving separate inventory hover, manual search and watched-item selection.
  The game's own description remains unchanged. Only independently verified
  current-page references can be drawn over it; covered unknown rows stay unknown.
- Reject outdated row results when their asking-price or icon pixels change
  during OCR. A vanished native shop retires current offers while preserving its
  bounded recovery cache; returning asking prices require the full source proof.
  These source checks do not themselves assume a scroll occurred.
- Establish item identity from visible name, type and distinctive item artwork
  before consulting market prices. Duplicate names cannot be resolved by the
  presence of a price, and visual proofs are local to the observed row or slot.
- Ignore hypothetical scroll-tier colors for non-scroll items, normalize narrow
  quotation formatting differences, and retain meaningful variant distinctions.
- Associate inventory source slots with the primary native description across
  supported positions and scales, keeping adjacent comparison panels separate.
- Replace indefinite checking and misleading no-data labels with explicit
  identification, variant-verification and sales-data states.
- Correct the audit's active-request timeout bug through a dedicated rescan API.
  Submitted requests now carry their own frame/context/deadline, while a separate
  observation controller owns shop identities, retention and description focus.
- Select unique exact-ID search results independently of market coverage, remove
  retired provider-selection plumbing and share one local quote/status result.
- Extract annotation geometry, remove unused legacy drawing paths and retain
  the distinct identity, viewport, offer, opacity and history authorities.
- Require the compiled Windows reader and shipped runtime files before staging
  or Setup compilation. Shared QA helpers select explicit versions, report or
  require migration baselines, and isolate native/Wine UI checks from the desktop.

## Validation

- The complete Python source suite passes **991 tests in 167.053 seconds**, with
  three platform/offscreen skips. The final run uses private Xvfb/D-Bus, temporary
  user paths, software rendering, bounded inference threads and reduced priority.
- Integration checks reject old icon/asking-price results after source changes,
  retire offers when a shop vanishes and prevent name-only recovery from restoring
  a different same-name item. New snapshot generations preserve visual identity
  and update existing cards when only the missing-reference reason changes.
- Shop-priority checks cover expiry without another frame, late reply rejection,
  dragging, native orange selection and known annotation/description occlusion.
  Selection equivalence preserves measured glyph coverage and exact icon pixels;
  an unrecognized new panel requests fresh OCR without claiming a scroll.
- Regression checks preserve active OCR deadlines during source retirement,
  retain real timeout handling and keep EXP submissions from consuming unread
  shop frames. Controller, immutable request, shared-proof and annotation-geometry
  checks preserve current/held offer distinctions and existing transition timers.
- Exact-ID search works with absent and expired snapshots. Delayed image arrivals
  can resolve a verified row after harmless selection recoloring, while changed
  icon/price pixels and unexplained cursor/tooltip occlusion remain rejected.
- Screenshot analysis identifies the clipped ring's hypothetical scroll-tier
  filter, quoted-name formatting, the adjacent comparison-panel association and
  Blue Moon top/earring ambiguity. Public/generated regressions cover the fixes;
  private player screenshots are not included.
- Both local changelog footers match the README. Update-review tests retain the
  compact plain-text summary without the donation images or HTML.
- All **46 release-tool tests** pass, covering required-reader preflight, stage
  preservation, compiler non-invocation on invalid inputs, exact artifact selection,
  migration reporting and Windows-Python bootstrap order. A harmless live probe
  confirms the common private Xvfb/D-Bus/offscreen-Qt wrapper. Windows known-folder
  containment prevents installer shortcuts from reaching the host desktop.
  Cleanup verifies ownership and containment before detaching a private QA portal
  mount; failures are reported separately from the actual test child status.
- All **34 native Rust tests** pass with pinned Rust 1.98.1. Both Linux musl
  and Windows gnullvm release readers are rebuilt offline. Two generated native
  regressions pass against the GNU and musl readers; private whole-frame replay
  verifies the actual shop, ledger-only frame and inventory-description path.
- The independent post-implementation integration review found no concrete
  remaining defect. The audit recommendations were implemented after authorization;
  stable settings/socket/desktop IDs and active upgrade compatibility remain.

Unsupported panel arrangements remain ambiguous; sub-one native UI scaling
retains the existing minimum title-marker limitation. Native Windows game capture
and WebView2 acceptance are not established by Wine checks. Final installer,
upgrade and publication results accompany the release in `VERIFICATION-1.0.2.md`.
The user authorized building, committing and publishing 1.0.2 after the
sales-summary fix; host installation remains a separate user action.

Private player screenshots remain outside the repository and packages. Public
regressions use generated or existing non-private fixtures. All capture remains
ordinary screen pixels, with no game hooks, input automation or process access.

## Release notes

Use the user-facing changes from [Change notes](CHANGELOG.md) when a release is
authorized. Include the centered footer below at the bottom of GitHub release
notes as well as this local patch record; its absolute image links work in both.

<br>

<h3 align="center">Buy monkey a beer</h3>
<!-- Balance the artwork's transparent padding so its visible centers align. -->
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="9" alt=""><a href="https://www.paypal.me/zhuffman68"><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/donate.png" width="190" align="middle" alt="Donate with PayPal"></a>
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="32" alt=""><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/lupin-beer.gif" width="96" alt="Lupin drinking a beer">
</p>
