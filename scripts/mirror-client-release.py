"""Download one trusted GitHub release into the local LAN mirror."""

import argparse
import json
from pathlib import Path

from client_release import download_release


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--mirror-root", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    args = parser.parse_args()
    result = download_release(args.release_id, args.mirror_root, args.public_key)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
