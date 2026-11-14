# Публикация Separate Window 1.4.0

Издатель: **Mycelium**. Поддержка: **qobuz43@gmail.com**.
Подготовлено по тому же принципу, что Mycelium Autofill: чистый ZIP расширения и отдельный комплект материалов RU/EN.

## Что загружать

1. **Пакет расширения:** `dist/separate-window-1.4.0.zip`. В корне лежит manifest.json; тестов, документации и исходных SVG в пакете нет.
2. **Иконка карточки:** `assets/icon128.png` — PNG 128×128, прозрачный отступ 16 px, знак 96×96.
3. **Скриншоты:** `assets/screenshot-01-select-ru.png`, `screenshot-02-window-ru.png`, `screenshot-03-app-ru.png`, `screenshot-04-widget-ru.png`. Для английской локали — соответствующие `-en.png`. Все 1280×800, PNG RGB. Первые три кадра — одна последовательность: открыть меню расширения, выбрать блок на странице, получить тот же ролик в отдельном окне. В исходной странице вокруг плеера размещены демонстрационные баннеры, рекомендации и подписка. Четвёртый кадр показывает перенос работающего калькулятора как пример использования с другими блоками. Меню показано фрагментами настоящего интерфейса: заголовок и нужная кнопка. Остальные снимки сделаны с работающим расширением на собственной демонстрационной странице. Рабочие заметки, рекламные лозунги и вымышленные приложения не используются.
4. **Малое промо:** `assets/promo-440x280.png` — иллюстрация переноса выбранного блока со страницы с баннерами в отдельное окно, с калькулятором как вторым примером. Это файл для замены картинки в поиске. Исходник и обоснование: [promo-tile.md](promo-tile.md). Дополнительное большое промо: `assets/promo-1400x560.png`.
5. **Тексты карточки:** `listing-ru.md` и `listing-en.md`.
6. **Privacy practices:** `privacy-fields.md`; инструкции проверки — `reviewer-instructions.md`.
7. **Privacy policy URL:** https://merlinrus.github.io/SeparateWindow/privacy.html
8. **Глобальный проморолик:** `videos/global-promo-1.4.0.mp4` — 24,47 секунды, английские подписи, оригинальная фоновая музыка. Загрузите на YouTube и вставьте ссылку в поле «Глобальный проморолик». Текст для загрузки и исходники описаны в [promo-video.md](promo-video.md).

Комплект `dist/chrome-web-store-materials-1.4.0.zip` содержит изображения, проморолик и тексты. **Его не нужно загружать как пакет расширения.**

Для поля **«Глобальные скриншоты»** подготовлен архив `dist/global-screenshots-1.4.0.zip`: `global-01-select.png`, `global-02-video.png`, `global-03-window.png`, `global-04-widget.png`. Это общий набор на английском с той же последовательностью действий. Отдельные архивы `dist/localized-ru-screenshots-1.4.0.zip` и `dist/localized-en-screenshots-1.4.0.zip` содержат по четыре изображения для соответствующих локализованных полей. Все файлы — RGB PNG 1280×800 без прозрачности. Не смешивайте старые и новые версии наборов.

## В кабинете Chrome Web Store

1. В аккаунте издателя Mycelium откройте существующую карточку Separate Window с ID `fhcafcdfknddjfgbbkhpglgamceiclcm`. ZIP Separate Window нельзя загружать обновлением Mycelium Autofill.
2. Загрузите `separate-window-1.4.0.zip`.
3. Укажите название Separate Window, категорию Productivity, язык RU, описания и поддержку qobuz43@gmail.com. Добавьте EN-локаль и её изображения/описание.
4. Загрузите иконку, четыре скриншота и промо. Укажите публичную политику и заполните поля по privacy-fields.md.
5. Вставьте reviewer-instructions.md. Доступы и тестовый аккаунт не требуются.
6. Выберите видимость и страны в своём кабинете. При необходимости начните с Unlisted и отложенной публикации.
7. Проверьте карточку и отправьте на рассмотрение.

Подготовка пакета не означает отправку, публикацию или одобрение обновления Google. Карточка продукта: https://chromewebstore.google.com/detail/separate-window/fhcafcdfknddjfgbbkhpglgamceiclcm . Текущая распакованная установка и магазинная версия могут иметь разные ID и отдельные локальные настройки.

## Английская карточка

В существующей карточке Separate Window откройте «Описание продукта» и в списке языка редактирования выберите English (en). Эта локаль уже включена в ZIP как `_locales/en/messages.json`; название и краткое описание берутся из пакета.

В поле полного описания вставьте всё содержимое `listing-description-en.txt`. В локализованные скриншоты английского языка добавьте `assets/screenshot-01-select-en.png`, `assets/screenshot-02-window-en.png`, `assets/screenshot-03-app-en.png`. Сохраните изменения английской локали вместе с обновлением текущего продукта.

Короткий текст обновления находится в `release-notes-ru.txt` и `release-notes-en.txt`. Английский текст можно добавить в конец полного английского описания под строкой “What's new in 1.4.0”.

Официальная инструкция: https://developer.chrome.com/docs/webstore/cws-dashboard-listing#localize_your_listing

## Воспроизводимая сборка

```powershell
python tools/build_icons.py
python tools/marketing_assets.py
python tests/smoke.py
python tools/package.py
python tools/verify_release.py
```

Для генерации нужны Python, Pillow и Playwright с Chromium. Само расширение не имеет внешних зависимостей и работает без сборщика. После любых изменений версии повторно соберите ZIP и обновите тексты карточки.

## Проверки

- MV3, упакованный JavaScript и строгая CSP без удалённого кода.
- Минимально используемые разрешения; избыточный activeTab удалён.
- PNG и favicon из одного SVG, читаемый знак в маленьких размерах.
- Настоящие RU/EN сценарии и корректные размеры материалов.
- Выбор iframe без передачи клика плееру; живой возврат во вкладку и восстановление после крестика.
- Политика отражает локальную обработку URL, селекторов и пользовательских снимков, а также собственную синхронизацию закладок Chrome.

## Источники требований

- https://developer.chrome.com/docs/webstore/images
- https://developer.chrome.com/docs/webstore/publish
- https://developer.chrome.com/docs/webstore/cws-dashboard-privacy
- https://developer.chrome.com/docs/webstore/program-policies/permissions
