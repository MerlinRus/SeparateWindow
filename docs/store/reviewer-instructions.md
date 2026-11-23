# Reviewer instructions — Separate Window 1.4.14

No account, credentials, payment, external application or server is required.
The publisher is Mycelium; support: qobuz43@gmail.com.

1. Open any ordinary HTTP(S) page with a visible video, image or interactive widget. Internal Chrome pages and the Chrome Web Store restrict extensions.
2. Click the extension icon and “Select a page element”. Move the pointer to an element; scrolling changes the selected ancestor. Click to open it in a popup. Esc cancels.
3. Only the chosen element should be visible. Hover in the top-right corner to reveal translucent controls. Moving away hides them.
4. Test zoom, rotation, saving and clearing window geometry, and taking a PNG screenshot. The controls are hidden from screenshots.
5. Use the star to create a bookmark in “Separate windows”. Its link reopens the saved element when the extension is installed. Regular later visits show a small reopen button.
6. Use “Back to tab” to restore the original page without reloading. Native popup close instead recovers the page by loading it in a normal tab; live JS/media state is not guaranteed in that case.
7. A cross-origin iframe is selected as a whole. Selection intercepts pointer events instead of toggling the player's play/pause controls.

For a supported player, click the video surface in the picker to select the whole player. After detaching, use its timeline and quality menu, then click the center once to pause or resume. Use the player’s fullscreen button to enter fullscreen. “Video only” and “Show player” toggle between a clean picture and the original controls without reloading.

Resize a detached YouTube window and hover or click around 70% of the timeline. The pointer and preview or seek position should agree, and the window should have no outer scrollbars. Repeat after using the zoom buttons.

Resize a detached Twitch player and verify that the video and controls follow the player bounds without outer scrollbars. Open Settings, choose a quality option, then reopen the menu to verify the selection. Also resize a detached cross-origin iframe and verify that its own viewport follows the window. Run `python tests/player_layout.py` to reproduce these cases locally.

In a detached RUTUBE embed, open the native gear menu and the quality submenu. Open the block link from the extension toolbar and press Escape to close it. If the selected video has not loaded its metadata, “Always on top” should ask you to start playback.
8. Start a video and use “Always on top” in the hover toolbar. Chrome opens the video in its built-in picture-in-picture player, including nested cross-origin frames inside closed web components. Press “Unpin” or close the floating window to return to the player. Site controls and subtitles may be unavailable, and some players prohibit PiP.

9. Change Language in the extension menu using the RU / EN buttons (browser language is the initial default). Verify that the popup, existing picker/toolbar, tooltips, messages and context menu update without reloading the page, and the preference survives reopening the menu.

10. Dynamic non-video panels preserve their measured ancestor sizes and are reselected after the page replaces their DOM nodes. Run `python tests/dashboard.py` for a local ResizeObserver-based reproduction with live updates, clicks, window resizing, replacement of both panel and parent, and restoration. No private Grafana instance is required or claimed to have been tested.

The store gallery follows a single real workflow: open the extension menu, select a player, watch the same video in a separate window. The first image combines actual menu header and button captures to focus on the action. The second shows the selection outline, and the third shows the actual clean video frame. The source page surrounds an original canvas-generated demo video with sample advertising banners, recommendations and a subscription panel. A fourth screenshot demonstrates the same extension isolating an interactive calculator; its input fields and calculate button are exercised after detaching it. There are no invented workspaces, third-party movie footage, personal data or service credentials.

Source and reproducible automation: https://github.com/MerlinRus/SeparateWindow
Run `python tests/smoke.py` for the isolated Chromium test. Run `python tools/store_assets.py` to reproduce the listing images. Build with `python tools/package.py`.

11. Check the full-size toolbar icon. In the popup, “Rate us” opens Chrome Web Store reviews. “Report a bug” and “Suggest a feature” open separate localized GitHub issue drafts containing the extension version. The user submits them manually. No active page address or content is attached. An email link is also available. `python tests/popup.py` checks both locales, layout, destinations and icon sizes.

12. On an HTTPS page, use “Always on top” with a widget or image. Choose “This tab” in Chrome’s sharing dialog. Click “Open preview” if Chrome requires another interaction. The floating preview updates while you use the original widget and requests capture at up to 120 fps. Closing it stops sharing. On Windows, use Chrome 156 or later. `python tests/pip.py --chrome --headed` checks the capture frame-rate setting, live pixel updates, capture cleanup, and nested video players in installed Chrome. `python tests/pip.py` exercises the video scenarios in bundled Chromium.

13. Resize the floating widget preview, close it, and reopen it from the same tab. Chrome can restore the position, and the extension keeps the new preview size for a fresh page. Resize and reopening are also exercised by `python tests/pip.py --chrome --headed`.

14. In the extension menu, enable “Auto PiP on this site” for an HTTPS site playing an eligible video. Switch to another tab. The extension uses Chrome's media-session callback, and Chrome may ask for permission. The preference is scoped to the site. `python tests/pip.py --chrome --headed --auto-only` checks the callback and native PiP window.
