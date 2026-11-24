// Deep sleep (issue #53): on a host that stops the classifier when idle, the next request
// starts it again, which takes a few seconds. Without a hint the page looks frozen, so any
// request still running after WAKE_NOTICE_DELAY_MS shows a notice until it answers.
(function () {
  const WAKE_NOTICE_DELAY_MS = 1500;
  const originalFetch = window.fetch.bind(window);
  let slowRequests = 0;

  function setNoticeVisible(visible) {
    const notice = document.getElementById("wake-notice");
    if (notice) {
      notice.hidden = !visible;
    }
  }

  window.fetch = async function fetchWithWakeNotice(...args) {
    let countedAsSlow = false;
    const timer = setTimeout(() => {
      countedAsSlow = true;
      slowRequests += 1;
      setNoticeVisible(true);
    }, WAKE_NOTICE_DELAY_MS);
    try {
      return await originalFetch(...args);
    } finally {
      clearTimeout(timer);
      if (countedAsSlow) {
        slowRequests -= 1;
        if (slowRequests === 0) {
          setNoticeVisible(false);
        }
      }
    }
  };
})();
