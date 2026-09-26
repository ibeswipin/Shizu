import re
import tokenize
import io


CLASS_RE = re.compile(
    r"^((?:[ \t]*@[^\n]*\n)*)class\s+(\w+)\s*\(([^()]*\bloader\.Module\b[^()]*)\)\s*:",
    re.MULTILINE,
)
LOADER_DECORATOR_RE = re.compile(r"^[ \t]*@loader\.(?:tds|module\([^\n]*\))[ \t]*\n", re.MULTILINE)
NAME_RE = re.compile(r"""["']name["']\s*:\s*["']([^"']+)["']""")


def _decorate_modules(code: str) -> str:
    name_match = NAME_RE.search(code)

    def repl(match):
        decorators = LOADER_DECORATOR_RE.sub("", match.group(1))
        module_name = name_match.group(1) if name_match else match.group(2)
        return (
            f'{decorators}@loader.module("{module_name}", "telethon", "")\n'
            f"class {match.group(2)}({match.group(3).strip()}):"
        )

    return CLASS_RE.sub(repl, code)


def transform(code: str) -> str:
    code = re.sub(r"from\s+hikkatl(\s+import|\s*\.)", r"from telethon\1", code)
    code = re.sub(r"import\s+hikkatl(\s+as\s+\w+)?", r"import telethon\1", code)
    code = re.sub(r"\bhikkatl\b", "telethon", code)

    code = _decorate_modules(code)

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
