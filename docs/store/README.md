# Публикация Separate Window 1.3.1

Издатель: **Mycelium**. Поддержка: **qobuz43@gmail.com**.
Подготовлено по тому же принципу, что Mycelium Autofill: чистый ZIP расширения и отдельный комплект материалов RU/EN.

## Что загружать

1. **Пакет расширения:** `dist/separate-window-1.3.1.zip`. В корне лежит manifest.json; тестов, документации и исходных SVG в пакете нет.
2. **Иконка карточки:** `assets/icon128.png` — PNG 128×128, прозрачный отступ 16 px, знак 96×96.
3. **Скриншоты:** `assets/screenshot-01-select-ru.png`, `screenshot-02-window-ru.png`, `screenshot-03-app-ru.png`. Для английской локали — соответствующие `-en.png`. Все 1280×800, PNG RGB. Это работающий интерфейс на собственных демо-данных; третий кадр оформляет настоящий снимок popup как презентацию приложения.
4. **Малое промо:** `assets/promo-440x280.png`. Дополнительное большое промо: `assets/promo-1400x560.png`.
5. **Тексты карточки:** `listing-ru.md` и `listing-en.md`.
6. **Privacy practices:** `privacy-fields.md`; инструкции проверки — `reviewer-instructions.md`.
7. **Privacy policy URL:** https://merlinrus.github.io/SeparateWindow/privacy.html

Комплект `dist/chrome-web-store-materials-1.3.1.zip` содержит изображения и тексты. **Его не нужно загружать как пакет расширения.**

## В кабинете Chrome Web Store

1. В аккаунте издателя Mycelium откройте существующую карточку Separate Window с ID `fhcafcdfknddjfgbbkhpglgamceiclcm`. ZIP Separate Window нельзя загружать обновлением Mycelium Autofill.
2. Загрузите `separate-window-1.3.1.zip`.
3. Укажите название Separate Window, категорию Productivity, язык RU, описания и поддержку qobuz43@gmail.com. Добавьте EN-локаль и её изображения/описание.
4. Загрузите иконку, три скриншота и промо. Укажите публичную политику и заполните поля по privacy-fields.md.
5. Вставьте reviewer-instructions.md. Доступы и тестовый аккаунт не требуются.
6. Выберите видимость и страны в своём кабинете. При необходимости начните с Unlisted и отложенной публикации.
7. Проверьте карточку и отправьте на рассмотрение.

Подготовка пакета не означает отправку, публикацию или одобрение обновления Google. Карточка продукта: https://chromewebstore.google.com/detail/separate-window/fhcafcdfknddjfgbbkhpglgamceiclcm . Текущая распакованная установка и магазинная версия могут иметь разные ID и отдельные локальные настройки.

## Воспроизводимая сборка

```powershell
python tools/build_icons.py
python tools/store_assets.py
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
