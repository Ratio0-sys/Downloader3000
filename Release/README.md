# Готовые сборки

Сюда складываются собранные файлы перед публикацией релиза.

**Сами сборки в репозиторий не попадают.** Причина простая: GitHub
не принимает файлы больше 100 МБ. Бинарники публикуются на странице
[Releases](https://github.com/Ratio0-sys/Downloader3000/releases),
а здесь версионируется только это описание.

## Как называются файлы

```text
Downloader3000-<версия>-<платформа>-<архитектура>.<расширение>
```

Например:

| Файл | Для чего |
| --- | --- |
| `Downloader3000-2.1.2-windows-x64.exe` | Windows 10 и новее |
| `Downloader3000-2.1.2-linux-x64.tar.gz` | Ubuntu 20.04+, Debian 11+ |
| `Downloader3000-2.1.2-macos-universal.zip` | macOS 11 и новее |
| `Downloader3000-2.1.2-android-arm64-v8a.apk` | большинство телефонов |
| `Downloader3000-2.1.2-android-armeabi-v7a.apk` | старые телефоны |

APK собирается отдельно под каждую архитектуру флагом `--split-per-abi`:
так телефон качает только своё, и файл выходит втрое меньше общего.

## Что уже внутри сборок

Пользователю не нужно ставить ничего дополнительно:

| Компонент | Зачем |
| --- | --- |
| Python и yt-dlp | сам движок скачивания |
| ffmpeg | склейка видео со звуком и конвертация в MP3 |
| QuickJS | решает JS-challenge YouTube, иначе часть форматов недоступна |

С версии 2.1.2 ffmpeg и QuickJS вшиты и в APK — на телефоне тоже
ничего доустанавливать не нужно.

Если в системе уже есть Node, Deno или Bun — программа возьмёт их:
они решают challenge быстрее встроенного QuickJS.

## Собрать всё

```bash
python tools/fetch_quickjs.py     # движок JS, качается один раз

flet pack src/main.py --name Downloader3000 --icon tools/app.ico     --distpath build_exe --add-data "src/assets;assets"     "--pyinstaller-build-args=--collect-all=imageio_ffmpeg" -y

flet build apk src --split-per-abi
flet build linux src
flet build macos src
```

Для Windows используется `flet pack`, а не `flet build windows`:
второй требует Visual Studio с компонентом C++, первый обходится
одним лишь Python.

Проще запустить [workflow](../.github/workflows/build.yml) на GitHub:
он собирает все платформы на нужных операционных системах и сам
создаёт черновик релиза.

## Контрольные суммы

Файл `SHA256SUMS.txt` создаётся при сборке релиза и прикладывается
к нему на GitHub — так суммы всегда соответствуют выложенным файлам.
Проверить скачанное:

```bash
sha256sum -c SHA256SUMS.txt        # Linux / macOS
Get-FileHash файл -Algorithm SHA256  # Windows PowerShell
```
