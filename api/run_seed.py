import argparse
from seeds.seed_users import run as seed_users
from seeds.seed_master_data import run as seed_master


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=["users", "master", "all"])
    args = parser.parse_args()

    if args.target in ("users", "all"):
        seed_users()
    if args.target in ("master", "all"):
        seed_master()


if __name__ == "__main__":
    main()
