// The only JavaScript in the app, and it's optional: every feature also
// works with plain HTML forms. It just smooths two rough edges.

// 1. Re-sort as soon as a different strategy is picked.
document.querySelectorAll("select[data-autosubmit]").forEach((select) => {
  select.addEventListener("change", () => select.form.submit());
});

// 2. Fetching features for a large playlist can take a few seconds, so
//    show a loading label and prevent double submits.
document.querySelectorAll("button[data-loading]").forEach((button) => {
  button.form.addEventListener("submit", () => {
    button.disabled = true;
    button.textContent = button.dataset.loading;
  });
});
