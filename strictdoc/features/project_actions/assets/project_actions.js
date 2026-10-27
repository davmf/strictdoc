// Streams the output of a running project action into the run screen.
// The server sends one "data" event per output line and a "finished" event
// after the run and the rebuild. On "finished", the page reloads to show the
// final state and the output files.
(function () {
  function streamRun(runSection) {
    const runId = runSection.dataset.runId;
    const lineCount = runSection.dataset.lineCount;
    const log = runSection.querySelector(".project_actions__log");
    const source = new EventSource(
      `/project_actions/stream?run_id=${runId}&offset=${lineCount}`
    );
    log.scrollTop = log.scrollHeight;
    source.onmessage = function (event) {
      const isAtBottom =
        log.scrollHeight - log.scrollTop - log.clientHeight < 20;
      log.append(JSON.parse(event.data) + "\n");
      if (isAtBottom) {
        log.scrollTop = log.scrollHeight;
      }
    };
    source.addEventListener("finished", function () {
      source.close();
      window.location.reload();
    });
  }

  window.addEventListener("DOMContentLoaded", function () {
    const runSection = document.querySelector(
      '[data-testid="project-actions-run"]'
    );
    if (runSection === null) {
      return;
    }
    const state = runSection.dataset.runState;
    if (state === "running" || state === "rebuilding") {
      streamRun(runSection);
    }
  });
})();
