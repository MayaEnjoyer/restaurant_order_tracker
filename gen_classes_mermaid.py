import ast, os, sys
from collections import defaultdict

root = sys.argv[1] if len(sys.argv) > 1 else "."

classes = {}
defined = set()

def dotted(module, name): return f"{module}.{name}" if module else name

for dirpath, _, files in os.walk(root):
    module = os.path.relpath(dirpath, root).replace(os.sep, ".")
    if module == ".": module = ""
    for f in files:
        if not f.endswith(".py"): continue
        path = os.path.join(dirpath, f)
        with open(path, "r", encoding="utf-8") as fh:
            try:
                tree = ast.parse(fh.read(), filename=path)
            except Exception:
                continue

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                name = dotted(module, node.name)
                defined.add(node.name)
                bases = set()
                for b in node.bases:
                    if isinstance(b, ast.Name):
                        bases.add(b.id)
                    elif isinstance(b, ast.Attribute):
                        bases.add(b.attr)
                attrs, methods = set(), set()
                for stmt in node.body:
                    if isinstance(stmt, ast.FunctionDef):
                        if not stmt.name.startswith("__"):
                            methods.add(stmt.name)
                        if stmt.name == "__init__":
                            for s in ast.walk(stmt):
                                if isinstance(s, ast.Assign):
                                    for t in s.targets:
                                        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                                            attrs.add(t.attr)
                                if isinstance(s, ast.AnnAssign):
                                    t = s.target
                                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                                        attrs.add(t.attr)
                    elif isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                        targets = [stmt.target] if isinstance(stmt, ast.AnnAssign) else stmt.targets
                        for t in targets:
                            if isinstance(t, ast.Name):
                                attrs.add(t.id)
                classes[name] = {"bases": bases, "attrs": attrs, "methods": methods}

print("classDiagram")
for cname, info in classes.items():
    safe = cname.replace(".", "_")
    print(f"class {safe} {{")
    for a in sorted(info["attrs"]):
        print(f"  {a}")
    for m in sorted(info["methods"]):
        print(f"  {m}()")
    print("}")
all_names = {k.split(".")[-1] for k in classes.keys()}
by_short = defaultdict(list)
for full in classes.keys():
    by_short[full.split(".")[-1]].append(full)

def map_name(n):
    if n in all_names and len(by_short[n]) == 1:
        return by_short[n][0].replace(".", "_")
    return n.replace(".", "_")

for child, info in classes.items():
    child_id = child.replace(".", "_")
    for b in info["bases"]:
        if b in all_names:
            print(f"{map_name(b)} <|-- {child_id}")
