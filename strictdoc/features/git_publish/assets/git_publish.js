// Load the "unpublished changes" badge into the navigation bar.
//
// Server pages are cached as static HTML, so the badge cannot be rendered
// into the page. This script fetches it on page load, and again after every
// request that may have written a file: any same-origin request that is not
// a GET. Table editing and node moving use fetch() directly and do not emit
// Turbo events, so the script wraps window.fetch to see those requests too.
// Turbo also uses fetch(), so form submissions are covered by the same hook.
//
// Changes made outside StrictDoc reach the page through the file watcher,
// which reloads the page and so reloads the badge.

(function () {
  if (window.gitPublishBadgeInstalled) {
    return;
  }
  window.gitPublishBadgeInstalled = true;

  const BADGE_CONTAINER_ID = "git_publish_badge";
  const RELOAD_DELAY_MILLISECONDS = 300;

  const originalFetch = window.fetch.bind(window);
  let reloadTimer = null;

  function getBadgeContainer() {
    return document.getElementById(BADGE_CONTAINER_ID);
  }

  async function reloadBadge() {
    const container = getBadgeContainer();
    if (!container) {
      return;
    }
    try {
      const response = await originalFetch(container.dataset.badgeUrl, {
        cache: "no-store",
      });
      if (response.ok) {
        container.innerHTML = await response.text();
      }
    } catch (error) {
      console.error("Could not load the unpublished changes badge:", error);
    }
  }

  // Several edits in a row cause one reload.
  function scheduleBadgeReload() {
    if (reloadTimer !== null) {
      clearTimeout(reloadTimer);
    }
    reloadTimer = setTimeout(() => {
      reloadTimer = null;
      reloadBadge();
    }, RELOAD_DELAY_MILLISECONDS);
  }

  function isWriteRequest(resource, options) {
    let method = "GET";
    let url = "";
    if (resource instanceof Request) {
      method = resource.method;
      url = resource.url;
    } else {
      url = String(resource);
    }
    if (options && options.method) {
      method = options.method;
    }
    if (method.toUpperCase() === "GET") {
      return false;
    }
    const requestUrl = new URL(url, window.location.href);
    return requestUrl.origin === window.location.origin;
  }

  window.fetch = function (resource, options) {
    const responsePromise = originalFetch(resource, options);
    if (isWriteRequest(resource, options)) {
      responsePromise.then(scheduleBadgeReload, scheduleBadgeReload);
    }
    return responsePromise;
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", reloadBadge);
  } else {
    reloadBadge();
  }
})();
