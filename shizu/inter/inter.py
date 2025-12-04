import re


def transform(code: str) -> str:
    lines = code.split("\n")
    transformed_lines = []

    for line in lines:
        if re.match(r"^\s*from \.\.inline", line):
            continue
        transformed_lines.append(line)

    code = "\n".join(transformed_lines)

    code = re.sub(r"@loader\.tds", "@loader.module()", code)

    match = re.search(r"class\s+(\w+)\s*\(\s*loader\.Module\s*\)\s*:", code)
    if match:
        module_name = match.group(1)
        code = re.sub(
            r"@loader\.module\(\)",
            f'@loader.module("{module_name}", "telethon", "")',
            code,
        )

    return code
