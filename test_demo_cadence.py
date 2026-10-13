import ast
from pathlib import Path
s=Path(__file__).with_name('app.py').read_text()
ast.parse(s)
assert "period=3.0 if args.demo" in s
assert "force_kind='pd'" in s
assert "if not args.demo:" in s
print('Demo cadence source checks passed')
