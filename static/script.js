// Small progressive enhancement hook for the prototype.
document.addEventListener('DOMContentLoaded', () => {
  const finder = document.querySelector('#appointment-finder');
  if (finder) {
    const state = document.querySelector('#location-state');
    const district = document.querySelector('#location-district');
    const city = document.querySelector('#location-city');
    const hospital = document.querySelector('#location-hospital');
    const doctor = document.querySelector('#location-doctor');
    const status = document.querySelector('#directory-status');
    const details = document.querySelector('#selected-hospital');
    const form = document.querySelector('#appointment-booking');
    const versions = new Map();
    const putOptions = (select, rows, prompt) => {
      select.replaceChildren(new Option(prompt, ''));
      rows.forEach((row) => select.add(new Option(row.name, row.name)));
      select.disabled = rows.length === 0;
    };
    const reset = (select, prompt) => { select.replaceChildren(new Option(prompt, '')); select.disabled = true; };
    const api = async (url) => {
      let response;
      try {
        response = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
      } catch (_) {
        throw new Error('Could not reach the appointment directory. Check that Flask is running and sign in again.');
      }
      let payload;
      try { payload = await response.json(); }
      catch (_) { throw new Error('The appointment directory returned an invalid response. Check the Flask server logs.'); }
      if (!response.ok) throw new Error(payload.error || 'The directory could not be loaded.');
      if (!payload || !Array.isArray(payload.items)) throw new Error('The appointment directory response is missing its items list.');
      return payload.items;
    };
    const invalidate = (...keys) => keys.forEach((key) => versions.set(key, (versions.get(key) || 0) + 1));
    const queryUrl = (base, params) => `${base}?${new URLSearchParams(params)}`;
    const showHospital = (item) => {
      details.replaceChildren();
      if (!item) { details.hidden = true; return; }
      details.hidden = false;
      const title = document.createElement('h3'); title.textContent = item.hospital_name;
      const address = document.createElement('p'); address.textContent = item.address || [item.area, item.city, item.district, item.state].filter(Boolean).join(', ');
      const source = document.createElement('p'); source.textContent = item.source_type === 'data.gov.in' ? `Government directory source · imported ${item.imported_at || 'date unavailable'} · confirm current details` : `Admin-provided listing · unverified · imported ${item.imported_at || 'date unavailable'}`;
      details.append(title, address, source);
      if (item.phone) { const phone = document.createElement('a'); phone.href = `tel:${item.phone}`; phone.textContent = `Call ${item.phone}`; details.append(phone); }
      if (item.specialties) { const specialty = document.createElement('p'); specialty.textContent = `Reported specialties: ${item.specialties}`; details.append(specialty); }
      if (item.pincode) { const pin = document.createElement('p'); pin.textContent = `PIN: ${item.pincode}`; details.append(pin); }
    };
    const load = async (key, label, action, emptyMessage) => {
      const version = (versions.get(key) || 0) + 1;
      versions.set(key, version);
      status.textContent = `Loading ${label}…`;
      status.className = 'notice';
      try {
        const rows = await action();
        if (versions.get(key) !== version) return null;
        status.textContent = rows.length ? `${rows.length} ${label} available.` : emptyMessage;
        return rows;
      }
      catch (error) {
        if (versions.get(key) !== version) return null;
        status.textContent = error.message;
        status.className = 'notice error';
        return null;
      }
    };
    load('states', 'states', () => api(finder.dataset.statesUrl), 'No geography data is loaded. Import the LGD States, Districts, and Urban-with-PIN datasets; see README.md for the command.').then((rows) => {
      if (rows) putOptions(state, rows, rows.length ? 'Choose state' : 'No states available');
    });
    state.addEventListener('change', async () => {
      invalidate('districts', 'cities', 'hospitals', 'doctors');
      reset(district, 'Choose district'); reset(city, 'Choose city or town'); reset(hospital, 'Choose hospital'); reset(doctor, 'No doctor selected'); showHospital(null);
      if (!state.value) { status.textContent = 'Choose a state to load its districts.'; status.className = 'notice'; return; }
      const rows = await load('districts', 'districts', () => api(queryUrl(finder.dataset.districtsUrl, { state: state.value })), 'No districts found for this state. Refresh the LGD geography dataset.');
      if (rows) putOptions(district, rows, rows.length ? 'Choose district' : 'No districts available');
    });
    district.addEventListener('change', async () => {
      invalidate('cities', 'hospitals', 'doctors');
      reset(city, 'Choose city or town'); reset(hospital, 'Choose hospital'); reset(doctor, 'No doctor selected'); showHospital(null);
      if (!district.value) { status.textContent = 'Choose a district to load its cities or towns.'; status.className = 'notice'; return; }
      const rows = await load('cities', 'cities / towns', () => api(queryUrl(finder.dataset.citiesUrl, { state: state.value, district: district.value })), 'No cities or towns found in this district.');
      if (rows) putOptions(city, rows, rows.length ? 'Choose city or town' : 'No cities available');
    });
    city.addEventListener('change', async () => {
      invalidate('hospitals', 'doctors');
      reset(hospital, 'Choose hospital'); reset(doctor, 'No doctor selected'); showHospital(null);
      if (!city.value) { status.textContent = 'Choose a city or town to load hospitals.'; status.className = 'notice'; return; }
      const rows = await load('hospitals', 'hospitals', () => api(queryUrl(finder.dataset.hospitalsUrl, { state: state.value, district: district.value, city: city.value })), 'No hospitals are listed for this location. An admin must import sourced hospital records.');
      if (rows) {
        hospital.replaceChildren(new Option(rows.length ? 'Choose hospital' : 'No hospitals available', ''));
        rows.forEach((item) => { const option = new Option(item.hospital_name, String(item.id)); option.dataset.hospital = JSON.stringify(item); hospital.add(option); });
        hospital.disabled = rows.length === 0;
      }
    });
    hospital.addEventListener('change', async () => {
      invalidate('doctors');
      const option = hospital.selectedOptions[0];
      showHospital(option && option.dataset.hospital ? JSON.parse(option.dataset.hospital) : null);
      reset(doctor, 'No doctor records');
      doctor.required = false;
      if (!hospital.value) { status.textContent = 'Choose a hospital to load its doctors.'; status.className = 'notice'; return; }
      const base = finder.dataset.doctorUrlBase.replace('/0/', `/${encodeURIComponent(hospital.value)}/`);
      const rows = await load('doctors', 'doctor names', () => api(base), 'No doctor records are associated with this hospital. You can continue without selecting a doctor.');
      if (rows) {
        doctor.replaceChildren(new Option(rows.length ? 'Choose doctor (optional)' : 'No doctor records', ''));
        rows.forEach((item) => {
          const verified = item.verification_status === 'verified' ? 'NMC checked' : 'unverified';
          const label = `${item.doctor_name}${item.specialty ? ` · ${item.specialty}` : ''} · ${verified}`;
          doctor.add(new Option(label, item.id));
        });
        doctor.disabled = rows.length === 0;
        status.textContent = rows.length ? `${rows.length} doctor names available for this hospital.` : 'No doctor records are associated with this hospital. You can continue without selecting a doctor.';
      }
    });
    const dateInput = document.querySelector('#appointment-date');
    if (dateInput) { const now = new Date(); dateInput.min = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`; }
    form.addEventListener('submit', (event) => {
      if (!hospital.value) { event.preventDefault(); status.textContent = 'Choose a hospital before saving a demo request.'; status.className = 'notice error'; }
    });
  }

  const reminderButton = document.querySelector('#enable-reminders');
  if (reminderButton) {
    const status = document.querySelector('#reminder-status');
    const reminders = [...document.querySelectorAll('[data-medication-id][data-reminder-time]')];
    let reminderTimer;
    const checkReminders = () => {
      const now = new Date();
      const currentTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
      const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
      reminders.forEach((item) => {
        if (item.dataset.reminderTime !== currentTime) return;
        const key = `health-copilot-reminder-${today}-${item.dataset.medicationId}`;
        if (localStorage.getItem(key)) return;
        new Notification('Medicine reminder', { body: `Time for your scheduled reminder: ${item.querySelector('strong').textContent}` });
        localStorage.setItem(key, 'sent');
      });
    };
    reminderButton.addEventListener('click', async () => {
      if (!('Notification' in window)) {
        status.textContent = 'Browser notifications are not supported here. Your schedule is still listed on this page.';
        return;
      }
      const permission = Notification.permission === 'default' ? await Notification.requestPermission() : Notification.permission;
      if (permission !== 'granted') {
        status.textContent = 'Notifications are not enabled. Your schedule is still listed on this page.';
        return;
      }
      status.textContent = 'Browser reminders are enabled while this dashboard stays open.';
      checkReminders();
      if (!reminderTimer) reminderTimer = window.setInterval(checkReminders, 15000);
    });
  }

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
