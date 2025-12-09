import re
import tokenize
import io


def transform(code: str) -> str:
    lines = code.split("\n")
    transformed_lines = []

    for line in lines:
        if re.match(r"^\s*from \.\.inline", line):
            continue
        transformed_lines.append(line)

    code = "\n".join(transformed_lines)
    code = re.sub(r"from\s+hikkatl(\s+import|\s*\.)", r"from telethon\1", code)
    code = re.sub(r"import\s+hikkatl(\s+as\s+\w+)?", r"import telethon\1", code)
    code = re.sub(r"\bhikkatl\b", "telethon", code)

    code = re.sub(r"@loader\.tds", "@loader.module()", code)

    match = re.search(r"class\s+(\w+)\s*\(\s*loader\.Module\s*\)\s*:", code)
    if match:
        module_name = match.group(1)
        code = re.sub(
            r"@loader\.module\(\)",
            f'@loader.module("{module_name}", "telethon", "")',
            code,
        )

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline)) # type: ignore[reportUnknownReturnType]
        lines_list = code.split("\n")
        string_regions = []
        
        for token in tokens:
            token_type, _, (start_line, start_col), (end_line, end_col), _ = token
            
            if token_type == tokenize.STRING:
                start_pos = sum(len(lines_list[i]) + 1 for i in range(start_line - 1)) + start_col
                end_pos = sum(len(lines_list[i]) + 1 for i in range(end_line - 1)) + end_col
                string_regions.append((start_pos, end_pos))
        
        if string_regions:
            result_parts = []
            last_pos = 0
            
            for start_pos, end_pos in string_regions:
                result_parts.append(code[last_pos:start_pos])
                string_content = code[start_pos:end_pos]
                
                quote_char = string_content[0] if string_content else "'"
                attr_quote = '"' if quote_char in ("'", "'''") else "'"
                
                def replace_emoji_tag(match, quote=attr_quote):
                    document_id = match.group(1)
                    emoji_content = match.group(2)
                    return f"<tg-emoji emoji-id={quote}{document_id}{quote}>{emoji_content}</tg-emoji>"
                
                transformed = re.sub(
                    r'<emoji\s+document_id=(\d+)>([^<]*?)</emoji>',
                    replace_emoji_tag,
                    string_content
                )
                result_parts.append(transformed)
                last_pos = end_pos
            
            result_parts.append(code[last_pos:])
            code = "".join(result_parts)
        else:
            def replace_emoji_tag_fallback(match):
                document_id = match.group(1)
                emoji_content = match.group(2)
                return f'<tg-emoji emoji-id="{document_id}">{emoji_content}</tg-emoji>'
            
            code = re.sub(
                r'<emoji\s+document_id=(\d+)>([^<]*?)</emoji>',
                replace_emoji_tag_fallback,
                code
            )
            
    except (tokenize.TokenError, SyntaxError):
        def replace_emoji_tag_fallback(match):
            document_id = match.group(1)
            emoji_content = match.group(2)
            return f'<tg-emoji emoji-id="{document_id}">{emoji_content}</tg-emoji>'
        
        code = re.sub(
            r'<emoji\s+document_id=(\d+)>([^<]*?)</emoji>',
            replace_emoji_tag_fallback,
            code
        )

    return code
