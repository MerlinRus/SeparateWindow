# Privacy practices — Separate Window 1.2.1

Publisher: Mycelium. Contact: qobuz43@gmail.com.

## Single purpose description

Open a user-selected web-page element in its own window and manage its display, reopening and return to a regular tab.

## Permissions justification

### tabs

Reads the current page URL/title and tab/window metadata needed to move the existing tab into a popup and return it. Records the latest URL while the tab is detached so it can be recovered as a normal tab after native window close. Also checks whether a temporary about:blank placeholder is still blank before removing it. It does not read the general browser history database.

### storage

Stores per-page CSS selectors and optional window geometry locally. Uses session storage for the original tab position, tab/window IDs and current URL while detached. No storage.sync or extension server is used.

### scripting

Injects packaged selection/isolation code into already-open pages when no active content-script listener is available. The user starts selection through the extension button, shortcut or context menu. No remote JavaScript is injected.

On an explicit “Always on top” click, packaged code also locates a ready video within the selected block and its descendant frames and toggles Chrome's built-in picture-in-picture API. Frame paths, video dimensions and temporary playback availability are processed in memory only. No video stream is captured or sent to the extension or developer.

### contextMenus

Adds “Separate Window — select element” to the browser's native context menu, to start the same user-driven element selection.

### bookmarks

Finds or creates the “Separate windows” bookmark folder and adds a link to the selected element only when the user presses the bookmark button. The folder search is by its title; the extension does not enumerate bookmark contents for analytics or transmit bookmarks.

### Host access: <all_urls>

Users select elements on arbitrary websites and may reopen saved selections on later visits. Content scripts inspect the DOM to identify the chosen element, temporarily isolate it with CSS and display a saved-selection button. Broad host access also permits user-requested captureVisibleTab screenshots. No request interception or general history API is used. File URLs work only if the user separately enables file access in Chrome. Restricted Chrome pages remain inaccessible.

The redundant activeTab permission was removed. Real Chromium tests verify selection, screenshots and tab recovery without it.

## Remote code

Select **No, I am not using remote code**. All executable extension code is inside the ZIP. No eval, remote scripts, external fonts or remote executable modules are used. The original website runs its own code in its own page context.

## Data usage

Accurately disclose the locally processed data relevant to the dashboard categories:

- **Web history:** current and saved page URLs used for selection links, per-page settings and tab recovery. The extension does not read Chrome's history database.
- **Website content:** DOM structure/CSS selector for the chosen element, page title and user-requested screenshot pixels.
- **User activity:** user choices such as selecting an element and saving window geometry. Pointer events during selection are processed in memory; no activity log or behavioral analytics is created.

Do not claim that the extension handles no user data merely because processing is local. Screenshots or chosen content may contain sensitive information displayed by a website; there is no dedicated extraction of credentials, financial, medical or private-message data.

Data-use certifications should reflect the implementation: data is not sold or transferred for advertising, used outside the stated window-management purpose, or used for creditworthiness/lending. Read the exact certification text in the dashboard before submitting.

## Privacy policy URL

https://merlinrus.github.io/SeparateWindow/privacy.html

Public RU/EN HTML, no login required. The extension's Help and Privacy links are user-triggered navigation, not background uploads.

## References

- https://developer.chrome.com/docs/webstore/cws-dashboard-privacy
- https://developer.chrome.com/docs/webstore/program-policies/permissions
- Runtime evidence: manifest.json, background.js, content.js, popup.js.
