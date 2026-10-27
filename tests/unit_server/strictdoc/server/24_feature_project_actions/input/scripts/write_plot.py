import argparse
import pathlib

parser = argparse.ArgumentParser()
parser.add_argument("--name", required=True)
parser.add_argument("--count", type=int, default=1)
args = parser.parse_args()

output_dir = pathlib.Path("out")
output_dir.mkdir(exist_ok=True)
for index in range(args.count):
    print(f"line {index}")  # noqa: T201
(output_dir / f"{args.name}.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8"
)
print("done")  # noqa: T201
