import os
import sys

# Works both as `python -m client.main` and when run directly (e.g. PyCharm's Run button).
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from client.game import Game
else:
    from .game import Game


def main():
    Game().run()


if __name__ == "__main__":
    main()
