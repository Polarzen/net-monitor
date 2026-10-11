import re

# Read the file
with open('src/net_monitor/ui/micro_model.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add a public property to expose groups after the set_foreground_pid method
new_property = '''
    @property
    def groups(self) -> dict[str, ApplicationNetworkGroup]:
        """Expose aggregated application groups for reuse by other components."""
        return self._groups
'''

# Find the set_foreground_pid method and add the property after it
pattern = r'(    def set_foreground_pid\(self, pid: int \| None\) -> None:\n        """Set the current foreground PID for spotlight computation\."""\n        self\._spotlight_foreground_pid = pid\n)'
replacement = r'\1' + new_property

content = re.sub(pattern, replacement, content)

# Write back
with open('src/net_monitor/ui/micro_model.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added groups property to MicroProjection')
