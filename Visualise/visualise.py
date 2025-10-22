from graphviz import Digraph
import os

project_path = ".NewMonika"  # путь к корню проекта

dot = Digraph(comment='NewMonika Project Structure')

folder_colors = {
    'monika': 'pink',
    'sayori': 'lightblue',
    'common': 'lightgrey',
    'NewMonika': 'white'
}

for root, dirs, files in os.walk(project_path):
    rel_path = os.path.relpath(root, project_path)
    if rel_path == ".":
        rel_path = "NewMonika"

    folder_name = os.path.basename(root)
    color = folder_colors.get(folder_name, 'white')

    dot.node(rel_path, rel_path, shape='folder', style='filled', fillcolor=color)

    for f in files:
        if f.endswith('.py'):
            node_id = os.path.join(rel_path, f)
            dot.node(node_id, f, shape='note')
            dot.edge(rel_path, node_id)

    for d in dirs:
        subfolder = os.path.join(rel_path, d)
        dot.edge(rel_path, subfolder)

dot.render("project_structure", format="png", cleanup=True)