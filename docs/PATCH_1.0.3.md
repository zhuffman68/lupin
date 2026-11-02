# Lupin 1.0.3

Steadier shop and inventory prices, clearer hover placement, and smoother recent-item history.

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

### Install or update

Use **Settings → Check now** in Lupin, then **Download & install**, or download the package for your system below.

- **Windows:** run `Lupin-1.0.3-Windows-x64-Setup.exe`.
- **Arch/Manjaro:** `sudo pacman -U ./lupin-1.0.3-1-x86_64.pkg.tar.zst`
- **Debian/Ubuntu:** `sudo apt install ./lupin_1.0.3-1_amd64.deb`

Settings, caches and watched items are preserved. Python, OCR and both local translation models are included. Windows uses the shared WebView2 runtime; Linux uses WebKitGTK, PipeWire and its desktop sharing portal.

Checksums, signed update metadata, build information and a verification report accompany the packages. Windows installer transactions are checked under Wine; native Windows game-capture and WebView2 acceptance remain separate from those checks.

[Detailed verification](https://github.com/zhuffman68/lupin/releases/download/v1.0.3/VERIFICATION-1.0.3.md)

<br>

<h3 align="center">Buy monkey a beer</h3>
<!-- Balance the artwork's transparent padding so its visible centers align. -->
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="9" alt=""><a href="https://www.paypal.me/zhuffman68"><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/donate.png" width="190" align="middle" alt="Donate with PayPal"></a>
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="32" alt=""><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/lupin-beer.gif" width="96" alt="Lupin drinking a beer">
</p>
