import os
import re

for root, _, files in os.walk('app/components'):
    for file in files:
        if not file.endswith('.tsx'): continue
        with open(os.path.join(root, file)) as f:
            content = f.read()

        # simple parsing, assuming tags are balanced inside button text
        buttons = re.findall(r'<button.*?</button>', content, re.DOTALL)
        for b in buttons:
            if 'aria-label' not in b:
                # check if it contains text, strip HTML tags
                inner = re.sub(r'<[^>]+>', '', b)
                inner = re.sub(r'\{[^}]+\}', '', inner) # remove react interpolations like {message.id} just in case
                if not inner.strip():
                    print(f"--- {file} ---")
                    print(b)
