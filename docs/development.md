# Local development

[English](development.md) | [简体中文](development.zh-CN.md)

The recommended development entry point starts the FastAPI backend and the
Vinext frontend together:

```bash
./start.command
```

On macOS, `start.command` can also be opened directly from Finder. The launcher:

1. creates the Python virtual environment when it is missing;
2. installs the project-local Node runtime on macOS when necessary;
3. installs missing frontend dependencies;
4. checks that ports `8000` and `3000` are available;
5. starts the API and web UI, waits for their health checks, and opens the app;
6. stops both services when you press `Ctrl-C` or close the terminal.

Runtime logs are written to the ignored `.run/` directory. The default local
SQLite database remains at `data/clincforestbench.db`.

Useful options:

```bash
./start.command --no-open
./start.command --api-port 8100 --web-port 3100
./start.command --host 0.0.0.0
./start.command --no-install
./start.command --help
```

The equivalent Make target is `make start`. `make api` and `make web` remain
available when separate terminals or independent service restarts are useful.

The launcher accepts the environment variables `CFB_HOST`, `CFB_API_PORT`,
`CFB_WEB_PORT`, `CFB_OPEN_BROWSER`, `CFB_AUTO_INSTALL`, and
`CFB_STARTUP_TIMEOUT`. Backend settings such as `OPENROUTER_API_KEY` continue to
come from the root `.env` file or the environment.

## Verification

Run the full local validation before submitting changes:

```bash
make validate
```

This runs the Python test suite, frontend lint, and a production frontend build.
The full suite expects the generated benchmark artifacts described in
[Data setup](data_setup.md).
