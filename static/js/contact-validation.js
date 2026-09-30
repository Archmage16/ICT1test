(() => {
  const namePattern = /^[\p{L}][\p{L}\p{M}]*(?:[ '-][\p{L}][\p{L}\p{M}]*)*$/u;
  document.querySelectorAll('form[data-contact-validation]').forEach(form => {
    const fields = form.querySelectorAll('[data-contact-name], [data-contact-phone], [data-contact-email]');
    const validate = field => {
      field.setCustomValidity('');
      const value = field.value.trim();
      if (!value) return; // Native required validation handles mandatory fields.
      let invalid = false;
      if (field.hasAttribute('data-contact-name')) {
        const name = value.normalize('NFC').replace(/[\u2019\u02bc]/g, "'").replace(/[\u2010\u2011]/g, '-').replace(/ +/g, ' ');
        invalid = !namePattern.test(name);
      } else if (field.hasAttribute('data-contact-phone')) {
        const digits = value.replace(/[^0-9]/g, '');
        invalid = !/^\+?[0-9 ()-]+$/.test(value) || digits.length < 7 || digits.length > 15;
      } else {
        invalid = field.validity.typeMismatch || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
      }
      if (invalid) field.setCustomValidity(field.dataset.invalidMessage);
    };
    fields.forEach(field => {
      field.addEventListener('input', () => validate(field));
      field.addEventListener('blur', () => validate(field));
      validate(field);
    });
    form.addEventListener('submit', event => {
      fields.forEach(validate);
      if (!form.reportValidity()) event.preventDefault();
    });
    // Bring server-side errors into view after a failed submission.
    form.querySelector('[aria-invalid="true"]')?.focus();
  });
})();
