# Lupin 1.0.5

Quicker item pricing, clearer Korean chat reading, and more useful database maps.

- Complete shop listings can be priced on their first read, including when an item description touches the unused space beside them.
- Inventory prices can appear before the remaining shop readings finish. Reusing unchanged tooltip checks reduces delay and repeated work while retaining item, scroll and NPC-shop validation.
- Maps show verified portals, destination names and links to released maps. Portals and monster spawns have separate controls.
- Minimap previews support zoom buttons, mouse-wheel zoom and drag panning. Back restores the previous view; Fit resets it.
- Quest pages link to the next steps in a sequence, including Rowen's Cursed Dolls quests.
- Korean chat-history reading handles moving backgrounds, timestamps and channel labels more reliably. Difficult messages yield to other rows, and interrupted readings can retry.
- Market-status ages use rolling numbers without redrawing the surrounding text.

### Install or update

Use **Settings → Check now** in Lupin, then **Download & install**, or download the package for your system below.

- **Windows:** run `Lupin-1.0.5-Windows-x64-Setup.exe`.
- **Arch/Manjaro:** `sudo pacman -U ./lupin-1.0.5-1-x86_64.pkg.tar.zst`
- **Debian/Ubuntu:** `sudo apt install ./lupin_1.0.5-1_amd64.deb`

Settings, caches and watched items are preserved. Python, OCR and both local translation models are included. Windows uses the shared WebView2 runtime; Linux uses WebKitGTK, PipeWire and its desktop sharing portal.

Checksums, signed update metadata, build information and a verification report accompany the packages. Recorded-frame tests do not establish live translation accuracy or a universal recognition time. Installer checks under Wine do not establish native Windows capture or WebView2 acceptance. Meso totals count confirmed visible pickups; hidden or unread messages can still be missed.

[Detailed verification](https://github.com/zhuffman68/lupin/releases/download/v1.0.5/VERIFICATION-1.0.5.md)

<br>

<h3 align="center">Buy monkey a beer</h3>
<!-- Balance the artwork's transparent padding so its visible centers align. -->
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="9" alt=""><a href="https://www.paypal.me/zhuffman68"><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/donate.png" width="190" align="middle" alt="Donate with PayPal"></a>
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="32" alt=""><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/lupin-beer.gif" width="96" alt="Lupin drinking a beer">
</p>
