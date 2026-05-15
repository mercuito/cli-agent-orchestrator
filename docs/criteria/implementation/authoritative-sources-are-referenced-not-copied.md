---
name: authoritative-sources-are-referenced-not-copied
when: Code introduces a configuration key, CLI flag, argument name, directory location, or other shared value.
---

# Reference Authoritative Sources Instead Of Copying

Configuration keys, CLI flags, argument names, directory locations, and shared
logic must have a single authoritative definition. Other call sites must import
and reference that definition rather than copying the string literal or
re-implementing the logic.


## Illustrations

### Configuration Directory

```markdown
plan.md
# We need to load config from the default config directory in the parser
- [ ] Read config from `/etc/myapp/config` in the parser
...
```

**Bad - copied literal.** The parser hardcodes the directory string instead of
referencing the shared constant.

```python
# parser.py
config_path = "/etc/myapp/config"
```

**Good:** A single source of truth defines the constant, and call sites import
it.

```python
# shared/constants.py
DEFAULT_CONFIG_DIR = "/etc/myapp/config"

# parser.py
from shared.constants import DEFAULT_CONFIG_DIR
config_path = DEFAULT_CONFIG_DIR
```

### CLI Flags

```markdown
plan.md
# We need to add a new CLI flag for verbose logging
- [ ] Add a new CLI flag `--verbose` for verbose logging
...
```

**Bad - copied literal.** The flag string is duplicated wherever it is checked,
so renaming requires touching every call site.

```python
# parser.py
verbose_flag = "--verbose"
```

**Good:** Flags are declared once in a shared module and referenced by name.

```python
# shared/cli.py
CLI_FLAGS = {
    "verbose": "--verbose",
    "config": "--config",
}

# parser.py
from shared.cli import CLI_FLAGS
verbose_flag = CLI_FLAGS["verbose"]
```
