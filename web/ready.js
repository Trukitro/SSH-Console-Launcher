// Shared "pywebview bridge is ready" gate used by every other script.
//
// History: each script used to independently listen for BOTH the
// "pywebviewready" event AND a blind 50ms-after-DOMContentLoaded fallback.
// Both listeners routinely fired, double-registering every click handler
// (that's why the Debug Console button used to open-then-immediately-close
// on a single click). Adding a `called` guard fixed the double-init, but
// created a worse regression: if the blind 50ms timer won the race before
// window.pywebview.api genuinely existed, init() ran too early, threw
// (`Cannot read properties of undefined (reading 'api')`), and the guard
// then permanently blocked the real, later pywebviewready event from ever
// retrying - the app was stuck on "Loading..." forever. A flat timeout
// can't know when the bridge is actually ready, so it can't be trusted as
// a one-shot fallback.
//
// Fix: don't guess with a timer. Poll for window.pywebview.api actually
// existing, and only run the callback once it's genuinely there. The
// pywebviewready event is still used as a fast path (it fires the moment
// the bridge is ready), the poll is the guaranteed-to-work backstop, and
// the guard still ensures the callback runs exactly once either way.
function onAppReady(callback) {
  let called = false;
  const tryRun = () => {
    if (called || !window.pywebview || !window.pywebview.api) return;
    called = true;
    callback();
  };

  tryRun();
  if (called) return;

  window.addEventListener("pywebviewready", tryRun);
  window.addEventListener("DOMContentLoaded", () => {
    const poll = setInterval(() => {
      tryRun();
      if (called) clearInterval(poll);
    }, 30);
  });
}
