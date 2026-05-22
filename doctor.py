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

if(config.get("repo_type") == "ros_ws"):
    # assume src folder holds all of the packages 
    repo_path = repo_path / "src"
    
    print("Processing ROS workspace at:", repo_path)
    
    # get all folders directly under the workspace src (filtering excludes)
    package_paths = [p for p in repo_path.iterdir() if p.is_dir() and p.name not in excludes]
    for p in package_paths:
        print("Found package:", p)
        
        # assume include folder under package name has all headers 
        include_path = p / "include" / p.name
        if include_path.exists():
            output_file_package = output_file.parent / f"{p.name}.puml"

            headers = []
            for pattern in config["include"]:
                for p in include_path.rglob(pattern.replace("**/", "")):
                    # check against excludes
                    if not any(p.match(ex) for ex in excludes):
                        headers.append(str(p))
 
            hpp2plantuml.CreatePlantUMLFile(headers, output_file=output_file_package)
            subprocess.run(["plantuml", "-dark", output_file_package])  # dark theme
        else:
            print("No include folder found for package:", p)
            
elif(config.get("repo_type") == "cpp"):
    print("Processing C++ repository at:", repo_path)
    
    headers = []
    for pattern in config["include"]:
        for p in repo_path.rglob(pattern):
            # check against excludes
            if not any(p.match(ex) for ex in excludes):
                headers.append(str(p))


# hpp2plantuml.CreatePlantUMLFile(headers, output_file=output_file)
# subprocess.run(["plantuml", "-dark", output_file])  # dark theme