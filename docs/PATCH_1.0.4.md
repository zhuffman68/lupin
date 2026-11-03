# Lupin 1.0.4

Faster shop pricing, steadier item overlays, and more reliable pickup tracking.

- Shop prices load sooner and recover more reliably while hovering and scrolling. Complete rows can appear while other listings are still being checked.
- Inventory prices stay steady while an item's orange highlight animates, including the blended border beside equipment icons.
- Only shop labels covered by the add-item price form fade. Detection is more reliable when labels or the pointer cover its controls, and labels brighten when the form closes.
- NPC buy, Buy Back and sell lists stay excluded, including empty Set-up pages. Separate inventory and equipped-item descriptions can still show prices.
- Meso pickups keep counting while EXP values are being confirmed. Brief name-reading failures no longer restart the session, and waiting messages distinguish delayed readings from a covered log.
- Settings has compact sections matching the rest of Lupin, and its button pulses and shimmers when an update is available. Reduce motion keeps a static indicator.

### Install or update

Use **Settings → Check now** in Lupin, then **Download & install**, or download the package for your system below.

- **Windows:** run `Lupin-1.0.4-Windows-x64-Setup.exe`.
- **Arch/Manjaro:** `sudo pacman -U ./lupin-1.0.4-1-x86_64.pkg.tar.zst`
- **Debian/Ubuntu:** `sudo apt install ./lupin_1.0.4-1_amd64.deb`

Settings, caches and watched items are preserved. Python, OCR and both local translation models are included. Windows uses the shared WebView2 runtime; Linux uses WebKitGTK, PipeWire and its desktop sharing portal.

Checksums, signed update metadata, build information and a verification report accompany the packages. Installer checks under Wine do not establish native Windows game-capture or WebView2 acceptance. Meso totals describe confirmed visible pickups; unread or hidden messages can still be missed.

[Detailed verification](https://github.com/zhuffman68/lupin/releases/download/v1.0.4/VERIFICATION-1.0.4.md)

<br>

<h3 align="center">Buy monkey a beer</h3>
<!-- Balance the artwork's transparent padding so its visible centers align. -->
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="9" alt=""><a href="https://www.paypal.me/zhuffman68"><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/donate.png" width="190" align="middle" alt="Donate with PayPal"></a>
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="32" alt=""><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/lupin-beer.gif" width="96" alt="Lupin drinking a beer">
</p>
