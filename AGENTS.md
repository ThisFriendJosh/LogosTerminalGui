# Logos Terminal GUI

- Keep the host independent of AI models and LogosMind implementation packages. Backends belong in separate processes and projects.
- Runtime GUI dependencies are Python/Tk and the standard library. Development-only tools belong in requirements-dev.txt.
- Keep the versioned module contract, SDK documentation, schema, and transport tests consistent. Use stable module/action identifiers. Breaking protocol changes require a new API major version.
- Preserve unrelated module settings and backend sessions. Do not commit state/, work/, credentials, model weights, Bible corpora, or conversation databases.
- Validate changes with `python -m unittest discover -v`. Run `python tools/check_schemas.py` when manifests/schema change. Tk layout checks need a display or Xvfb.
- Follow the repository's existing GPL v3 license.
