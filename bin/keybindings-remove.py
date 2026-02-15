#!/usr/bin/env python3
"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

Remove objects from a JSONC `keybindings.json` array by attribute match.

Usage:
    python3 bin/keybindings-remove.py <attribute> <search_string> < keybindings.json

Examples:
    # remove objects where the 'command' contains 'example'
    python3 bin/keybindings-remove.py command example < keybindings.json > keybindings-noexample.json

Behavior:
    - Removes matching objects and correctly handles trailing commas so the resulting JSONC remains syntactically valid.
    - Preserves comments and whitespace before the opening `[` and after the closing `]`, as well as comments inside and around each object.
    - Prints the modified content to stdout; does not write files in-place.
    - Set `KEYBINDINGS_REMOVE_DEBUG=1` to enable debug logging to stderr when parsing or matching issues occur.

Inputs / Outputs:
    stdin:  JSONC text (VS Code keybindings array)
    stdout: Modified JSONC text encoded as UTF-8

Exit codes:
    0   Success
    1   Usage / bad args
    2   File read/write or other runtime error
"""
import sys
import os
import re
import json

def usage(prog: str | None = None) -> None:
    """Print a concise usage message to stderr and exit with code 1."""
    if prog is None:
        prog = os.path.basename(sys.argv[0])
    msg = (
        f"Usage: {prog} <attribute> <search_string>\n\n"
        "Options:\n  -h, --help    Show this usage message and exit\n"
    )
    print(msg, file=sys.stderr)
    sys.exit(1)

def extract_preamble_postamble(text):
    """
    Find the top-level JSON array brackets, skipping any brackets that appear
    inside comments or strings in the preamble/postamble.
    """
    i = 0
    n = len(text)
    in_string = False
    string_char = ''
    esc = False
    in_line_comment = False
    in_block_comment = False
    start = -1
    
    # Find opening bracket, skipping comments and strings
    while i < n:
        ch = text[i]
        next2 = text[i:i+2] if i+2 <= n else ''
        
        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if next2 == '*/':
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == string_char:
                in_string = False
            i += 1
            continue
        
        # Not in string/comment
        if next2 == '//':
            in_line_comment = True
            i += 2
            continue
        if next2 == '/*':
            in_block_comment = True
            i += 2
            continue
        if ch == '"' or ch == "'":
            in_string = True
            string_char = ch
            i += 1
            continue
        if ch == '[':
            start = i
            break
        i += 1
    
    if start == -1:
        return '', '', text
    
    # Find matching closing bracket
    depth = 1
    i = start + 1
    in_string = False
    string_char = ''
    esc = False
    in_line_comment = False
    in_block_comment = False
    end = -1
    
    while i < n:
        ch = text[i]
        next2 = text[i:i+2] if i+2 <= n else ''
        
        if in_line_comment:
            if ch == '\n':
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if next2 == '*/':
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_string:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == string_char:
                in_string = False
            i += 1
            continue
        
        # Not in string/comment
        if next2 == '//':
            in_line_comment = True
            i += 2
            continue
        if next2 == '/*':
            in_block_comment = True
            i += 2
            continue
        if ch == '"' or ch == "'":
            in_string = True
            string_char = ch
            i += 1
            continue
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    
    if end == -1:
        return '', '', text
    
    preamble = text[:start]
    postamble = text[end+1:]
    array_text = text[start+1:end]  # exclude [ and ]
    return preamble, array_text, postamble

def split_units(array_text: str):
    # Each unit: (comments/whitespace before, object, trailing comma, whitespace)
    units = []
    lines = array_text.splitlines(keepends=True)
    i = 0
    n = len(lines)
    while i < n:
        comments = ''
        # Gather comments/whitespace before object
        while i < n and '{' not in lines[i]:
            comments += lines[i]
            i += 1
        if i >= n:
            break
        # Gather object
        obj_lines = ''
        depth = 0
        started = False
        while i < n:
            line = lines[i]
            if '{' in line:
                started = True
                depth += line.count('{')
            if started:
                obj_lines += line
            if '}' in line:
                depth -= line.count('}')
                if depth == 0:
                    i += 1
                    break
            i += 1
        # Gather trailing comma and whitespace
        trailing = ''
        while i < n and (lines[i].strip().startswith(',') or lines[i].strip() == '' or lines[i].strip().startswith('//') or lines[i].strip().startswith('/*')):
            trailing += lines[i]
            i += 1
        units.append((comments, obj_lines, trailing))
    return units

def strip_json_comments(text):
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return ''
        return s
    pattern = r'("(?:\\.|[^"\\])*"|//.*?$|/\*.*?\*/)'  # string or comment
    return re.sub(pattern, replacer, text, flags=re.DOTALL | re.MULTILINE)

def strip_trailing_commas(text):
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text

def should_remove(obj_text, attr, val):
    # non-greedy match to extract the JSON object body
    obj_match = re.search(r'\{[\s\S]*?\}', obj_text)
    if not obj_match:
        return False
    obj_str = obj_match.group(0)
    try:
        clean = strip_json_comments(obj_str)
        clean = strip_trailing_commas(clean)
        obj = json.loads(clean)
        # perform substring check (case-sensitive)
        attr_val = obj.get(attr, '')
        contains = val in str(attr_val)
        # debug output to stderr when KEYBINDINGS_REMOVE_DEBUG env var set
        if os.environ.get('KEYBINDINGS_REMOVE_DEBUG'):
            print('DEBUG: obj=', obj, file=sys.stderr)
            print(f"DEBUG: attr={attr!r} attr_val={attr_val!r} contains={contains}", file=sys.stderr)
        return contains
    except Exception:
        # Debug info when parsing fails
        if os.environ.get('KEYBINDINGS_REMOVE_DEBUG'):
            print(f"DEBUG: failed to parse object text: {obj_str}", file=sys.stderr)
        return False

def main():
    prog = os.path.basename(sys.argv[0])
    if any(arg in ('-h', '--help') for arg in sys.argv[1:]):
        usage(prog)
    if len(sys.argv) != 3:
        usage(prog)
    attr, val = sys.argv[1], sys.argv[2]
    raw = sys.stdin.read()
    preamble, array_text, postamble = extract_preamble_postamble(raw)
    units = split_units(array_text)
    # Output
    sys.stdout.write(preamble)
    sys.stdout.write('[')
    for comments, obj, trailing in units:
        if should_remove(obj, attr, val):
            continue
        sys.stdout.write(comments)
        sys.stdout.write(obj)
        sys.stdout.write(trailing)
    sys.stdout.write(']')
    sys.stdout.write(postamble)
    if not postamble.endswith('\n'):
        sys.stdout.write('\n')

if __name__ == "__main__":
    main()
