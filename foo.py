from dotenv import load_dotenv

from core.file_man import get_mp3_bitrate
from pg import get_example

load_dotenv()


def main():
    example = get_example()
    brate = get_mp3_bitrate(example)
    print(f"Bitrate of '{example}': {brate} kbps")


if __name__ == '__main__':
    main()
