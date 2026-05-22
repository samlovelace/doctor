import hpp2plantuml
from pathlib import Path
import sys
import subprocess
import yaml
import xml.etree.ElementTree as ET
import re

repo_path = Path(sys.argv[1])
output_file = sys.argv[2]

with open("doctor.yaml") as f:
    config = yaml.safe_load(f)

excludes = config.get("exclude", [])
out_dir = config.get("output", {}).get("dir", "docs/uml")
output_file = Path(out_dir) / output_file

if config.get("output", {}).get("location") == "there":
    output_file = repo_path / output_file

output_file.parent.mkdir(parents=True, exist_ok=True)

ros_config = config.get("ros", {})
publisher_patterns = ros_config.get("publishers", ["create_publisher"])
subscriber_patterns = ros_config.get("subscribers", ["create_subscription"])
service_patterns = ros_config.get("services", ["create_service"])
client_patterns = ros_config.get("clients", ["create_client"])


def parse_package_xml(package_path):
    xml_path = package_path / "package.xml"
    if not xml_path.exists():
        return None, []
    tree = ET.parse(xml_path)
    root = tree.getroot()
    name = root.findtext("name") or package_path.name
    depends = []
    for tag in ["depend", "build_depend", "exec_depend", "build_export_depend"]:
        for el in root.findall(tag):
            if el.text:
                depends.append(el.text.strip())
    return name, list(set(depends))


def parse_ros_interfaces(package_path, pub_patterns, sub_patterns, svc_patterns, cli_patterns):
    """
    Scan all source files in a package for publisher/subscriber/service/client calls.
    Returns dict with lists of topic strings found for each interface type.
    """
    interfaces = {
        "publishers": [],
        "subscribers": [],
        "services": [],
        "clients": [],
    }

    # scan both include and src directories
    scan_dirs = ["include", "src"]
    source_files = []
    for d in scan_dirs:
        scan_path = package_path / d
        if scan_path.exists():
            source_files += list(scan_path.rglob("*.hpp"))
            source_files += list(scan_path.rglob("*.h"))
            source_files += list(scan_path.rglob("*.cpp"))

    def extract_topic(line):
        """Try to extract the first string literal argument from a call."""
        match = re.search(r'["\']([^"\']+)["\']', line)
        return match.group(1) if match else None

    for f in source_files:
        try:
            content = f.read_text(errors="ignore")
        except Exception:
            continue

        for line in content.splitlines():
            stripped = line.strip()

            for pattern in pub_patterns:
                if pattern in stripped:
                    topic = extract_topic(stripped)
                    if topic:
                        interfaces["publishers"].append(topic)

            for pattern in sub_patterns:
                if pattern in stripped:
                    topic = extract_topic(stripped)
                    if topic:
                        interfaces["subscribers"].append(topic)

            for pattern in svc_patterns:
                if pattern in stripped:
                    topic = extract_topic(stripped)
                    if topic:
                        interfaces["services"].append(topic)

            for pattern in cli_patterns:
                if pattern in stripped:
                    topic = extract_topic(stripped)
                    if topic:
                        interfaces["clients"].append(topic)

    # deduplicate
    for key in interfaces:
        interfaces[key] = list(set(interfaces[key]))

    return interfaces


def generate_dependency_graph(packages, output_puml):
    package_names = set(packages.keys())
    lines = ["@startuml", "skinparam componentStyle rectangle", ""]
    for name in sorted(package_names):
        lines.append(f'component "{name}" as {name.replace("-", "_")}')
    lines.append("")
    for name, deps in sorted(packages.items()):
        for dep in sorted(deps):
            if dep in package_names:
                lines.append(f"{name.replace('-', '_')} --> {dep.replace('-', '_')}")
    lines.append("")
    lines.append("@enduml")
    output_puml.write_text("\n".join(lines))
    print(f"Generated dependency graph: {output_puml}")
    subprocess.run(["plantuml", "-dark", str(output_puml)])


def generate_node_graph(package_interfaces, output_puml):
    """
    Generate a PlantUML component diagram showing nodes connected via topics.
    Matches publishers in one package to subscribers in another.
    """
    lines = ["@startuml", "skinparam componentStyle rectangle", ""]

    # declare all packages as components
    for name in sorted(package_interfaces.keys()):
        lines.append(f'component "{name}" as {name.replace("-", "_")}')

    lines.append("")

    # collect all published topics and who publishes/subscribes
    topic_publishers = {}   # topic -> [package]
    topic_subscribers = {}  # topic -> [package]

    for name, interfaces in package_interfaces.items():
        for topic in interfaces["publishers"]:
            topic_publishers.setdefault(topic, []).append(name)
        for topic in interfaces["subscribers"]:
            topic_subscribers.setdefault(topic, []).append(name)

    # draw connections for topics that have both a publisher and subscriber
    drawn = set()
    for topic, pubs in topic_publishers.items():
        if topic in topic_subscribers:
            for pub in pubs:
                for sub in topic_subscribers[topic]:
                    key = (pub, sub, topic)
                    if key not in drawn:
                        pub_id = pub.replace("-", "_")
                        sub_id = sub.replace("-", "_")
                        lines.append(f'{pub_id} --> {sub_id} : "{topic}"')
                        drawn.add(key)

    lines.append("")
    lines.append("@enduml")
    output_puml.write_text("\n".join(lines))
    print(f"Generated node graph: {output_puml}")
    subprocess.run(["plantuml", "-dark", str(output_puml)])


if config.get("repo_type") == "ros_ws":
    src_path = repo_path / "src"
    print("Processing ROS workspace at:", src_path)

    package_paths = [p for p in src_path.iterdir() if p.is_dir() and p.name not in excludes]

    packages = {}
    package_interfaces = {}

    for p in package_paths:
        name, deps = parse_package_xml(p)
        if name:
            packages[name] = deps
            print(f"Found package: {name} ({len(deps)} deps)")

        # parse ROS interfaces
        interfaces = parse_ros_interfaces(
            p,
            publisher_patterns,
            subscriber_patterns,
            service_patterns,
            client_patterns,
        )
        package_interfaces[p.name] = interfaces
        print(f"  pubs: {interfaces['publishers']}")
        print(f"  subs: {interfaces['subscribers']}")

    # class diagrams per package
    for p in package_paths:
        include_path = p / "include" / p.name
        if include_path.exists():
            output_file_package = output_file.parent / f"{p.name}.puml"
            headers = []
            for pattern in config["include"]:
                for h in include_path.rglob(pattern.replace("**/", "")):
                    if not any(h.match(ex) for ex in excludes):
                        headers.append(str(h))
            if headers:
                hpp2plantuml.CreatePlantUMLFile(headers, output_file=str(output_file_package))
                subprocess.run(["plantuml", "-dark", str(output_file_package)])
            else:
                print(f"No headers found for package: {p.name}")
        else:
            print(f"No include folder found for package: {p.name}")

    if packages:
        dep_graph_puml = output_file.parent / "dependency_graph.puml"
        generate_dependency_graph(packages, dep_graph_puml)

    if package_interfaces:
        node_graph_puml = output_file.parent / "node_graph.puml"
        generate_node_graph(package_interfaces, node_graph_puml)

elif config.get("repo_type") == "cpp":
    print("Processing C++ repository at:", repo_path)
    headers = []
    for pattern in config["include"]:
        for p in repo_path.rglob(pattern):
            if not any(p.match(ex) for ex in excludes):
                headers.append(str(p))
    hpp2plantuml.CreatePlantUMLFile(headers, output_file=str(output_file))
    subprocess.run(["plantuml", "-dark", str(output_file)])