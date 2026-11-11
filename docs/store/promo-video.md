# Глобальный проморолик

Файл: `videos/global-promo-1.4.0.mp4` — 24,47 секунды, 1280×720, 30 кадров/с, H.264, без звука. Английские подписи. Копия для загрузки находится в `dist/separate-window-global-promo-1.4.0.mp4`.

## Содержание

- 0:00 — название и логотип
- 0:02 — меню расширения и указатель на кнопке выбора
- 0:07 — выбор плеера на странице с демонстрационными баннерами
- 0:10 — то же видео в отдельном окне без интерфейса сайта
- 0:14 — выбор калькулятора, изменение количества и расчёт нового результата
- 0:22 — название и приглашение установить расширение

Действия сняты в Chromium с работающим расширением. Видео и калькулятор остаются в прежнем документе после переноса; запись проверяет это по идентификатору страницы. В калькуляторе количество меняется с 4 на 2, результат — с 1000 на 500. Используются собственные демонстрационные страницы и анимированный пейзаж; чужих фильмов, музыки и рекламных материалов в ролике нет.

## Размещение

Загрузите MP4 на YouTube с доступом «Открытый доступ» или «Доступ по ссылке», затем вставьте ссылку в поле **«Глобальный проморолик»** карточки Chrome Web Store. Сам MP4 в это поле не загружается. Локализованный проморолик может заменять глобальный для соответствующего языка.

Название для YouTube:

> Separate Window — video and widgets in their own windows

Описание для YouTube:

```text
Select a video or another page element and open it in its own window with Separate Window.

This demo shows selecting a player on a busy page, hiding the player interface and using a calculator after moving it to a separate window.

Install Separate Window:
https://chromewebstore.google.com/detail/separate-window/fhcafcdfknddjfgbbkhpglgamceiclcm

By Mycelium
Support: qobuz43@gmail.com
```

Инструкция магазина: https://developer.chrome.com/docs/webstore/cws-dashboard-listing

## Повторная сборка

Нужны Python, Pillow, Playwright и Chromium, используемые для галереи. FFmpeg устанавливается как отдельная зависимость инструмента, в расширение не входит.

```powershell
python -m pip install --target tools/.deps -r tools/requirements-video.txt
python tools/marketing_assets.py
python tools/promo_video.py
```

Монтаж задан в `tools/promo-story.html`. `tools/promo_video.py` записывает действия, компонует кадры и полностью декодирует готовый MP4 для проверки. Временные записи и контрольные кадры сохраняются в игнорируемой папке `tools/.artifacts/promo`. Для повторного монтажа без пересъёмки используйте `python tools/promo_video.py --reuse-recordings`.
