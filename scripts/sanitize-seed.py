#!/usr/bin/env python3
"""
Sanitize a SQLite .dump output for D1 compatibility.

Replaces SQLite-specific constructs that D1 doesn't support:
1. unistr('...') → inline the actual string with proper escaping
2. Any other SQLite-extensions that D1 might not support
"""
import re
import sys


def replace_unistr(match):
    """Replace unistr('...') with the actual string value."""
    content = match.group(1)
    # Replace \uXXXX with actual unicode characters
    def replace_unicode(m):
        return chr(int(m.group(1), 16))
    content = re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode, content)
    # Escape single quotes for SQL
    content = content.replace("'", "''")
    # Escape backslashes (SQLite doesn't process them, but for safety)
    content = content.replace('\\', '\\\\')
    # Return as a regular SQL string literal
    return f"'{content}'"


def sanitize(line):
    """Sanitize a single line from a .dump file."""
    # Replace unistr('...') with regular string
    line = re.sub(r"unistr\('((?:[^'\\]|\\.)*)'\)", replace_unistr, line)

    # Replace \uXXXX inside regular strings too (shouldn't happen, but just in case)
    # Actually, \uXXXX in SQLite is only processed by unistr(), not in regular strings
    return line


def main():
    if len(sys.argv) > 1:
        input_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else input_path
    else:
        # Read from stdin, write to stdout
        for line in sys.stdin:
            sys.stdout.write(sanitize(line))
        return

    with open(input_path, 'r') as f:
        data = f.read()
    
    output = sanitize(data)
    
    with open(output_path, 'w') as f:
        f.write(output)
    
    print(f"✅ Sanitized: {output_path}")


def sanitize(data):
    lines = data.split('\n')
    result = []
    for line in lines:
        result.append(replace_unistr_in_line(line))
    return '\n'.join(result)


def replace_unistr_in_line(line):
    """Replace unistr('...') with the actual string value."""
    result = []
    pos = 0
    while pos < len(line):
        idx = line.find("unistr(", pos)
        if idx == -1:
            result.append(line[pos:])
            break
        result.append(line[pos:idx])
        # Find the matching closing paren
        start_quote = idx + len("unistr(")
        if start_quote >= len(line) or line[start_quote] != "'":
            result.append(line[idx:idx + len("unistr(")])
            pos = idx + len("unistr(")
            continue
        # Find the closing single-quote followed by )
        end = start_quote + 1
        while end < len(line):
            if line[end] == "'" and end + 1 < len(line) and line[end + 1] == ")":
                break
            if line[end] == "'" and end + 1 < len(line) and line[end + 1] == "'":
                # Escaped quote in string
                end += 2
                continue
            end += 1
        if end >= len(line):
            result.append(line[idx:])
            break
        content = line[start_quote + 1:end]
        pos = end + 2
        
        # Process the content
        processed = ""
        i = 0
        while i < len(content):
            if content[i] == "'" and i + 1 < len(content) and content[i + 1] == "'":
                processed += "'"
                i += 2
            elif content[i] == '\\' and i + 1 < len(content) and content[i + 1] == 'u':
                # Unicode escape
                hex_str = content[i+2:i+6]
                if len(hex_str) == 4 and all(c in '0123456789abcdefABCDEF' for c in hex_str):
                    processed += chr(int(hex_str, 16))
                    i += 6
                else:
                    processed += content[i]
                    i += 1
            else:
                processed += content[i]
                i += 1
        
        result.append(f"'{processed}'")
    
    return ''.join(result)


if __name__ == "__main__":
    main()
