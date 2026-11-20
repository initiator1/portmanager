"use strict";
const patchbay = document.querySelector("#patchbay");
const demoToggle = document.querySelector("#demo-toggle");
const demoBadge = document.querySelector("#demo-badge");
const demoOutput = document.querySelector("#demo-output");
demoToggle.addEventListener("click", () => {
  const assigned = patchbay.dataset.state !== "assigned";
  patchbay.dataset.state = assigned ? "assigned" : "collision";
  patchbay.querySelectorAll("[data-port]").forEach((node, index) => {
    node.textContent = String(5190 + (assigned ? index : 0));
  });
  demoBadge.textContent = assigned ? "Assigned" : "Collision";
  demoToggle.textContent = assigned
    ? "Show the collision"
    : "Assign separate ports";
  demoOutput.textContent = assigned
    ? "$ portmanager claim ./studio web\n$ portmanager claim ./api api\n$ portmanager claim ./docs web"
    : "Three projects request :5190.\nThey cannot share the same listener.";
});
document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    const code = document.getElementById(button.dataset.copy);
    const status = document.getElementById("copy-status");
    try {
      await navigator.clipboard.writeText(code.textContent);
      status.textContent =
        button.dataset.copy === "install-command"
          ? "Install command copied."
          : "Workspace setup commands copied.";
    } catch {
      const range = document.createRange();
      range.selectNodeContents(code);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      status.textContent =
        "Command selected. Use your keyboard or context menu to copy it.";
    }
  });
});
