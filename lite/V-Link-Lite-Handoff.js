// Injected only into the Lite runtime's built HTML, never into V-Link sources.
(() => {
  const root = document.getElementById('root');
  if (!root) return;

  let sent = false;
  const ready = () => {
    if (sent || document.getElementById('boot-mark')) return;
    const marks = root.getElementsByTagName('use');
    let splashMounted = false;
    for (const mark of marks) {
      const href = mark.getAttribute('href') || mark.getAttribute('xlink:href') || '';
      if (href.endsWith('/assets/svg/logos/moose.svg#moose')) {
        splashMounted = true;
        break;
      }
    }
    if (!splashMounted) return;

    sent = true;
    observer.disconnect();
    const signal = () => {
      // An image ping avoids modifying the V-Link HTTP server. The Lite-only
      // overlay listens on loopback and sends a CORP-approved image response.
      const beacon = new Image();
      window.__vLinkLiteSplashBeacon = beacon;
      beacon.src = 'http://127.0.0.1:40777/ready?' + Date.now();
    };
    let signalled = false;
    const finish = () => {
      if (signalled) return;
      signalled = true;
      signal();
    };
    // An occluded Chromium window may throttle animation frames. This is a
    // fallback after React mounted, not a startup timer used as readiness.
    const fallback = setTimeout(finish, 1000);
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => requestAnimationFrame(() => {
        clearTimeout(fallback);
        finish();
      }));
    }
  };

  const observer = new MutationObserver(ready);
  observer.observe(root, { childList: true, subtree: true });
  ready();
})();
