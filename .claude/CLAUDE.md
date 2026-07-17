# User Preferences

## Use the project's Makefile

If a project contains a `Makefile`, prefer its targets over invoking development tools directly.

- Check available targets with `make help` or by reading the `Makefile`.
- Use `make <target>` whenever an appropriate target exists.
- Only run underlying tools directly if no suitable Makefile target is available.

The Makefile is the source of truth for project-specific commands, configuration, flags, and tool versions.

---

## Use asdf for all tool versions

This machine uses `asdf` to manage all development tool versions.

- Never assume installed tool versions.
- Check `.tool-versions` before selecting a version.
- Use `asdf list <tool>` to see available versions.
- Use `asdf current <tool>` to verify the active version.
- Use `asdf set <tool> <version>` to change versions.
- Do not change `.tool-versions` unless requested or there is a clear reason.

