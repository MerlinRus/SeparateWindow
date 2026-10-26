# Reviewer instructions — Separate Window 1.2.0

No account, credentials, payment, external application or server is required.
The publisher is Mycelium; support: qobuz43@gmail.com.

1. Open any ordinary HTTP(S) page with a visible video, image or interactive widget. Internal Chrome pages and the Chrome Web Store restrict extensions.
2. Click the extension icon and “Select a page element”. Move the pointer to an element; scrolling changes the selected ancestor. Click to open it in a popup. Esc cancels.
3. Only the chosen element should be visible. Hover in the top-right corner to reveal translucent controls. Moving away hides them.
4. Test zoom/rotation/brightness, save/remove geometry and the PNG screenshot button. The controls are hidden from screenshots.
5. Use the star to create a bookmark in “Separate windows”. Its link reopens the saved element when the extension is installed. Regular later visits show a small reopen button.
6. Use “Back to tab” to restore the original page without reloading. Native popup close instead recovers the page by loading it in a normal tab; live JS/media state is not guaranteed in that case.
7. A cross-origin iframe is selected as a whole. Selection intercepts pointer events instead of toggling the player's play/pause controls.
8. Start a video and use “Always on top” in the hover toolbar. Chrome displays that video in a separate picture-in-picture window without reloading the source player, including nested cross-origin frames. Press “Return video” or close PiP to return it. Site controls/subtitles may not appear, and some players prohibit PiP. Images and arbitrary widgets do not support this mode. No external component or additional permission is required.

The store screenshots use an original canvas-generated demonstration video, captured from the real extension UI. They contain no third-party movie footage, personal data or service credentials. Russian and English are selected automatically from the browser UI language.

Source and reproducible automation: https://github.com/MerlinRus/SeparateWindow
Run `python tests/smoke.py` for the isolated Chromium test. Run `python tools/store_assets.py` to reproduce the listing images. Build with `python tools/package.py`.
