# SmolSlimeConfigurator AFH <img src="icon.png" width="32" height="32" alt="SmolSlimeConfiguratorICON">

Pure Simple UI Configurator for SlimeVR Smol Slimes (Unofficial), adapted for StackedSmol AFH trackers and receivers.

<img width="1316" height="539" alt="newyes" src="https://github.com/user-attachments/assets/ce07f8ac-0857-42c3-9a02-f86d84e19fcc" />

## Features

- **AFH-first workflow** — includes safe AFH pairing controls for channel `100` / 2500 MHz.
- **Standard SlimeVR compatibility** — the SlimeVR server sees the receiver as a normal HID dongle; AFH changes are firmware-side and configurator-side only.
- **Automatic firmware updater** — downloads `.uf2` and `.hex` files from GitHub releases.
- **GitHub Actions artifact fallback** — if a firmware repo has no latest release, the configurator checks workflow artifacts, downloads a matching StackedSmol/Receiver zip, extracts it, finds the firmware file, and flashes it.
- **Smart device detection** — automatically recognizes whether the selected COM port is a tracker or receiver, switches the UI tab, and shows a human-readable status panel.
- **Smart/Raw console modes** — Smart mode summarizes noisy firmware logs for normal users; Raw console mode keeps the full developer log visible.
- **AFH diagnostics** — parses serial output into a debug state, detects repeated pairing requests without ACK, and can save a full debug log.
- **Custom firmware support** — flash your own `.uf2` or `.hex` files.
- **Cross-platform** — Windows, Linux, macOS, and Android-capable Python workflow.
- **Theme customization** — light/dark mode and accent color options.

## Download / install

### Option 1: download a ready-made executable

Use the project releases page when you want a packaged app:

- Windows: download `SmolSlimeConfigurator.exe`.
- Linux: download `SmolSlimeConfigurator-linux`, then run `chmod +x SmolSlimeConfigurator-linux`.
- macOS: download `SmolSlimeConfigurator-macos`, then allow it in Privacy & Security if Gatekeeper blocks the unsigned app.

### Option 2: run from Python source

```bash
python -m pip install customtkinter pyserial requests
python SmolSlimeConfiguratorV9.py
```

### Release binaries

GitHub releases publish two flavors per OS:

- `SmolSlimeConfigurator*` — normal console-capable build; useful when you want a terminal window for troubleshooting.
- `SmolSlimeConfigurator-GUI*` — windowed GUI build; cleaner for ordinary use.

### Option 3: build your own executable

Use Python 3.10+ and run:

```bash
python -m pip install customtkinter pyserial requests pyinstaller
pyinstaller --onefile --windowed --name SmolSlimeConfigurator SmolSlimeConfiguratorV9.py
```

The built file appears in `dist/`.

## Firmware downloads and artifact fallback

The configurator first queries the selected GitHub repository's `releases/latest` API and lists release assets ending in `.uf2` or `.hex`.

If `releases/latest` returns 404, returns an empty release list, or contains no firmware assets, the configurator falls back to the repository's GitHub Actions artifacts API:

1. Query `/actions/artifacts?per_page=100`.
2. Filter non-expired artifacts whose names look like StackedSmol, Stacked Smol, Receiver, or Dongle builds.
3. Download the artifact zip selected in the firmware picker.
4. Extract it into a temporary folder.
5. Find the first `.uf2` or `.hex` file inside.
6. Flash that extracted firmware file.

This is useful for AFH firmware projects that publish CI artifacts before creating formal GitHub releases.

## AFH recovery checklist

Use this when StackedSmol AFH pairing is unreliable or a tracker was paired to old receiver data:

1. Flash the receiver and trackers from matching AFH firmware builds.
2. Connect the receiver over USB.
3. Open the **Receiver** tab and press **Start AFH Pairing**.
4. Connect one tracker over USB.
5. Open the **Tracker** tab and press **Pair AFH**.
6. If the tracker still has stale pairing data, press **Clear+Pair AFH**, read the warning, and confirm only if you intentionally want to clear saved pairing data.
7. Verify the tracker appears in receiver **List** output and that the parsed debug state shows the expected Tracker ID.
8. Repeat with one tracker at a time.
9. Return to the receiver and press **⎋ Pairing Mode** to exit pairing mode.

## AFH buttons

- **Pair AFH** sends `afh_set_channel 100`, `afh_info`, then `pair`. It does not clear saved data.
- **Clear+Pair AFH** shows a warning and, if confirmed, sends `clear`, `afh_set_channel 100`, `afh_info`, then `pair`.
- **Run AFH Debug** sends `info`, `afh_info`, `list`, and `battery`.
- **Save Debug Log** saves the parsed AFH state and the console text to a `.txt` file.
- **Raw console / сырые логи** toggles between human-friendly Smart mode and full firmware log mode.
- **AFH Info** sends `afh_info`.
- **Force Channel 100** sends `afh_set_channel 100`.

If the console prints `Pairing request received` three or more times without `Paired`, the configurator adds this hint:

> Tracker requests are reaching a receiver, but no pair ACK was accepted yet. Keep receiver in Start AFH Pairing, and use Pair AFH on one tracker at a time.

## Standard SlimeVR server behavior

No SlimeVR server patch is required. With compatible AFH firmware, the receiver remains a standard HID dongle from the server's point of view.

---

# SmolSlimeConfigurator AFH — Русская версия

Простой неофициальный конфигуратор SlimeVR Smol Slimes, адаптированный для StackedSmol AFH трекеров и ресиверов.

## Возможности

- **AFH-процесс по умолчанию** — безопасные кнопки для AFH-пейринга на канале `100` / 2500 MHz.
- **Совместимость со стандартным SlimeVR** — сервер SlimeVR видит ресивер как обычный HID-донгл; изменения нужны только в прошивке и конфигураторе.
- **Автообновление прошивки** — загрузка `.uf2` и `.hex` из GitHub Releases.
- **Fallback на GitHub Actions artifacts** — если latest release отсутствует, конфигуратор ищет подходящий CI-артефакт StackedSmol/Receiver, скачивает zip, распаковывает его, находит прошивку и прошивает устройство.
- **Умное определение устройства** — автоматически понимает, что сейчас на COM-порту: трекер или ресивер, переключает вкладку и показывает понятную панель состояния.
- **Режим Smart/Raw console** — Smart mode превращает шумные firmware-логи в человеческие подсказки; Raw console показывает полный лог для отладки.
- **AFH-диагностика** — парсит serial-лог в состояние отладки, замечает повторные запросы пейринга без ACK и сохраняет debug log.
- **Своя прошивка** — можно выбрать локальный `.uf2` или `.hex` файл.

## Запуск из исходников

```bash
python -m pip install customtkinter pyserial requests
python SmolSlimeConfiguratorV9.py
```

## Готовые файлы в релизах

В GitHub Releases публикуются две версии под каждую ОС:

- `SmolSlimeConfigurator*` — обычная сборка с консолью, удобна для отладки.
- `SmolSlimeConfigurator-GUI*` — оконная GUI-сборка без лишней консоли, удобна для обычного пользователя.

## Как работает fallback на artifacts

Сначала конфигуратор запрашивает `releases/latest` выбранного GitHub-репозитория и ищет `.uf2` / `.hex` среди release assets.

Если latest release возвращает 404, список релизов пустой или в релизе нет прошивок, включается fallback:

1. Запрос `/actions/artifacts?per_page=100`.
2. Фильтр неистёкших артефактов с названиями StackedSmol, Stacked Smol, Receiver или Dongle.
3. Скачивание выбранного zip-артефакта.
4. Распаковка во временную папку.
5. Поиск первого `.uf2` или `.hex` внутри.
6. Прошивка найденного файла.

## Чеклист восстановления AFH-пейринга

1. Прошейте ресивер и все трекеры совместимыми AFH-сборками.
2. Подключите ресивер по USB.
3. На вкладке **Receiver** нажмите **Start AFH Pairing**.
4. Подключите один трекер по USB.
5. На вкладке **Tracker** нажмите **Pair AFH**.
6. Если у трекера остались старые данные пейринга, нажмите **Clear+Pair AFH**, прочитайте предупреждение и подтвердите только если действительно хотите очистить сохранённые данные.
7. Проверьте через **List**, что трекер появился у ресивера, и что в debug-состоянии виден правильный Tracker ID.
8. Повторяйте строго по одному трекеру за раз.
9. Вернитесь к ресиверу и нажмите **⎋ Pairing Mode**, чтобы выйти из режима пейринга.

## AFH-кнопки

- **Pair AFH** отправляет `afh_set_channel 100`, `afh_info`, затем `pair`. Сохранённые данные не очищаются.
- **Clear+Pair AFH** показывает предупреждение и после подтверждения отправляет `clear`, `afh_set_channel 100`, `afh_info`, затем `pair`.
- **Run AFH Debug** отправляет `info`, `afh_info`, `list`, `battery`.
- **Save Debug Log** сохраняет распарсенное AFH-состояние и текст консоли в `.txt`.
- **Raw console / сырые логи** переключает между понятным Smart mode и полными firmware-логами.
- **AFH Info** отправляет `afh_info`.
- **Force Channel 100** отправляет `afh_set_channel 100`.

Если трекер три или больше раз пишет `Pairing request received`, но нет `Paired`, конфигуратор покажет подсказку: запросы трекера доходят до ресивера, но ACK пейринга ещё не принят. Держите ресивер в **Start AFH Pairing** и используйте **Pair AFH** только для одного трекера за раз.

## SlimeVR server

Патчить SlimeVR server не нужно. С AFH-прошивкой ресивер остаётся обычным HID-донглом для сервера.
