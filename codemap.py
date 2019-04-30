from __future__ import print_function
import click
import re
import os
from collections import defaultdict
import graphviz
import inspect
from types import FunctionType
from tqdm import tqdm
import sys
import editdistance
import warnings
import json

warnings.filterwarnings("ignore")

if sys.version_info > (3, 0):
    from importlib.machinery import SourceFileLoader
else:
    import imp

"""
# TODO:

Need functionality for inspecting a single function.
'' overlap of functions
'' overlap of files
 Separate by files
 Separate by functions
'' 
"""


def get_files(path):
    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            for name in files:
                yield os.path.join(root, name)
    else:
        yield path


def extract_wrapped(decorated):
    if hasattr(decorated, "__closure__") and \
            decorated.__closure__ is not None:
        closure = (c.cell_contents for c in decorated.__closure__)
        return next((c for c in closure if isinstance(c, FunctionType)),
                    None)
    else:
        return decorated


def get_functions(fn):
    module_name = fn[:-3].replace("/", ".")
    if module_name[0:2] == "..":
        module_name = module_name[2:]

    try:
        if sys.version_info > (3, 0):
            m = SourceFileLoader(module_name, fn).load_module()
        else:
            m = imp.load_source(module_name, fn)
        # print("loaded {}".format(module_name))
    except Exception as e:
        # print(e)
        # print("could not load {}".format(fn))
        return []

    file_str = open(fn).read()
    f_list = dir(m)

    def check_f(f_str):
        matches = [m.start() for m in re.finditer(f_str + '\(', file_str)]
        is_func = any("def" in file_str[m - 4: m] for m in matches)
        is_class = any("class" in file_str[m - 6: m] for m in matches)
        return is_func, is_class

    desc = []
    for f in f_list:
        is_func, is_class = check_f(f)
        if is_func or is_class:
            try:
                extracted_f = extract_wrapped(m.__dict__[f])
                desc.append(
                    {"name": f,
                     "text": inspect.getsource(extracted_f),
                     "is_class": is_class})
            except (TypeError, IOError) as e:
                if hasattr(m.__dict__[f], "callback"):
                    extracted_f = extract_wrapped(m.__dict__[f].callback)
                    desc.append({"name": f,
                                 "text": inspect.getsource(extracted_f),
                                 "is_class": is_class})
    return desc


def make_maps(filename, exclude):
    try:
        definition_map = json.load(open(".defs.codemap"))
        file_map = json.load(open(".files.codemap"))
        print("using .files.codemap and .defs.codemap found locally")
        return definition_map, file_map
    except IOError:
        pass
    files = [f for f in get_files(filename) if f[-3:] == ".py" and
             f[-4] != "_" and exclude not in f]
    definition_map = {}
    file_map = {}
    for f in tqdm(files, leave=False, desc="Parsing Files"):
        funcs = get_functions(f)
        file_map[f] = funcs
        for fn in funcs:
            definition_map[fn["name"]] = {"file": f, "text": fn["text"],
                                          "is_class": fn["is_class"]}

    return definition_map, file_map


def follow_deps(deps, starting_point, degrees=1):
    filtered_deps = defaultdict(lambda: set())

    def r(sp, deg):
        dependents = deps[sp]
        if deg > 0:
            for d in dependents:
                r(d, deg - 1)
        filtered_deps.update({sp: dependents})
        return filtered_deps

    r(starting_point, degrees - 1)

    return filtered_deps


def flatten_deps(deps):
    flat_deps = []
    iterable = deps.values() if isinstance(deps, dict) else deps
    for dep in iterable:
        flat_deps.extend(dep)
    return flat_deps


def filter_deps(deps, inspect_function, def_map, degrees):
    if inspect_function is not None:
        print("inspecting")
        new_deps = {}
        ins_fs = inspect_function.split(',')
        intersecting_deps = set(flatten_deps(deps))
        for f in ins_fs:
            d_0 = follow_deps(deps, f, degrees=degrees)
            intersecting_deps = intersecting_deps.intersection(
                set(flatten_deps(d_0))
            )
            new_deps.update(d_0)

        if len(ins_fs) > 1:
            for d in intersecting_deps:
                def_map[d]["intersection"] = True
        return new_deps


def get_function_dependencies(definition_map, file_map):

    unique_fn = set()
    unique_fn_size = 0
    try:
        dependencies = json.load(open(".deps.codemap"))
        callers = json.load(open(".callers.codemap"))
        print("using .defs.codemap and .callers.codemap found locally")
        return dependencies, callers
    except IOError:
        dependencies = defaultdict(lambda: set())
        callers = defaultdict(lambda: set())
    for fn_name in tqdm(definition_map.keys(), leave=False, desc="Building "
                                                                 "Dependency Maps"):

        func = definition_map[fn_name]
        new_str = func["text"]
        file_name = func["file"]
        unique_fn.add(file_name)
        if len(unique_fn) > unique_fn_size:
            unique_fn_size += 1

        file_text = open(file_name).read()

        for k in definition_map.keys():
            if k in new_str:
                try:
                    idx = new_str.index(k)
                    not_lit_a = (new_str[0:idx].count("'") % 2 == 0 and
                                 new_str[idx:].count("'") % 2 == 0) or \
                                new_str[0:idx].count("'") == 0 or \
                                new_str[idx:].count("'") == 0
                    not_lit_b = (new_str[0:idx].count('"') % 2 == 0 and
                                 new_str[idx:].count('"') % 2 == 0) or \
                                new_str[idx:].count('"') == 0 or \
                                new_str[0:idx].count('"') == 0

                    # find if in comment
                    idx_0 = idx
                    while new_str[idx_0] != '#' and new_str[idx_0] != '\n' and \
                            idx_0 > 0:
                        idx_0 -= 1

                    is_not_comment = new_str[idx_0] != "#"

                    module_parts = definition_map[k]["file"][:-3].replace("/",
                                                                          ".")
                    if module_parts[0:2] == "..":
                        module_parts = module_parts[2:].split(".")

                    first_class = file_text.index("\nclass") if \
                        "\nclass" in file_text else len(file_text)
                    first_func = file_text.index("\ndef") if \
                        "\ndef" in file_text else len(file_text)

                    imports_end = min(first_func, first_class)
                    is_imported = any(p in file_text[:imports_end]
                                      for p in [module_parts[-1]]) or \
                                  re.search(u'[\s|,]' + k + u'[\s|,]',
                                            file_text[:imports_end]) is not None
                    is_local = k in [o["name"] for o in file_map[file_name]]
                    if not_lit_a and not_lit_b and k not in file_map[file_name] \
                           and not new_str[idx - 1].isalnum() \
                            and not new_str[idx + len(k)].isalnum() and \
                            not new_str[idx + len(k)] == "_" and \
                            not new_str[idx - 1] == "_" and \
                            is_not_comment and (is_imported or is_local) and fn_name != k:
                        callers[k].add(fn_name)
                        dependencies[fn_name].add(k)
                except:
                    pass

    return dependencies, callers


def graph_from_deps(dependencies, definition_map, file_map, reverse=False,
                    update_graph=None, inspect_function=None,
                    highlight_files=None, show_files=None):
    dot = graphviz.Digraph() if update_graph is None else update_graph

    print("{} nodes".format(len(dependencies)))
    print("{} edges".format(sum(len(d) for d in dependencies)))
    for f in tqdm(dependencies.keys() + flatten_deps(dependencies), desc="Adding Nodes", leave=False):
        func = definition_map[f]
        file_name = func["file"]
        shape = "rectangle" if func["is_class"] else 'ellipse'
        c = lambda x: "lightblue" if "intersection" in func else x

        if inspect_function is not None and f == inspect_function:
            dot.attr('node', shape=shape, style='filled', color=c('green'))
        else:
            dot.attr('node', shape=shape, style='filled',
                     color=c('lightgrey'))

        cluster_name = "shared_functions" if "intersection" in func and \
                                             not show_files else file_name
        with dot.subgraph(name="cluster_" + cluster_name) as cu:
            if highlight_files is not None and file_name in highlight_files or cluster_name == "shared_functions" or show_files:
                cu.node(f)
            else:
                dot.node(f)

    for fn_name in tqdm(dependencies.keys(), desc="Adding Edges", leave=False):
        func = definition_map[fn_name]
        file_name = func["file"]
        deps = dependencies[fn_name]

        for k in deps:
            cluster_name = "shared_functions" if "intersection" in definition_map[k] and not show_files else definition_map[k]["file"]
            with dot.subgraph(name="cluster_" + cluster_name) as cu:
                cu.attr(label=cluster_name)
                cu.attr(color='lightblue', style='filled')
                shape = "rectangle" if definition_map[k][
                    "is_class"] else \
                    'ellipse'
                c = lambda x: "lightblue" if "intersection" in definition_map[k] else x

                if inspect_function is not None and k == inspect_function:
                    dot.attr('node', shape=shape,
                             style='filled', color=c('green'))
                else:
                    dot.attr('node', shape=shape,
                             style='filled', color=c('lightgrey'))

                if definition_map[k]["file"] == file_name and highlight_files is not None and \
                        (definition_map[k]["file"] in highlight_files or cluster_name == "shared_functions") or show_files:
                    if reverse:
                        dot.edge(k, fn_name)
                    else:
                        dot.edge(fn_name, k)
                else:
                    if reverse:
                        dot.edge(k, fn_name)
                    else:
                        dot.edge(fn_name, k)
    return dot


@click.command()
@click.option("--exclude")
@click.option("--inspect-function", default=None)
@click.option("--highlight-files")
@click.option("--show-files", is_flag=True)
@click.option("--show-dependencies", is_flag=True)
@click.option("--cache-result", is_flag=True)
@click.option("--degrees", default=5)
@click.argument("filename")
def analyze_deps(filename, exclude, inspect_function, highlight_files,
                 show_files, show_dependencies, cache_result, degrees):
    sys.path.append(os.getcwd())
    if highlight_files is not None:
        highlight_files = highlight_files.split(",")

    def_map, file_map = make_maps(filename, exclude)

    dependencies, callers = get_function_dependencies(def_map, file_map)

    if highlight_files is not None:
        ins_fns = highlight_files
        intersecting_deps = set(flatten_deps(dependencies))
        new_deps = set()
        for fn in ins_fns:
            functions = [o["name"] for o in file_map[fn]]
            new_deps = set()
            for f in functions:
                d_0 = follow_deps(dependencies, f, degrees=degrees)
                new_deps = new_deps.union(set(flatten_deps(d_0)))

            intersecting_deps = intersecting_deps.intersection(new_deps)

        if len(ins_fns) > 1:
            for d in intersecting_deps:
                def_map[d]["intersection"] = True

    if inspect_function is not None:
        if inspect_function not in def_map:
            min_d = 100000
            best_k = inspect_function
            for k in def_map.keys():
                d = editdistance.eval(inspect_function, k)
                if min_d > d:
                    min_d = d
                    best_k = k
            print("{} not found as a function... returning results for {}"
                  .format(inspect_function, best_k))
            inspect_function = best_k
        dot = graph_from_deps(filter_deps(dependencies, inspect_function, def_map,
                                          degrees), def_map, file_map,
                               reverse=show_dependencies,
                              inspect_function=inspect_function,
                              highlight_files=highlight_files,
                              show_files=show_files)
        dot = graph_from_deps(filter_deps(callers, inspect_function, def_map,
                                           degrees), def_map, file_map,
                               reverse=not show_dependencies, update_graph=dot,
                               inspect_function=inspect_function,
                               highlight_files=highlight_files,
                               show_files=show_files)
    else:
        dot = graph_from_deps(dependencies, def_map, file_map,
                              reverse=show_dependencies,
                              highlight_files=highlight_files,
                              show_files=show_files)

    print('now_drawin')
    dot.render(view=True)
    if cache_result:
        for k in dependencies.keys():
            dependencies[k] = list(dependencies[k])
        for k in callers.keys():
            callers[k] = list(callers[k])
        json.dump(def_map, open(".defs.codemap", "w+"))
        json.dump(file_map, open(".files.codemap", "w+"))
        json.dump(dict(dependencies), open(".deps.codemap", "w+"))
        json.dump(dict(callers), open(".callers.codemap", "w+"))


if __name__ == '__main__':
    analyze_deps()
