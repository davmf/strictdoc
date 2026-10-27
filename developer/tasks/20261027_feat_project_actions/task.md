# Run project commands from the web UI

## WHAT

A project can declare commands ("project actions") in its StrictDoc
configuration. The StrictDoc server lists them, runs them with parameters
that the user enters in the browser, streams their output, shows the files
they produce and rebuilds the project when they finish. A project can also
bind an action to SysML elements of a given type. The page of a matching
element then shows a button that runs the action for that element.

StrictDoc stays model agnostic and has no code specific to simulation or to
a particular model. The reference project is
`/home/dxf/halcyon-dpcr-model`, whose `tools/run.py` provides the commands.

### Requirements

1. Declaration
   - A project declares actions in `strictdoc_config.py`.
   - Each action has a handle (`snake_case`), a title, a fixed argv and a
     list of typed parameters.
   - Parameter types: choice, integer, float, boolean and string. Each
     parameter has a default, a command line flag and, for a choice, the
     allowed values.
   - An action can list output paths (globs relative to the project root)
     that it produces.
   - The feature is off unless the project enables a new project feature,
     `PROJECT_ACTIONS`.
2. Running
   - The server shows a "Run" screen with one form per action.
   - The server validates every parameter against its type and choices
     before it starts a process. It builds argv from the declaration and
     the validated values. It never passes user input through a shell.
   - The process runs with the project root as its working directory.
   - At most one action runs at a time. A second request gets a clear
     "busy" message.
   - The user can cancel a running action.
   - The run screen streams stdout and stderr while the process runs, then
     shows the exit code and the duration.
3. After a run
   - The server rebuilds the traceability index when the process exits,
     so new JUnit results appear on requirement pages and the test report
     screen without a manual step.
   - The run screen shows the output files that changed during the run:
     SVG and PNG inline, MP4 as a video, GIF as an image, HTML in an iframe,
     anything else as a download link.
   - The server serves only files inside the project root that match the
     action's declared output paths.
4. Element binding
   - An action can declare a SysML binding: an element kind (for example
     `part`), the definition its type must specialise (for example
     `Scenario`) and the parameter that receives the element name.
   - A matching element on a SysML design page shows a button for the
     action. The button opens the action form with the bound parameter
     filled in and locked.
5. Safety
   - The run screen and its endpoints exist only when `PROJECT_ACTIONS` is
     enabled.
   - If the server listens on any host other than `127.0.0.1` or
     `localhost`, it refuses to start actions unless the project config
     explicitly allows remote runs.
   - The user guide explains that an action runs arbitrary project code
     with the server's permissions.

### Reference project changes (Halcyon repository, not StrictDoc)

1. `tools/run.py` gains `--json` output for `check`, `bounds`, `simulate`
   and `verify`, so a later version of the run screen can render tables.
2. A new `tools/run.py trace --scenario X --output build/media/x.html`
   command writes a self-contained HTML player built from the recorded
   trace (`RunOptions(record_trace=True)`). The player has play, pause,
   speed and a scrub bar. It replaces the tkinter `animate --live` window
   for browser use.
3. `strictdoc_config.py` declares actions for `check`, `bounds`,
   `simulate`, `verify`, `plots`, `animate --video` and `trace`. The
   `simulate`, `animate` and `trace` actions bind to part usages typed by
   a `Scenario` specialisation.

### Success criteria

- In the Halcyon project, a user changes `blocks.capacity` in the web
  editor, runs `verify` from the browser and sees the updated PASS/FAIL
  results on the SYS requirements without leaving the browser.
- From the `baseSteady` element page, a user starts `trace` and plays the
  animation on the run screen.
- End-to-end tests cover declaring, running, cancelling, the busy state,
  parameter validation, output display and element binding.
- `invoke lint` and the `invoke test-*` tasks pass.

### Out of scope

- Several concurrent runs, a run queue and run history across restarts.
- Authentication and per-user permissions.
- Rendering `--json` output as tables on the run screen.

## WHY

The Halcyon model lives in two places. StrictDoc shows and edits the
static SysML model and its requirements. The simulation and the four
verification layers run only from a terminal through `tools/run.py`.

To check the effect of a design change, a user edits the model in the
browser, switches to a terminal, runs `tools/run.py verify`, then rebuilds
or reloads StrictDoc to see the JUnit results. The live animation opens a
tkinter desktop window, which does not work when the user reaches the
StrictDoc server from a browser on another machine or without a display.

The same split applies to any StrictDoc project that generates evidence
with scripts: test runs, analyses or code generators.

## HOW

Add a feature-flagged "project actions" subsystem in its own modules: a
declaration type in the project config, a runner that owns one subprocess,
a new router and a run screen. Reuse the server's existing rebuild path.
The model-specific parts (JSON output, trace player, action list) live in
the Halcyon repository.

### Phases

1. Declaration and runner (StrictDoc)
   - `strictdoc/core/project_action.py`: `ProjectAction` and
     `ProjectActionParameter` dataclasses, with validation that turns form
     values into argv.
   - `ProjectConfig` gains an `actions` argument and the
     `PROJECT_ACTIONS` feature.
   - `strictdoc/server/project_action_runner.py`: starts the process with
     `subprocess.Popen` (argv list, `shell=False`), keeps a bounded output
     buffer, supports cancel and records file modification times before
     the run to detect changed outputs.
   - Integration tests for validation and argv building.
2. Router and run screen (StrictDoc)
   - `strictdoc/server/routers/project_actions_router.py`, included from
     `app.py` only when the feature is enabled. Keep it out of
     `main_router.py`.
   - The output stream uses server-sent events (`StreamingResponse`) per
     run. The existing `/ws/{client_id}` websocket only broadcasts reloads.
   - A new screen template in
     `strictdoc/export/html/templates/screens/project_actions/` and a new
     `project_actions.js` controller in `strictdoc/export/html/_static/`.
   - Add a "Run" entry to `templates/_shared/nav.jinja.html` when the
     feature is on.
   - End-to-end tests under `tests/end2end/screens/project_actions/` with a
     small fixture project whose actions are short Python scripts.
3. Rebuild and outputs (StrictDoc)
   - Move `rebuild_index_after_file_change()` and
     `notify_clients_after_file_change()` out of `main_router.py` so that
     both routers can call them. This touches a shared component.
   - Serve changed output files through an endpoint that checks the
     declared globs and the project root.
4. SysML element binding (StrictDoc)
   - Resolve the binding in the SysML reader: an element matches when its
     type specialises the named definition. Halcyon needs one level of
     indirection (`baseSteady : BaseSteadyStat`, `BaseSteadyStat :>
     Scenario`) within one file.
   - Render the action buttons in the SysML design node template.
5. Reference project (Halcyon repository)
   - `--json` output, the `trace` command and its HTML player, and the
     action declarations in `strictdoc_config.py`.
   - Fix the README: the "Design verification" section names
     `build/results/`, but `run.py` writes JUnit to `reports/junit/`.

### Shared components touched

The user approves these changes before implementation starts (AGENTS.md,
"Change scope"):

- `strictdoc/core/project_config.py`: new argument and feature.
- `strictdoc/server/app.py`: conditional router include.
- `strictdoc/server/routers/main_router.py`: move of the rebuild helpers.
- `strictdoc/export/html/templates/_shared/nav.jinja.html`: "Run" entry.
- SysML reader and design node template: element binding.

### Trade-offs

- Server-sent events instead of the websocket: one stream per run, no
  client ID handling, and no change to the reload broadcast.
- An HTML player produced by the project instead of a StrictDoc player:
  StrictDoc only needs to show an HTML file in an iframe, and the player
  can change with the model without changing StrictDoc.
- `animate --video` needs no extra work. It is an action whose MP4 output
  the run screen shows.

### Open questions

- Should choice values come from the model, for example every part usage
  typed by a `Scenario` specialisation, instead of a static list in the
  config?
- Should a finished run's output and log persist on disk, so that a page
  reload or another user can see the last result?
- Is this feature meant for upstream StrictDoc, or only for the
  `david/sysml-*` branches?
