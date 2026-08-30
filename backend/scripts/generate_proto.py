import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROTO_ROOT = ROOT / "proto"
OUTPUT_ROOT = ROOT / "src"
PROTO_FILES = sorted(PROTO_ROOT.glob("**/*.proto"))


def main() -> None:
    if not PROTO_FILES:
        raise SystemExit("No protobuf files found")

    command = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{PROTO_ROOT}",
        f"--python_out={OUTPUT_ROOT}",
        f"--pyi_out={OUTPUT_ROOT}",
        f"--grpc_python_out={OUTPUT_ROOT}",
        *(str(path) for path in PROTO_FILES),
    ]
    subprocess.run(command, check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
