# Web UI: unpublished changes and publish

## WHAT

A user who edits documents in the StrictDoc web UI shall be able to see,
discard and commit their changes without using Git on the command line.

The UI shall use plain terms. It says "publish" for a commit and "unpublished
changes" for a dirty working tree. It does not mention staging, the index or
branches.

This task covers two stages. Each stage is a separate PR.

### Feature flag

- A new experimental project feature, `GIT_PUBLISH`, enables both stages.
- The feature works only in `strictdoc server` mode. Static HTML export
  ignores it.
- If the project root is not a Git working tree, the server shall start
  normally. The UI shall show "Publishing is unavailable: this project is not
  in a Git repository" in place of the stage 1 and stage 2 controls.
- If the server listens on an address other than a loopback address
  (`127.0.0.1`, `::1`, `localhost`), the stage 2 "Publish" and the stage 1
  "Discard" actions shall be disabled. The UI shall say why. Reading the list
  of unpublished changes stays available.

### Managed files

StrictDoc only reads, discards and commits managed files. A managed file is
one of these:

- A document file, meaning a file with an extension from
  `get_document_extensions(project_config)`, located under one of the
  project's input paths.
- A file inside the project's assets directory
  (`dir_for_sdoc_assets`, default `_static`) under an input path.

StrictDoc ignores every other file, including other files in the same
directory. It never runs `git add -A`, `git add .` or `git commit -a`.

### Stage 1: unpublished changes (PR 1)

1. The navigation bar shall show a badge with the number of managed files
   that have unpublished changes, for example "3 unpublished changes". If
   there are none, the badge shall read "All changes published".
2. Clicking the badge shall open a "Changes since last publish" screen. For
   each changed file the screen shall show:
   - the document title (or the file path for non-document files)
   - the kind of change: modified, new or deleted
   - a link to the existing changelog view comparing `HEAD` with `HEAD+`,
     so the user can see the node-level changes.
3. Each changed file shall have a "Discard changes" action.
   - The action shall ask for confirmation. The dialog shall name the file
     and say that the change cannot be undone.
   - For a modified or deleted tracked file, StrictDoc shall restore the
     file to its state in `HEAD`.
   - For a new, untracked file, StrictDoc shall delete the file.
   - After a discard, the server shall rebuild its document tree. The UI
     shall show the result without a manual page reload.
4. The badge and the screen shall update after every edit that the server
   writes to disk, and after the file watcher detects an external change.

### Stage 2: publish (PR 2)

1. The "Changes since last publish" screen shall have a "Publish" button.
2. Clicking "Publish" shall open a form with:
   - A pre-filled, editable description. StrictDoc generates it from the
     changelog engine. For example:
     `SRS: modified REQ-12, added REQ-40, removed REQ-7`.
   - The list of files that will be published, all selected by default.
     The user can clear the checkbox of a file to leave it out.
3. On confirm, StrictDoc shall create one Git commit that contains only the
   selected managed files. The commit message is the description from the
   form. StrictDoc does not push.
4. StrictDoc shall refuse to publish if the project has validation errors.
   The UI shall list the errors.
5. StrictDoc shall refuse to publish, and shall show a plain-language
   message, in each of these repository states:
   - a merge, rebase, cherry-pick or revert is in progress
   - `HEAD` is detached
   - files outside the selected managed files are already staged
   - Git has no `user.name` or `user.email` configured.
6. Each message from item 5 shall have a "Show details" section with the
   Git command output and a one-line hint for a Git-literate colleague.
7. After a successful publish, the screen shall show the short commit hash
   and the commit message. The badge shall return to "All changes
   published", unless unselected files remain.
8. A "Show details" section on the result screen shall list every Git
   command StrictDoc ran, with its exit code.

### Success criteria

- A user can edit a requirement in the UI, publish it and see a new commit
  in `git log`, without opening a terminal.
- No StrictDoc action changes a file that is not a managed file.
- `invoke lint` and `invoke check` pass.
- The new end-to-end tests pass with `invoke test-end2end --focus
  git_publish --headless`.

### Out of scope

- Push, pull or fetch (stage 3 of the original proposal).
- Revision history screens (stage 4).
- Branches, pull requests and merge requests (stage 5).
- Authentication and per-user commit authorship.
- Auto-commit on every save.

## WHY

The user guide lists a missing feature: "a dedicated screen where a user can
commit and push changes to GitHub/GitLab or other Git servers"
(`docs/strictdoc_01_user_guide.sdoc`, section "Limitations of web user
interface"). The backlog tracks it as `SDOC-BACKLOG-6` "Auto-commit to Git
repository" (`docs/strictdoc_28_Backlog.sdoc`). The web UI backlog also asks
the server to "provide visibility to what happens under the hood".

Today the only supported workflow needs two terminals: one runs the server,
the other reviews and commits the `.sdoc` files. A user who does not know
Git, such as a reviewer or a quality engineer, cannot finish that workflow
alone.

This task uses an explicit publish step instead of auto-commit on every
save. One
commit per save gives a noisy history with no useful messages, which is a
poor audit trail for regulated projects (IEC 62304, DO-178C). A publish step
with a generated message costs the user one click and records what changed.

This task defers push and pull. The server has no authentication, so a network
deployment with push would let anyone who can reach the port push with the
host's credentials. Merge conflicts are the point where a user cannot avoid
Git knowledge, so sync needs its own design.

## HOW

Summary: add a `GIT_PUBLISH` feature flag, a small set of new `GitClient`
methods, a new feature package `strictdoc/features/git_publish/` with its
own router, screen and templates, and one badge in the shared navigation
bar. Reuse the existing `HEAD+` changelog engine for the change list and the
generated commit message.

### Rules for the implementing agent

- Follow `AGENTS.md` and the SDG (`docs/strictdoc_11_developer_guide.sdoc`).
- Use `developer/tasks/20261001_web_ui_publish_changes/Context.md` as
  working memory. Do not edit `task.md`.
- Implement stage 1 fully, including tests and docs, before you start
  stage 2. Each stage is one PR with one commit, per the SDG Git workflow.
- Commit messages use Conventional Commits, for example
  `feat(server, git_publish): show unpublished changes`.
- The user approves changes to the shared components listed under "Shared
  components". Stop and ask before you change any other shared component.

### Shared components

Change each of these only as described:

- `strictdoc/core/project_config.py`: add `ProjectFeature.GIT_PUBLISH` to
  the experimental features and add `is_activated_git_publish()`, following
  the pattern of `is_activated_diff()`.
- `strictdoc/features/diff_and_changelog/git_client.py`: add the methods
  listed below. Do not change existing methods.
- `strictdoc/export/html/templates/_shared/nav.jinja.html`: include one
  feature-local partial for the badge, guarded by
  `is_running_on_server and is_activated_git_publish()`. Put the badge
  markup in the feature's own template, not in `nav.jinja.html`.
- `strictdoc/server/app.py` or `strictdoc/server/routers/main_router.py`:
  register the new router. Expose the existing index rebuild
  (`rebuild_index_after_file_change` and `notify_clients_after_file_change`
  in `main_router.py`) so the new router can call it after a discard.
  Prefer a small refactor that moves the rebuild into a callable on
  `app.state` over duplicating it.

### Feature-local code

Put new code in `strictdoc/features/git_publish/`:

- `git_publish_service.py`: computes managed files, their status, the
  repository state checks and the commit message. It calls `GitClient` and
  holds no FastAPI code.
- `git_publish_router.py`: routes for the badge partial, the changes
  screen, discard, the publish form and the publish action.
- `templates/`: Jinja templates for the badge, the screen, the dialogs and
  the result.
- `assets/`: any JS or CSS the screen needs. Follow the pattern used in
  `strictdoc/features/diff_and_changelog/`.

### New GitClient methods

All methods take explicit paths and run Git with `subprocess.run(...,
check=False)`, as the existing methods do. Each returns a result object
that keeps the command line, exit code, stdout and stderr, so the UI can
show them under "Show details".

- `get_status(paths) -> List[FileStatus]`: runs
  `git status --porcelain=v1 -z --untracked-files=all -- <paths>`. It parses
  modified, added, deleted and untracked entries, including renames.
- `get_repository_state() -> RepositoryState`: detects merge, rebase,
  cherry-pick and revert in progress. Use `git rev-parse --git-path` to find
  `MERGE_HEAD`, `rebase-merge`, `rebase-apply`, `CHERRY_PICK_HEAD` and
  `REVERT_HEAD`. Do not hard-code `.git/`, because worktrees and submodules
  use a different layout. Detect detached `HEAD` with
  `git symbolic-ref -q HEAD`.
- `get_staged_paths() -> List[str]`: runs
  `git diff --cached --name-only -z`.
- `has_identity() -> bool`: checks `git config user.name` and
  `git config user.email`.
- `restore_paths(paths)`: runs
  `git restore --source=HEAD --staged --worktree -- <paths>` for tracked
  files.
- `commit_paths(paths, message) -> str`: runs `git add -- <paths>`, then
  `git commit -F - -- <paths>` with the message on stdin, and returns the
  new commit hash. Passing the message on stdin avoids quoting problems.

### Git root

`other_router.py` creates `GitClient(".")`, so the diff feature assumes the
server runs from the Git root. Do not keep that assumption for this feature.
Resolve the root once with `git rev-parse --show-toplevel` from the project
directory, and pass paths relative to that root. If the command fails, the
feature is unavailable (see "Feature flag").

### Change list and commit message

- Get the node-level changes from `ChangeGenerator.generate_from_revisions`
  with `HEAD` and `HEAD+`, as the changelog tab does.
- Build the message as one line per document:
  `<document title>: modified <UIDs>, added <UIDs>, removed <UIDs>`. Use the
  node title for nodes without a UID. If the summary is longer than 72
  characters, use `Update <N> documents` as the first line and put the
  per-document lines in the body.
- For non-document managed files, add `Update assets: <file names>`.
- `HEAD+` builds a snapshot with `git add -A` into a temporary index. That
  is safe, because it does not touch the real index. Keep it.

### Concurrency and the file watcher

- Serialize discard and publish with one lock per server process, so two
  browser tabs cannot run them at the same time.
- Before a discard, call `document_watcher.inhibit_next_change(path)` for
  each restored or deleted document. Then rebuild the index once and send
  the `reload` broadcast. This avoids a double rebuild.
- When `watch_enabled` is off, the discard handler must still rebuild the
  index itself.
- Compute the badge count on request, not in the background. Cache it per
  request only.

### Validation before publish

Rebuild the traceability index from the files on disk. If the rebuild
returns an error, show it and do not commit. Reuse the same rebuild entry
point as the discard path.

### Requirements and docs

- Add L2 requirements to `docs/strictdoc_21_l2_high_level_requirements.sdoc`
  in a new section next to "Screen: Project tree diff". Write them in EARS
  syntax with `SDOC-SSS-33` "Version control (Git)" as the parent. One
  requirement per numbered item in WHAT is a reasonable granularity.
- Add `@relation(<UID>, scope=file)` markers to the new tests and the new
  modules.
- Add a "Publishing changes from the web UI" section to the user guide near
  the "Diff/changelog" section. Cover the feature flag, managed files, the
  refusal messages and the loopback-only rule.
- Update "Limitations of web user interface" in the user guide. Commit is
  now possible. Push and pull are still missing.
- Add a summary to the "Unreleased" section of
  `docs/strictdoc_04_release_notes.sdoc`, following the SDG release notes
  playbook.
- Do not change the status of `SDOC-BACKLOG-6`. The maintainers decide that.
- Keep documentation lines at 80 characters or fewer. Run `invoke docs` to
  check the output.

### Tests

Unit tests in `tests/unit/strictdoc/features/git_publish/`:

- Each new `GitClient` method against a temporary Git repository created in
  the test. Cover a clean tree, modified, new, deleted and renamed files,
  each refusal state, and a path with spaces.
- Managed-file filtering: a non-document file in an input path is never
  listed, discarded or committed.
- Commit message generation for one document, several documents, a long
  summary and assets only.

End-to-end tests in `tests/end2end/screens/git_publish/`, set up like
`tests/end2end/screens/diff/01_view_basic_diff/test_case.py`. Add a screen
helper under `tests/end2end/helpers/screens/git_publish/`.

- `01_badge_shows_unpublished_changes`: edit a requirement, check the badge
  count.
- `02_discard_modified_document`: edit, discard, check that the file matches
  `HEAD` and the UI shows the old content.
- `03_discard_new_document`: create a document in the UI, discard, check
  that the file is gone.
- `04_publish_one_document`: edit, publish with the generated message,
  check `git log -1` and `git show --stat` contain only the managed file.
- `05_publish_leaves_unmanaged_files_alone`: add an untracked `notes.txt`
  and a modified tracked file that is not managed. Publish, then check that
  both are unchanged and uncommitted.
- `06_publish_refused_during_merge`: create a merge conflict in the test
  repository, check the refusal message and that no commit was created.
- `07_feature_unavailable_outside_git`: run the server in a directory
  without `.git`, check the "unavailable" message.

Set `user.name` and `user.email` in each test repository, as the diff test
does. Run end-to-end tests with `--headless`. Iterate with `--focus`:

    invoke test-unit --focus git_publish
    invoke test-end2end --focus git_publish --headless

Run `invoke lint` and `invoke check` before each commit.

### Risks to note in the PR description

- All commits use the host's Git identity. That is correct for one local
  user and wrong for a shared server.
- `HEAD+` changelog generation copies the working tree into a worktree. On
  a large project the badge may be slow. If so, compute the badge count
  from `get_status` alone and run the changelog engine only on the screen.
- Windows: `fcntl` is not available. The publish lock must use
  `threading.Lock`, not a file lock.
