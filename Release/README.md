# Готовые сборки

Сюда складываются собранные файлы перед публикацией релиза.

**Сами сборки в репозиторий не попадают.** Причина простая: GitHub
не принимает файлы больше 100 МБ, а один только APK весит около 156.
Бинарники публикуются на странице
[Releases](https://github.com/Ratio0-sys/Downloader3000/releases),
а здесь версионируется только это описание и файл контрольных сумм.

## Как называются файлы

```text
Downloader3000-<версия>-<платформа>-<архитектура>.<расширение>
```

Например:

| Файл | Для чего |
| --- | --- |
| `Downloader3000-2.1.0-windows-x64.zip` | Windows 10 и новее |
| `Downloader3000-2.1.0-linux-x64.tar.gz` | Ubuntu 20.04+, Debian 11+ |
| `Downloader3000-2.1.0-macos-universal.zip` | macOS 11 и новее |
| `Downloader3000-2.1.0-android-arm64-v8a.apk` | большинство телефонов |
| `Downloader3000-2.1.0-android-armeabi-v7a.apk` | старые телефоны |
| `Downloader3000-2.1.0-android-universal.apk` | все архитектуры в одном файле |

Универсальный APK втрое больше остальных, потому что содержит сразу три
архитектуры. Для релиза лучше выкладывать раздельные — они собираются
флагом `--split-per-abi`.

## Собрать всё

```bash
flet build windows src
flet build linux   src
flet build macos   src
flet build apk     src --split-per-abi
```

Проще запустить [workflow](../.github/workflows/build.yml) на GitHub:
он собирает все платформы на нужных операционных системах и сам
создаёт черновик релиза.

## Контрольные суммы

Рядом со сборками кладётся `SHA256SUMS.txt`, чтобы можно было проверить
целостность скачанного:

```bash
sha256sum -c SHA256SUMS.txt        # Linux / macOS
Get-FileHash файл -Algorithm SHA256  # Windows PowerShell
```
