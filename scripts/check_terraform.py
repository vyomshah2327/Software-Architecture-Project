"""Light static check of infra/terraform when the terraform program is not available.

It parses every .tf file and checks that each var.X, local.X, resource and data reference points at
something that exists. It does not replace `terraform validate`, which CI also runs.
"""
import glob
import pathlib
import re
import sys

import hcl2

root = pathlib.Path(__file__).parent.parent / "infra" / "terraform"
variables, local_names, resources, data_sources, outputs = set(), set(), set(), set(), set()
text = ""
for f in sorted(root.glob("*.tf")):
    text += f.read_text() + "\n"
    with open(f) as fh:
        doc = hcl2.load(fh)
    for v in doc.get("variable", []):
        variables.update(k.strip('"') for k in v)
    for block in doc.get("locals", []):
        local_names.update(k.strip('"') for k in block)
    for r in doc.get("resource", []):
        for rtype, named in r.items():
            resources.update(f"{rtype.strip(chr(34))}.{n.strip(chr(34))}" for n in named)
    for d in doc.get("data", []):
        for dtype, named in d.items():
            data_sources.update(f"{dtype.strip(chr(34))}.{n.strip(chr(34))}" for n in named)

errors = []
for name in sorted(set(re.findall(r"\bvar\.([a-z_0-9]+)", text))):
    if name not in variables:
        errors.append(f"undefined variable var.{name}")
for name in sorted(set(re.findall(r"\blocal\.([a-z_0-9]+)", text))):
    if name not in local_names:
        errors.append(f"undefined local local.{name}")
declared = resources | data_sources
for ref in sorted(set(re.findall(r"\b((?:ibm|random)_[a-z_]+\.[a-z_0-9]+)\b", text))):
    if ref not in declared:
        errors.append(f"reference to something that is not declared: {ref}")
unused = sorted(v for v in variables if f"var.{v}" not in text)
if unused:
    print("note: unused variables:", ", ".join(unused))
if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"terraform static check passed: {len(variables)} variables, {len(local_names)} locals, {len(resources)} resources")
