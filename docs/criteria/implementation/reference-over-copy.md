---
name: centralized-vocabulary
when: Always
---

# Referencing Authoratative Sources

When coding, you must refer to authortative sources vs copying.
Configuration keys, CLI flags, argument names, directory locations, logic.


## Illustrations
```markdown
plan.md
# We need to add a new CLI flag for verbose logging
- [ ] Add a new CLI flag `--verbose` for verbose logging
...
```

**Good:** 
```py
# shared/constants.py
# create a single source of truth for the constant
DEFAULT_CONFIG_DIR = '/etc/myapp/config'

# parser.py
from shared.constants import DEFAULT_CONFIG_DIR

# reference the constant instead of copying the string literal
config_path = DEFAULT_CONFIG_DIR
```

```py
# shared/cli.py
CLI_FLAGS = {
    'verbose': '--verbose',
    'config': '--config',
}

# parser.py
from shared.cli import CLI_FLAGS
# reference the CLI flag instead of copying the string literal
verbose_flag = CLI_FLAGS['verbose']
```
**Bad:**
```py config_paths.py
DEFAULT_CONFIG_DIR = '/etc/myapp/config'
```

```py# parser.py
# copying the string literal instead of referencing the constant
config_path = '/etc/myapp/config'
```

```py# parser.py
# copying the string literal instead of referencing the CLI flag
verbose_flag = '--verbose'
``` 