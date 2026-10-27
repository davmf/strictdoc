import argparse
import pathlib

parser = argparse.ArgumentParser()
parser.add_argument("--scenario", required=True)
parser.add_argument("--replications", type=int, default=1)
args = parser.parse_args()

for index in range(args.replications):
    print(f"{args.scenario}: replication {index + 1}")  # noqa: T201
output_dir = pathlib.Path("out")
output_dir.mkdir(exist_ok=True)
(output_dir / f"{args.scenario}.svg").write_text(
    '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40">'
    '<rect width="40" height="40" fill="orange"/></svg>',
    encoding="utf-8",
)
