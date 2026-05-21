import hpp2plantuml
from pathlib import Path
import sys
import subprocess
import yaml

repo_path = Path(sys.argv[1])
output_file = sys.argv[2]

with open("doctor.yaml") as f:
    config = yaml.safe_load(f)

excludes = config.get("exclude", [])

out_dir = config.get("output_dir", "docs/uml")
output_file = Path(out_dir) / output_file

if(config.get("output", {}).get("location") == "there"):
    output_file = repo_path / output_file

output_file.parent.mkdir(parents=True, exist_ok=True)

headers = []
for pattern in config["include"]:
    for p in repo_path.rglob(pattern.replace("**/", "")):
        # check against excludes
        if not any(p.match(ex) for ex in excludes):
            headers.append(str(p))

hpp2plantuml.CreatePlantUMLFile(headers, output_file=output_file)
subprocess.run(["plantuml", "-dark", output_file])  # dark theme