# Lupin 1.0.6

Find recent shop locations, browse consistent item cards, and use a more responsive interface while reading the screen.

- **Where seen:** item cards in Prices and Database show recent sellers, channels, FM rooms or map locations, asking prices, quantities and sighting ages. Results load when opened, animate in and stay cached for 15 minutes.
- Search, watched/recent items and inventory descriptions share full item cards. Shop rows open the same view with their asking price; paired stats and full-width tabs make details easier to browse.
- On-screen items use the available height. List/detail navigation keeps scroll positions, with steadier cards and clear sliding transitions.
- Reduced repeated work during screen reading, crowded shop hovers, card changes and image loading. Slides, resizing, scrolling, watched-item expansion and rolling numbers retain their effects.
- More consistent inventory prices through brief unreadable frames and moving descriptions, including consumables, scrolls and materials with a shop open. Shop-item hovers keep the shop's listing labels.
- Korean reading handles clear messages with unreadable timestamps or senders. Translation checks shortage and negation, improves party/skill wording and drops obsolete results.
- Hidden pages and unchanged overlays do less work. Translation loads on demand and can release after an idle interval; both local models remain included.
- Window placement is remembered, Settings can clear cached installers, and Linux packages omit unused debug data.

### Install or update

Use **Settings → Check now** in Lupin, then **Download & install**, or download the package for your system below.

- **Windows:** run `Lupin-1.0.6-Windows-x64-Setup.exe`.
- **Arch/Manjaro:** `sudo pacman -U ./lupin-1.0.6-1-x86_64.pkg.tar.zst`
- **Debian/Ubuntu:** `sudo apt install ./lupin_1.0.6-1_amd64.deb`

Settings, caches and watched items are preserved. Python, OCR and both local translation models are included. Windows uses the shared WebView2 runtime; Linux uses WebKitGTK, PipeWire and its desktop sharing portal.

Shop locations are recent sightings: an item may have sold, and its equipment stats are unverified. Recognition and translation depend on visible, readable text. Test replays do not establish a universal frame rate or recognition time; Wine checks do not establish native Windows capture or WebView2 acceptance.

Checksums, signed update metadata, build information and [detailed verification](https://github.com/zhuffman68/lupin/releases/download/v1.0.6/VERIFICATION-1.0.6.md) accompany the packages.

<br>

<h3 align="center">Buy monkey a beer</h3>
<!-- Balance the artwork's transparent padding so its visible centers align. -->
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="9" alt=""><a href="https://www.paypal.me/zhuffman68"><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/donate.png" width="190" align="middle" alt="Donate with PayPal"></a>
</p>
<p align="center">
  <img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/header-spacer.svg" width="32" alt=""><img src="https://raw.githubusercontent.com/zhuffman68/lupin/main/docs/media/lupin-beer.gif" width="96" alt="Lupin drinking a beer">
</p>
