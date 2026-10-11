import pathlib
content = pathlib.Path('pyproject.toml').read_text(encoding='utf-8')
content = content.replace('version = "0.3.0"', 'version = "0.4.0"')
pathlib.Path('pyproject.toml').write_text(content, encoding='utf-8')
print('pyproject.toml updated')
