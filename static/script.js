// Small progressive enhancement hook for the prototype.
document.addEventListener('DOMContentLoaded', () => {
  const search = document.querySelector('#report-search');
  if (search) {
    const reports = [...document.querySelectorAll('.report-list .report-entry')];
    const status = document.querySelector('#report-search-status');
    search.addEventListener('input', () => {
      const query = search.value.trim().toLocaleLowerCase();
      let visible = 0;
      reports.forEach((report) => {
        const matches = report.textContent.toLocaleLowerCase().includes(query);
        report.hidden = !matches;
        if (matches) visible += 1;
      });
      status.textContent = query ? `${visible} report${visible === 1 ? '' : 's'} found` : '';
    });
  }

  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', () => {
      const button = form.querySelector('button[type="submit"], button:not([type])');
      if (button && !button.name) {
        button.dataset.originalText = button.textContent;
        button.textContent = 'Please wait…';
        button.disabled = true;
      }
    });
  });
});
