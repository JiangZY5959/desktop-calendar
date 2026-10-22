# -*- coding: utf-8 -*-
"""静态检查：模块内是否存在“用了没导入的别名”（如 weather.py 的 L.WEEK_CN）。

这类错误只在特定数据路径下才触发（天气拿到真实数据才走到那行），
平时跑不出来，却会让进程直接 abort——所以必须静态兜住。

用法: python3 lint_aliases.py
"""
import ast
import os
import sys

BUILTINS = set(dir(__builtins__)) if isinstance(__builtins__, dict) is False else set(__builtins__)
BUILTINS |= {
    'True', 'False', 'None', 'self', 'cls', 'super', 'Exception', 'BaseException',
    'print', 'len', 'range', 'int', 'str', 'float', 'list', 'dict', 'set', 'tuple',
    'open', 'isinstance', 'getattr', 'setattr', 'hasattr', 'callable', 'sorted',
    'enumerate', 'zip', 'map', 'filter', 'min', 'max', 'abs', 'round', 'sum', 'any',
    'all', 'repr', 'type', 'id', 'iter', 'next', 'bytes', 'object', 'property',
    'staticmethod', 'classmethod', 'ord', 'chr', 'hex', 'format', 'divmod', 'pow',
}


def collect_names(tree):
    names = set(BUILTINS)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != '*':
                    names.add(a.asname or a.name)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.Global):
            names.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            names.update(node.names)
    return names


def check(path):
    with open(path) as f:
        src = f.read()
    try:
        tree = ast.parse(src, path)
    except SyntaxError as e:
        return ['%s: 语法错误 %s' % (os.path.basename(path), e)]
    names = collect_names(tree)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base = node.value.id
            if base in names:
                continue
            # 只报“短别名”形式（模块别名），避免把 obj.xxx 误报。
            # 注意不能只查小写：模块别名也常写成 L / T / D / S 这类大写单字母，
            # 之前的 islower() 过滤恰好把真正的 bug（L.WEEK_CN）漏掉了。
            if 1 <= len(base) <= 3 and base.isalpha():
                bad.append('%s:%d 未定义的模块别名 %r（使用了 .%s）'
                           % (os.path.basename(path), node.lineno, base, node.attr))
    return bad


def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brl')
    problems = []
    files = sorted(f for f in os.listdir(root) if f.endswith('.py'))
    for fn in files:
        problems.extend(check(os.path.join(root, fn)))
    seen = set()
    uniq = []
    for p in problems:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    if uniq:
        print('发现未定义别名:')
        for p in uniq:
            print('  ' + p)
        return 1
    print('别名引用检查通过（%d 个模块）' % len(files))
    return 0


if __name__ == '__main__':
    sys.exit(main())
