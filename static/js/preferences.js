(() => {
  const control = document.querySelector('#theme-choice');
  if (!control) return;
  let preference = 'light';
  try { preference = localStorage.getItem('olympiq-theme') || 'light'; } catch (_) {}
  if (!['light', 'dark', 'system'].includes(preference)) preference = 'light';
  control.value = preference;
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  const apply = () => { document.documentElement.dataset.theme = preference === 'system' ? (system.matches ? 'dark' : 'light') : preference; };
  control.addEventListener('change', () => {
    preference = control.value;
    try { localStorage.setItem('olympiq-theme', preference); } catch (_) {}
    apply();
  });
  system.addEventListener('change', apply);
  apply();
  document.querySelectorAll('form[data-submit-once]').forEach(form => {
    form.addEventListener('submit', () => {
      const button = form.querySelector('button[type="submit"]');
      if (button) { button.disabled = true; button.textContent = button.dataset.sending; }
    });
  });
})();
