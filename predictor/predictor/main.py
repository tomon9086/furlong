"""予想プログラムエントリーポイント"""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


def main() -> None:
    # TODO: 予想処理を実装する
    pass


if __name__ == "__main__":
    main()
