# Об игровых данных

Этот репозиторий содержит **только код движка**. Игровых данных в нём нет и быть
не должно: `*.wad` внесён в [.gitignore](.gitignore).

- **DOOM**, его движок и файлы `doom.wad` / `doom2.wad` принадлежат
  id Software / ZeniMax. Их нельзя выкладывать в репозиторий и распространять.
- **Freedoom** (`freedoom1.wad`, `freedoom2.wad`) — отдельный свободный проект
  с совместимыми данными, распространяется по своей BSD-подобной лицензии:
  <https://freedoom.github.io/>. Его достаточно скачать самому и указать путь
  через `--wad` или переменную окружения `DOOMWAD`.

Формат WAD, номера типов вещей, имена лампов и раскладка кадров спрайтов —
общедоступные сведения о формате данных; код движка написан с нуля и
распространяется по [MIT](LICENSE).

---

# About game data

This repository contains **engine code only** — no game data, and `*.wad` is
gitignored. DOOM and its data files belong to id Software / ZeniMax.
[Freedoom](https://freedoom.github.io/) is a separate free-content project under
its own BSD-style license; download it yourself and point the engine at it with
`--wad`. The engine code itself is [MIT](LICENSE).
