# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2016-2021 Scille SAS

import shutil
import argparse
import subprocess
from pathlib import Path


BUILD_DIR = Path("build").resolve()


def run(cmd, **kwargs):
    print(f">>> {cmd}")
    ret = subprocess.run(cmd, shell=True, **kwargs)
    assert ret.returncode == 0, ret.returncode
    return ret


def main(program_source: Path, output: Path, force: bool):
    if output.exists():
        if force:
            shutil.rmtree(output)
        else:
            raise SystemExit(f"{output} already exists")
    output.mkdir(parents=True)

    # Retrieve program version
    global_dict = {}
    exec((program_source / "parsec/_version.py").read_text(), global_dict)
    program_version = global_dict.get("__version__")
    print(f"### Detected Parsec version {program_version} ###")

    # Copy sources in an isolated dir (snap doesn't support using a snapcraft.yml parent folder as source)
    src_dir = output / "src"
    print(f"### Copy Parsec sources to {src_dir} ###")

    src_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(program_source / "parsec", src_dir / "parsec")
    shutil.copy(program_source / "README.rst", src_dir / "README.rst")
    shutil.copy(program_source / "HISTORY.rst", src_dir / "HISTORY.rst")

    # Ugly hack given snapcraft doesn't support extra requirements...
    setup_py_src = (program_source / "setup.py").read_text()
    patched_setup_py_src = setup_py_src.replace(
        "install_requires=requirements",
        "install_requires=requirements + extra_requirements['core']",
    )
    assert patched_setup_py_src != setup_py_src
    (src_dir / "setup.py").write_text(setup_py_src)

    shutil.copytree(program_source / "packaging/snap/bin", output / "bin")

    # Copy snapcraft.yaml and set version info
    snapcraft_yaml_src = (program_source / "packaging/snap/snapcraft.yaml").read_text()
    patched_snapcraft_yaml_src = snapcraft_yaml_src.format(
        program_version=program_version, program_src=src_dir
    )
    # Fun facts about "snapcraft.yaml":
    # - it cannot be named "snapcraft.yml"
    # - it must be stored in a "snap" folder
    # - there is no "--config" in snapcraft to avoid having to build a specific
    #   folder structure and use cd before running a command...
    snapcraft_yaml = output / "snap/snapcraft.yaml"
    snapcraft_yaml.parent.mkdir(parents=True)
    snapcraft_yaml.write_text(patched_snapcraft_yaml_src)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate build dir for Snap with parsec sources, ready to run snapcraft on it"
    )
    parser.add_argument("--program-source")
    parser.add_argument("--output")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(Path(args.program_source).absolute(), Path(args.output).absolute(), args.force)