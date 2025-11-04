import json
import os
import re
import subprocess
import sys
import time
import webbrowser


APP_ID = "2685278"  # Kate Mobile
SCOPE = "audio,offline"
URL = (f"https://oauth.vk.com/authorize?"
       f"client_id={APP_ID}&display=page&scope={SCOPE}"
       f"&response_type=token&v=5.199&redirect_uri=https://oauth.vk.com/blank.html")

UA = ("KateMobileAndroid/80 lite-553 "
      "(Android 9; SDK 28; armeabi-v7a; Xiaomi Redmi 7A)")

VK_AUTH_JSON_CONFIG = '../cred/vk_auth.json'

def main():

    print("Откроется страница входа VK.\n"
          "Войдите, нажмите «Разрешить», затем в браузере:\n"
          "  ⌘+L  (фокус в адресную строку)\n"
          "  ⌘+C  (скопировать URL)\n"
          "Скрипт поймает токен из буфера обмена.")

    # macOS: откроет в деф-браузере
    webbrowser.open(URL)

    token_pattern = re.compile(r'access_token=([^&]+)')
    tok = None
    for _ in range(180):  # 3 минуты
        clip = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        m = token_pattern.search(clip)
        if m:
            tok = m.group(1)
            break
        time.sleep(1)

    if not tok:
        print("❌ Токен не найден. Проверьте, скопировали ли вы полный URL.")
        sys.exit(1)

    cfg_path = os.path.expanduser(VK_AUTH_JSON_CONFIG)
    with open(cfg_path, "w") as f:
        json.dump({"token": tok, "ua": UA}, f, indent=2)
    print("🎉 TOKEN:", tok)
    print("✅ Сохранено в", cfg_path)

if __name__ == "__main__":
    main()