const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class MockOption {
  constructor(text, value) {
    this.textContent = text;
    this.value = String(value);
    this.dataset = {};
  }
}

class MockElement {
  constructor() {
    this.listeners = new Map();
    this.children = [];
    this.dataset = {};
    this.disabled = false;
    this.hidden = false;
    this.className = '';
    this.textContent = '';
  }
  addEventListener(name, callback) {
    const listeners = this.listeners.get(name) || [];
    listeners.push(callback);
    this.listeners.set(name, listeners);
  }
  async dispatch(name) {
    return Promise.all((this.listeners.get(name) || []).map((callback) => callback({ preventDefault() {} })));
  }
  replaceChildren(...children) { this.children = children; }
  add(child) { this.children.push(child); }
  append(...children) { this.children.push(...children); }
  get selectedOptions() { return this.children.filter((option) => option.value === this.value); }
  get value() { return this._value ?? this.children[0]?.value ?? ''; }
  set value(value) { this._value = String(value); }
}

function buildPage(fetchImpl) {
  const selectors = [
    '#location-state', '#location-district', '#location-city', '#location-hospital',
    '#location-doctor', '#directory-status', '#selected-hospital', '#appointment-booking',
    '#appointment-date',
  ];
  const nodes = new Map(selectors.map((selector) => [selector, new MockElement()]));
  const finder = new MockElement();
  finder.dataset = {
    statesUrl: '/api/appointments/states',
    districtsUrl: '/api/appointments/districts',
    citiesUrl: '/api/appointments/cities',
    hospitalsUrl: '/api/appointments/hospitals',
    doctorUrlBase: '/api/appointments/hospitals/0/doctors',
  };
  nodes.set('#appointment-finder', finder);
  let ready;
  const document = {
    addEventListener(name, callback) { if (name === 'DOMContentLoaded') ready = callback; },
    querySelector(selector) { return nodes.get(selector) || null; },
    querySelectorAll() { return []; },
    createElement() { return new MockElement(); },
  };
  const context = {
    document,
    Option: MockOption,
    URLSearchParams,
    Date,
    fetch: fetchImpl,
    setTimeout,
    clearTimeout,
    console,
  };
  vm.runInNewContext(fs.readFileSync('static/script.js', 'utf8'), context);
  ready();
  return nodes;
}

const jsonResponse = (items) => ({ ok: true, json: async () => ({ items }) });
const flush = () => new Promise((resolve) => setImmediate(resolve));

test('state → district → city → hospital → doctor selectors load and reset in order', async () => {
  const calls = [];
  const fetchImpl = async (url) => {
    const parsed = new URL(url, 'http://localhost');
    calls.push(parsed.pathname + parsed.search);
    if (parsed.pathname.endsWith('/states')) return jsonResponse([{ name: 'Test State' }]);
    if (parsed.pathname.endsWith('/districts')) return jsonResponse([{ name: 'Test District' }]);
    if (parsed.pathname.endsWith('/cities')) return jsonResponse([{ name: 'Test City' }]);
    if (parsed.pathname.endsWith('/doctors')) return jsonResponse([{
      id: 9, doctor_name: 'Synthetic Test Doctor', specialty: 'Test only', verification_status: 'verified',
    }]);
    return jsonResponse([{
      id: 7, hospital_name: 'Synthetic Test Clinic', state: 'Test State', district: 'Test District',
      city: 'Test City', source_type: 'admin_uploaded',
    }]);
  };
  const page = buildPage(fetchImpl);
  await flush();

  const state = page.get('#location-state');
  const district = page.get('#location-district');
  const city = page.get('#location-city');
  const hospital = page.get('#location-hospital');
  const doctor = page.get('#location-doctor');
  assert.equal(state.children[1].textContent, 'Test State');

  state.value = 'Test State';
  await state.dispatch('change');
  assert.equal(district.children[1].textContent, 'Test District');
  district.value = 'Test District';
  await district.dispatch('change');
  assert.equal(city.children[1].textContent, 'Test City');
  city.value = 'Test City';
  await city.dispatch('change');
  assert.equal(hospital.children[1].textContent, 'Synthetic Test Clinic');
  hospital.value = '7';
  await hospital.dispatch('change');
  assert.match(doctor.children[1].textContent, /NMC checked/);
  assert.ok(calls.some((url) => url.includes('state=Test+State')));

  state.value = '';
  await state.dispatch('change');
  assert.equal(district.disabled, true);
  assert.equal(city.disabled, true);
  assert.equal(hospital.disabled, true);
  assert.equal(doctor.disabled, true);
});

test('empty hospitals and malformed API JSON produce useful statuses', async () => {
  let malformed = false;
  const fetchImpl = async (url) => {
    const parsed = new URL(url, 'http://localhost');
    if (parsed.pathname.endsWith('/states')) return jsonResponse([{ name: 'Test State' }]);
    if (parsed.pathname.endsWith('/districts')) return jsonResponse([{ name: 'Test District' }]);
    if (parsed.pathname.endsWith('/cities')) return jsonResponse([{ name: 'Test City' }]);
    if (parsed.pathname.endsWith('/hospitals')) return jsonResponse([]);
    if (malformed) return { ok: true, json: async () => ({ wrong: [] }) };
    return jsonResponse([]);
  };
  const page = buildPage(fetchImpl);
  await flush();
  const state = page.get('#location-state');
  const district = page.get('#location-district');
  const city = page.get('#location-city');
  const status = page.get('#directory-status');
  state.value = 'Test State'; await state.dispatch('change');
  district.value = 'Test District'; await district.dispatch('change');
  city.value = 'Test City'; await city.dispatch('change');
  assert.match(status.textContent, /No hospitals are listed/);
  assert.equal(page.get('#location-hospital').disabled, true);

  malformed = true;
  page.get('#location-hospital').value = '7';
  await page.get('#location-hospital').dispatch('change');
  assert.match(status.textContent, /missing its items list/);
});
