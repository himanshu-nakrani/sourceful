import os
import re

for root, _, files in os.walk('app/components'):
    for file in files:
        if not file.endswith('.tsx'): continue
        with open(os.path.join(root, file)) as f:
            content = f.read()

        buttons = re.findall(r'<button([^>]*)>(.*?)</button>', content, re.DOTALL)
        for attrs, inner in buttons:
            if 'aria-label' not in attrs:
                # Strip all tags and {} react expressions
                stripped = re.sub(r'<[^>]+>', '', inner)
                stripped = re.sub(r'\{[^}]+\}', '', stripped).strip()
                if not stripped:
                    print(f"--- {file} ---")
                    # print(f"<button{attrs}>{inner}</button>")
                    print("Attrs:", attrs)
                    print("Inner:", inner)
