import json
import os
import requests
import sys
import unicodedata

import vk_api

CONFIG = os.path.join(os.path.dirname(__file__), "../cred/vk_auth.json")
API_VER = "5.199"
SAVE_DIR = "vk_audio"
LIST_N = 30  # сколько треков показать в списке


def safe_name(text: str, maxlen=150):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    bad = r'\/:*?"<>|'
    return "".join(c for c in text if c not in bad).strip()[:maxlen]


def load_auth(path=CONFIG):
    try:
        with open(path) as f:
            cfg = json.load(f)
        return cfg["token"], cfg["ua"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        sys.exit(f"❌  Не удалось прочитать {path}")


def main():
    token, ua = load_auth()
    vk = vk_api.VkApi(token=token, api_version=API_VER).get_api()

    try:
        # id текущего пользователя
        my_id = vk.users.get()[0]["id"]
        print(f"🔍  Получаю аудио для пользователя ID {my_id} …")
    except vk_api.exceptions.ApiError as e:
        sys.exit(f"❌ VK API error {e}")

    # Получаем до 1000 треков (можно увеличить limit, если нужно)
    items = vk.audio.get(count=1000)["items"]
    if not items:
        sys.exit("❌  Список аудио пуст или доступ запрещён.")

    print(f"Найдено {len(items)} трек(ов). Показываю первые {LIST_N}:")
    print("-" * 80)
    for i, a in enumerate(items[:LIST_N], 1):
        dur = f"{a['duration'] // 60:02d}:{a['duration'] % 60:02d}"
        print(f"{i:>3} │ {a['artist']} – {a['title']} ({dur})")
    print("-" * 80)

    try:
        idx = int(input(f"Введите номер (1-{LIST_N}) для скачивания: "))
        assert 1 <= idx <= LIST_N
        track = items[idx - 1]
    except (ValueError, AssertionError):
        sys.exit("❌  Неверный выбор.")

    url = track.get("url")
    if not url:
        sys.exit("❌  У выбранного трека нет ссылки (возможно, доступ ограничен).")

    os.makedirs(SAVE_DIR, exist_ok=True)
    fname = os.path.join(
        SAVE_DIR,
        f"{safe_name(track['artist'])} - {safe_name(track['title'])}.mp3"
    )

    print(f"🔽  Скачиваю в «{fname}» …")
    try:
        with requests.get(url, headers={"User-Agent": ua}, stream=True, timeout=20) as r:
            r.raise_for_status()
            with open(fname, "wb") as f:
                for chunk in r.iter_content(4096):
                    f.write(chunk)
        print("✅  Готово!")
    except Exception as e:
        sys.exit(f"❌  Ошибка: {e}")


if __name__ == "__main__":
    main()
