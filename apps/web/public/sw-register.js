/* M7e-E1: registers /sw.js and tells the page (AppPrompts.tsx) when it can install or update. */
(function () {
  var s = (window.__mediease = window.__mediease || {});
  function emit(n) {
    window.dispatchEvent(new Event("mediease:" + n));
  }
  addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault();
    s.install = e;
    emit("installable");
  });
  addEventListener("appinstalled", function () {
    s.install = undefined;
    emit("installed");
  });
  var sw = navigator.serviceWorker;
  if (!sw || !window.isSecureContext) return;
  function waiting(w) {
    s.waiting = w;
    emit("update");
  }
  sw.register("/sw.js", { scope: "/", updateViaCache: "none" }).then(function (r) {
    if (r.waiting && sw.controller) waiting(r.waiting);
    r.addEventListener("updatefound", function () {
      var w = r.installing;
      if (w)
        w.addEventListener("statechange", function () {
          // Installed while another version controls the page: an update, not the first install.
          if (w.state === "installed" && sw.controller) waiting(w);
        });
    });
  }, function () {});
  // After Update, the new version takes over: load the page again on it.
  sw.addEventListener("controllerchange", function () {
    if (s.updating && !s.reloaded) {
      s.reloaded = true;
      location.reload();
    }
  });
})();
