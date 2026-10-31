"""Tiny KiCad s-expression parser (stdlib only)."""
import re

_tok = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text):
    stack = [[]]
    for m in _tok.finditer(text):
        t = m.group(0)
        if t == "(":
            stack.append([])
        elif t == ")":
            x = stack.pop()
            stack[-1].append(x)
        elif t.startswith('"'):
            stack[-1].append(("s", t[1:-1].replace('\\"', '"')))
        else:
            stack[-1].append(t)
    return stack[0][0]


def val(x):
    return x[1] if isinstance(x, tuple) else x


def find(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def first(node, name):
    r = find(node, name)
    return r[0] if r else None


def balanced(text, start):
    """Index just after the s-expression that starts at text[start] == '('."""
    depth, i, instr = 0, start, False
    while i < len(text):
        c = text[i]
        if instr:
            if c == "\\":
                i += 1
            elif c == '"':
                instr = False
        else:
            if c == '"':
                instr = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    raise ValueError("unbalanced s-expression")


def blocks(text, head):
    """All top-level-or-nested occurrences of '(<head>' as (start, end, text)."""
    out, pos = [], 0
    while True:
        i = text.find("(" + head, pos)
        if i < 0:
            return out
        j = balanced(text, i)
        out.append((i, j, text[i:j]))
        pos = j
