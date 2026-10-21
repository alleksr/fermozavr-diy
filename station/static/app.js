"use strict";

// A 12-column dashboard. Phrases still come from /api/state and decisions.py.
// value ≈ query value, timeseries ≈ timeseries, journal ≈ table, note ≈ note.
// The time range filters graphs and the journal. Frost and the spray phrase stay live.

const LAYOUT_KEY = "fvz-dashboard-v2";
const CHART_GAP_MS = 3 * 60 * 60 * 1000;
const INKS = ["#4c78d8", "#e07a3d", "#2f9e6b", "#7b5ea7"];
const SVG_NS = "http://www.w3.org/2000/svg";
const RANGE_MS = { "1h": 3600000, "4h": 14400000, "12h": 43200000, "1d": 86400000 };
const WIDTHS = [3, 4, 6, 8, 12];
const HEIGHTS = [2, 3, 4, 5, 6];

const QUANTITY_UNITS = {
  air_temperature: "celsius",
  relative_humidity: "percent_rh",
  reference_temperature: "celsius",
};

const QUANTITY_LABELS = {
  air_temperature: "температура воздуха",
  relative_humidity: "относительная влажность",
  reference_temperature: "температура опоры",
};

const UNIT_LABELS = { celsius: "°C", percent_rh: "%" };

const WIDGET_TYPES = [
  ["value", "Показание", "Одно число на плитке", { w: 4, h: 2, quantity: "air_temperature", sensor: "", accent: "green" }],
  ["timeseries", "График", "Кривые. На одной шкале одна единица", { w: 8, h: 4, series: [], dual: false, seriesSet: false }],
  ["journal", "Журнал", "Строки как пришли, вместе с сотыми", { w: 12, h: 4 }],
  ["frost", "Заморозок", "Фраза про ночную полосу", { w: 6, h: 5 }],
  ["spray", "Окно обработки", "Попало ли показание в вашу полосу", { w: 6, h: 6 }],
  ["note", "Заметка", "Свой текст на доске", { w: 4, h: 2, text: "" }],
];

const BAND_FIELDS = [
  ["spray_temp_min", "temp_min", "Температура от, °C"],
  ["spray_temp_max", "temp_max", "Температура до, °C"],
  ["spray_rh_min", "rh_min", "Влажность от, %"],
  ["spray_rh_max", "rh_max", "Влажность до, %"],
];

function defaultLayout() {
  return {
    title: "Узел T/RH",
    range: "12h",
    nextId: 10,
    widgets: [
      { id: "temp", type: "value", title: "Температура воздуха", w: 4, h: 2, quantity: "air_temperature", sensor: "", accent: "green" },
      { id: "rh", type: "value", title: "Влажность", w: 4, h: 2, quantity: "relative_humidity", sensor: "", accent: "" },
      { id: "ref", type: "value", title: "Температура опоры", w: 4, h: 2, quantity: "reference_temperature", sensor: "", accent: "" },
      { id: "frost", type: "frost", title: "Заморозок", w: 6, h: 5 },
      { id: "spray", type: "spray", title: "Окно обработки", w: 6, h: 6 },
      { id: "chart", type: "timeseries", title: "Температура", w: 12, h: 5, series: [], dual: false, seriesSet: false },
      { id: "journal", type: "journal", title: "Журнал", w: 12, h: 4 },
    ],
  };
}

let layout = defaultLayout();
let dashboards = [];
let editing = false;
let lastState = null;
let lastRows = [];
let renderToken = 0;
let lastSignature = "";
let editorDraft = null;
let saveTimer = 0;
let saveSeq = 0;

function loadLayout() {
  return defaultLayout();
}

function saveLayout() {
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => { flushLayout(); }, 200);
}

async function flushLayout() {
  window.clearTimeout(saveTimer);
  if (!layout.id) return null;
  const seq = ++saveSeq;
  const ident = layout.id;
  const response = await fetch("/api/dashboards/" + ident, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: layout.title,
      range: layout.range,
      nextId: layout.nextId,
      widgets: layout.widgets,
    }),
  });
  const body = await readJson(response);
  if (seq !== saveSeq) return body;
  if (!response.ok) {
    setPageStatus(body.error || "Дашборд не сохранился", "bad");
    return body;
  }
  if (Array.isArray(body.dashboards)) dashboards = body.dashboards;
  renderMenu();
  return body;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  return node;
}

function button(text, className, onClick) {
  const node = el("button", className, text);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

function comma(value, digits) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  let text = number.toFixed(digits);
  if (text.startsWith("-")) text = "−" + text.slice(1);
  return text.replace(".", ",");
}

function formatValue(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  const trimmed = number.toFixed(4).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
  const signed = trimmed.startsWith("-") ? "−" + trimmed.slice(1) : trimmed;
  return signed.replace(".", ",");
}

function formatQuantity(value, quantity) {
  if (quantity === "relative_humidity") return comma(value, 0) + " %";
  return comma(value, 1) + " °C";
}

function formatTime(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).format(date);
}

function formatClock(ts, span) {
  const options = span > 18 * 60 * 60 * 1000
    ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }
    : { hour: "2-digit", minute: "2-digit" };
  return new Intl.DateTimeFormat("ru-RU", options).format(new Date(ts));
}

function unitLabel(unit) {
  return UNIT_LABELS[unit] || unit;
}

function inRange(iso) {
  if (layout.range === "all") return true;
  const span = RANGE_MS[layout.range];
  const time = Date.parse(iso);
  return Number.isFinite(time) && Date.now() - time <= span;
}

function ranged(rows) {
  return rows.filter((row) => inRange(row.observed_at));
}

async function readJson(response) {
  try {
    return await response.json();
  } catch (error) {
    return {};
  }
}

function setPageStatus(text, kind) {
  const status = document.querySelector("#page-status");
  status.textContent = text || "";
  status.className = "banner" + (kind ? " " + kind : "");
}

async function postSettings(payload) {
  const response = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await readJson(response);
  if (!response.ok) {
    setPageStatus(body.error || "Настройка не сохранилась", "bad");
    return;
  }
  setPageStatus("", "");
  await refresh(true);
}

function stopWheel(input) {
  input.addEventListener("wheel", (event) => event.preventDefault(), { passive: false });
}

function numberOrNull(form, name) {
  const raw = String(form.elements[name].value || "").trim();
  if (!raw) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function addFact(list, name, value) {
  const item = el("div", "fact");
  item.append(el("dt", null, name), el("dd", null, value));
  list.append(item);
}

function renderPeople(title, rows, withDelta) {
  const wrap = el("div");
  wrap.append(el("p", "subhead", title));
  const list = el("ul", "plain");
  for (const row of rows) {
    let text = row.sensor_id + ": " + row.temperature;
    if (withDelta && row.delta) text += " · ход от выбранного " + row.delta;
    list.append(el("li", null, text));
  }
  wrap.append(list);
  return wrap;
}

function renderPicker(state) {
  const label = el("label", "picker");
  label.append(document.createTextNode("Экземпляр для решения"));
  const select = document.createElement("select");
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "не выбран";
  select.append(empty);
  const seen = new Set();
  for (const sensor of state.sensors || []) {
    if (seen.has(sensor.sensor_id)) continue;
    seen.add(sensor.sensor_id);
    const option = document.createElement("option");
    option.value = sensor.sensor_id;
    option.textContent = sensor.sensor_id;
    if (sensor.sensor_id === state.decision_sensor_id) option.selected = true;
    select.append(option);
  }
  let ignore = true;
  select.addEventListener("change", () => {
    if (ignore) return;
    postSettings({ decision_sensor_id: select.value || null });
  });
  label.append(select);
  setTimeout(() => { ignore = false; }, 0);
  return label;
}

function ruleFrost(bars) {
  return (
    "Ночная полоса от " + comma(bars.frost_low_c, 1) + " до +" + comma(bars.frost_high_c, 1) +
    " °C. Планка " + comma(bars.temperature_c, 1) + " °C. Ход за " + bars.trend_minutes +
    " минут. Падение меньше планки падением не считаем."
  );
}

function renderFrost(state) {
  const frost = state.frost || {};
  const wrap = el("div");
  const phrase = el("h3", "phrase " + (frost.tone || "quiet"), frost.title || "Нет фразы");
  phrase.title = "Имя в программе: " + (frost.code || "—");
  const showNumber = Boolean(frost.facts && frost.facts.now) && frost.code !== "stale";
  if (showNumber) {
    wrap.append(el("p", "reading-value", frost.facts.now));
    phrase.classList.add("caption");
  }
  wrap.append(phrase, el("p", "detail", frost.detail || ""));
  if (frost.at_time_title) {
    const past = el("div", "past");
    past.append(
      el("p", "subhead", "В момент этой строки"),
      el("p", "detail", frost.at_time_title),
      el("p", "detail", frost.at_time_detail || ""),
    );
    wrap.append(past);
  }
  if (frost.facts) {
    const facts = el("dl", "facts");
    if (!showNumber && frost.facts.now) addFact(facts, "Сейчас", frost.facts.now);
    addFact(facts, "Экземпляр", frost.facts.sensor_id);
    addFact(facts, "40 минут назад", frost.facts.then || "нет строки");
    addFact(facts, "Ход", frost.facts.delta || "нет");
    wrap.append(facts);
  }
  if (Array.isArray(frost.sensors) && frost.sensors.length) wrap.append(renderPeople("Свежие показания", frost.sensors, false));
  if (Array.isArray(frost.neighbors) && frost.neighbors.length) wrap.append(renderPeople("Рядом, в те же минуты", frost.neighbors, true));
  if (state.bars) wrap.append(el("p", "rule", ruleFrost(state.bars)));
  wrap.append(renderPicker(state));
  return wrap;
}

function ruleSpray(bars) {
  return (
    "Полосу задаёте вы. Если она уже " + comma(bars.temperature_c * 2, 1) +
    " °C или " + comma(bars.humidity_rh * 2, 0) +
    " % влажности, внутри и снаружи её не различить. Выше " +
    comma(bars.saturation_rh, 0) + " % — около насыщения."
  );
}

function renderBandForm(state) {
  const band = state.spray_band || {};
  const form = el("form", "band");
  form.autocomplete = "off";
  for (const [name, key, labelText] of BAND_FIELDS) {
    const label = el("label");
    label.append(document.createTextNode(labelText));
    const input = document.createElement("input");
    input.type = "number";
    input.step = "any";
    input.name = name;
    input.inputMode = "decimal";
    if (band[key] != null) input.value = String(band[key]);
    stopWheel(input);
    label.append(input);
    form.append(label);
  }
  const actions = el("div", "dialog-actions full");
  const submit = el("button", "primary", "Запомнить полосу");
  submit.type = "submit";
  actions.append(submit, button("Стереть полосу", "quiet", () => {
    postSettings({ spray_temp_min: null, spray_temp_max: null, spray_rh_min: null, spray_rh_max: null });
  }));
  form.append(actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    postSettings({
      spray_temp_min: numberOrNull(form, "spray_temp_min"),
      spray_temp_max: numberOrNull(form, "spray_temp_max"),
      spray_rh_min: numberOrNull(form, "spray_rh_min"),
      spray_rh_max: numberOrNull(form, "spray_rh_max"),
    });
  });
  return form;
}

function renderSpray(state) {
  const spray = state.spray || {};
  const wrap = el("div");
  const phrase = el("h3", "phrase " + (spray.tone || "quiet"), spray.title || "Нет фразы");
  phrase.title = "Имя в программе: " + (spray.code || "—");
  wrap.append(phrase, el("p", "detail", spray.detail || ""));
  if (spray.code === "band_incomplete") {
    wrap.append(el("p", "detail", "Четыре края. Пока они пустые, экран не подставляет обычную полосу."));
  }
  wrap.append(renderBandForm(state));
  if (state.bars) wrap.append(el("p", "rule", ruleSpray(state.bars)));
  return wrap;
}

function resolveSensor(widget, rows) {
  if (widget.sensor) return widget.sensor;
  const matching = rows.filter((row) => row.quantity === widget.quantity);
  const decision = lastState && lastState.decision_sensor_id;
  if (decision && matching.some((row) => row.sensor_id === decision)) return decision;
  return matching.length ? matching[matching.length - 1].sensor_id : "";
}

function latestPoint(rows, sensor, quantity) {
  let found = null;
  for (const row of rows) {
    if (row.sensor_id === sensor && row.quantity === quantity) found = row;
  }
  return found;
}

function renderValue(widget, rows) {
  const wrap = el("div", "kpi");
  const sensor = resolveSensor(widget, rows);
  const point = sensor ? latestPoint(rows, sensor, widget.quantity) : null;
  wrap.append(el("p", "kpi-label", (sensor || "экземпляр не выбран") + " · " + (QUANTITY_LABELS[widget.quantity] || widget.quantity)));
  if (!point) {
    wrap.append(el("p", "kpi-value", "—"), el("p", "kpi-sub", "В этом окне строки нет"));
    return wrap;
  }
  wrap.append(el("p", "kpi-value", formatQuantity(point.value, widget.quantity)));
  const bits = [formatTime(point.observed_at)];
  const staleMinutes = lastState && lastState.bars ? lastState.bars.stale_minutes : 3;
  if (Date.now() - Date.parse(point.observed_at) > staleMinutes * 60 * 1000) bits.push("устарело");
  wrap.append(el("p", "kpi-sub", bits.join(" · ")));
  return wrap;
}

function renderJournal(rows) {
  const wrap = el("div");
  const visible = ranged(rows).slice().reverse().slice(0, 40);
  if (!visible.length) {
    wrap.append(el("p", "detail", "В этом окне журнал пуст. Запись ниже ляжет сюда целиком, вместе с сотыми."));
    return wrap;
  }
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const name of ["Время", "Экземпляр", "Величина", "Число", "Опыт", "Заметка"]) head.append(el("th", null, name));
  const thead = document.createElement("thead");
  thead.append(head);
  const tbody = document.createElement("tbody");
  for (const row of visible) {
    const line = document.createElement("tr");
    const cells = [
      formatTime(row.observed_at),
      row.sensor_id,
      QUANTITY_LABELS[row.quantity] || row.quantity,
      formatValue(row.value) + " " + unitLabel(row.unit),
      row.experiment || "",
      row.note || "",
    ];
    for (const cell of cells) line.append(el("td", null, cell));
    tbody.append(line);
  }
  table.append(thead, tbody);
  wrap.append(table);
  return wrap;
}

function collectSeries(rows) {
  const map = new Map();
  for (const row of rows) {
    const key = row.sensor_id + "\t" + row.quantity;
    if (!map.has(key)) {
      map.set(key, { key, sensor_id: row.sensor_id, quantity: row.quantity, unit: row.unit, points: [] });
    }
    const time = Date.parse(row.observed_at);
    if (!Number.isFinite(time) || !Number.isFinite(Number(row.value))) continue;
    map.get(key).points.push({ t: time, v: Number(row.value) });
  }
  for (const series of map.values()) series.points.sort((a, b) => a.t - b.t);
  return [...map.values()].filter((series) => series.points.length);
}

function seriesLabel(series) {
  return series.sensor_id + " · " + (QUANTITY_LABELS[series.quantity] || series.quantity);
}

function splitSeries(widget, available) {
  const selected = (widget.series || [])
    .map((key) => available.find((series) => series.key === key))
    .filter(Boolean);
  const units = [...new Set(selected.map((series) => series.unit))];
  if (units.length <= 1) return { left: selected, right: [], conflict: false };
  if (widget.dual && units.length === 2) {
    return {
      left: selected.filter((series) => series.unit === units[0]),
      right: selected.filter((series) => series.unit === units[1]),
      conflict: false,
    };
  }
  const first = selected[0].unit;
  return {
    left: selected.filter((series) => series.unit === first),
    right: [],
    conflict: selected.some((series) => series.unit !== first),
  };
}

function svg(name, attrs) {
  const node = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

function svgText(x, y, text, anchor) {
  const node = svg("text", { x, y, "text-anchor": anchor || "start" });
  node.textContent = text;
  return node;
}

function extent(points) {
  let min = Infinity;
  let max = -Infinity;
  for (const point of points) {
    if (point.v < min) min = point.v;
    if (point.v > max) max = point.v;
  }
  if (!Number.isFinite(min)) return { min: 0, max: 1 };
  if (min === max) return { min: min - 1, max: max + 1 };
  const pad = (max - min) * 0.12;
  return { min: min - pad, max: max + pad };
}

function segmentsOf(points) {
  const groups = [];
  let current = [];
  for (const point of points) {
    const prev = current[current.length - 1];
    if (prev && point.t - prev.t > CHART_GAP_MS) {
      groups.push(current);
      current = [];
    }
    current.push(point);
  }
  if (current.length) groups.push(current);
  return groups;
}

function axisDigits(unit, span) {
  if (unit === "percent_rh") return 0;
  if (span > 20) return 0;
  return 1;
}

function drawChart(left, right) {
  const width = 640;
  const height = 260;
  const padLeft = 48;
  const padRight = right.length ? 48 : 16;
  const padTop = 12;
  const padBottom = 28;
  const all = left.concat(right);
  const times = all.flatMap((series) => series.points.map((point) => point.t));
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  const span = t1 - t0;
  const plotWidth = width - padLeft - padRight;
  const plotHeight = height - padTop - padBottom;
  const xOf = (time) => (t1 === t0 ? padLeft + plotWidth / 2 : padLeft + ((time - t0) / (t1 - t0)) * plotWidth);
  const picture = svg("svg", { viewBox: "0 0 " + width + " " + height, role: "img" });
  const title = svg("title", {});
  title.textContent = all.map(seriesLabel).join(". ");
  picture.append(title, svg("path", {
    d: "M " + padLeft + " " + padTop + " V " + (height - padBottom) + " H " + (width - padRight),
    fill: "none",
    stroke: "#e1e4e8",
  }));
  function paint(seriesList, side) {
    const points = seriesList.flatMap((series) => series.points);
    const range = extent(points);
    const dataSpan = Math.max(...points.map((point) => point.v)) - Math.min(...points.map((point) => point.v));
    const digits = axisDigits(seriesList[0].unit, dataSpan);
    const yOf = (value) => padTop + (1 - (value - range.min) / (range.max - range.min)) * plotHeight;
    for (let step = 0; step < 3; step += 1) {
      const value = range.min + ((range.max - range.min) * step) / 2;
      const y = yOf(value);
      picture.append(svgText(side === "left" ? padLeft - 6 : width - padRight + 6, y + 4, comma(value, digits), side === "left" ? "end" : "start"));
    }
    return seriesList.map((series, index) => {
      const ink = INKS[(side === "left" ? index : left.length + index) % INKS.length];
      for (const group of segmentsOf(series.points)) {
        if (group.length >= 2) {
          picture.append(svg("polyline", {
            points: group.map((point) => xOf(point.t).toFixed(1) + "," + yOf(point.v).toFixed(1)).join(" "),
            fill: "none",
            stroke: ink,
            "stroke-width": "1.8",
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
          }));
        } else {
          picture.append(svg("circle", { cx: xOf(group[0].t).toFixed(1), cy: yOf(group[0].v).toFixed(1), r: "3", fill: ink }));
        }
      }
      return { series, ink };
    });
  }
  const legend = [];
  if (left.length) legend.push(...paint(left, "left"));
  if (right.length) legend.push(...paint(right, "right"));
  picture.append(svgText(padLeft, height - 8, formatClock(t0, span), "start"));
  if (t1 !== t0) picture.append(svgText(width - padRight, height - 8, formatClock(t1, span), "end"));
  return { picture, legend };
}

function maybeBindChart(widget, available) {
  if (widget.seriesSet) return;
  const temps = available.filter((series) => series.unit === "celsius");
  if (!temps.length) return;
  widget.series = temps.map((series) => series.key);
  widget.seriesSet = true;
  saveLayout();
}

function renderTimeseries(widget, rows) {
  const wrap = el("div");
  const available = collectSeries(ranged(rows));
  maybeBindChart(widget, available);
  const parts = splitSeries(widget, available);
  if (!parts.left.length && !parts.right.length) {
    wrap.append(el("p", "detail", available.length
      ? "Кривые не выбраны. В режиме правки откройте настройку карточки."
      : "В этом окне точек нет."));
    return wrap;
  }
  const drawn = drawChart(parts.left, parts.right);
  wrap.append(drawn.picture);
  const legend = el("ul", "legend");
  for (const item of drawn.legend) {
    const line = el("li");
    const swatch = el("span", "swatch");
    swatch.style.background = item.ink;
    line.append(swatch, document.createTextNode(seriesLabel(item.series) + ", " + unitLabel(item.series.unit)));
    legend.append(line);
  }
  wrap.append(legend);
  if (parts.conflict || widget.pending) {
    wrap.append(el("p", "detail", "На одной шкале одна единица. В настройке карточки можно включить вторую ось или второй график."));
  }
  return wrap;
}

function renderNote(widget) {
  const wrap = el("div");
  wrap.append(el("p", "note-text", widget.text || "Пустая заметка. Текст задаётся в настройке карточки."));
  return wrap;
}

function renderWidgetBody(widget, state, rows) {
  if (widget.type === "frost") return renderFrost(state || {});
  if (widget.type === "spray") return renderSpray(state || {});
  if (widget.type === "value") return renderValue(widget, ranged(rows));
  if (widget.type === "timeseries") return renderTimeseries(widget, rows);
  if (widget.type === "journal") return renderJournal(rows);
  if (widget.type === "note") return renderNote(widget);
  return el("p", "detail", "Неизвестная карточка");
}

function applyFrame(node, widget) {
  node.style.gridColumn = "span " + Math.min(12, Math.max(2, widget.w || 4));
  node.style.gridRow = "span " + Math.min(8, Math.max(2, widget.h || 2));
  if (widget.type === "value" && widget.accent) node.dataset.accent = widget.accent;
  else delete node.dataset.accent;
  node.querySelector("h2").textContent = widget.title || "";
}

function moveWidget(id, beforeId) {
  const list = layout.widgets;
  const from = list.findIndex((widget) => widget.id === id);
  if (from < 0) return;
  const item = list.splice(from, 1)[0];
  const to = list.findIndex((widget) => widget.id === beforeId);
  list.splice(to < 0 ? list.length : to, 0, item);
  saveLayout();
  const canvas = document.querySelector("#canvas");
  for (const widget of list) {
    const node = canvas.querySelector('[data-id="' + widget.id + '"]');
    if (node) canvas.appendChild(node);
  }
}

function bindGrip(handle, id) {
  handle.addEventListener("pointerdown", (event) => {
    if (!editing) return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    const widgetNode = handle.closest(".widget");
    widgetNode.classList.add("dragging");
    let last = "";
    function move(ev) {
      const under = document.elementFromPoint(ev.clientX, ev.clientY);
      const target = under && under.closest(".widget");
      if (!target || target.dataset.id === id || target.dataset.id === last) return;
      last = target.dataset.id;
      moveWidget(id, target.dataset.id);
    }
    function up() {
      widgetNode.classList.remove("dragging");
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
    }
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
  });
}

function bindResize(handle, id) {
  handle.addEventListener("pointerdown", (event) => {
    if (!editing) return;
    event.preventDefault();
    handle.setPointerCapture(event.pointerId);
    const widget = layout.widgets.find((item) => item.id === id);
    const node = handle.closest(".widget");
    const canvas = document.querySelector("#canvas");
    const column = canvas.getBoundingClientRect().width / 12;
    const startX = event.clientX;
    const startY = event.clientY;
    const startW = widget.w;
    const startH = widget.h;
    function move(ev) {
      widget.w = Math.min(12, Math.max(2, Math.round(startW + (ev.clientX - startX) / column)));
      widget.h = Math.min(8, Math.max(2, Math.round(startH + (ev.clientY - startY) / 80)));
      applyFrame(node, widget);
    }
    function up() {
      saveLayout();
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
    }
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
  });
}

function buildWidget(widget) {
  const node = el("article", "widget");
  node.dataset.id = widget.id;
  const bar = el("div", "widget-bar");
  const tools = el("div", "widget-tools");
  const grip = button("тащить", "tool", () => {});
  grip.setAttribute("aria-label", "Перетащить карточку");
  bindGrip(grip, widget.id);
  tools.append(
    grip,
    button("настроить", "tool", () => openEditor(widget.id)),
    button("убрать", "tool", () => removeWidget(widget.id)),
  );
  bar.append(tools, el("h2", null, widget.title || ""));
  const resize = el("button", "resize");
  resize.type = "button";
  resize.setAttribute("aria-label", "Изменить размер");
  bindResize(resize, widget.id);
  node.append(bar, el("div", "widget-body"), resize);
  return node;
}

function removeWidget(id) {
  layout.widgets = layout.widgets.filter((widget) => widget.id !== id);
  saveLayout();
  const node = document.querySelector('#canvas [data-id="' + id + '"]');
  if (node) node.remove();
}

function renderAll(state, rows) {
  const canvas = document.querySelector("#canvas");
  const byId = new Map([...canvas.children].map((node) => [node.dataset.id, node]));
  const ids = new Set(layout.widgets.map((widget) => widget.id));
  for (const [id, node] of byId) {
    if (!ids.has(id)) node.remove();
  }
  for (const widget of layout.widgets) {
    let node = byId.get(widget.id);
    if (!node) {
      node = buildWidget(widget);
      canvas.appendChild(node);
    } else {
      canvas.appendChild(node);
    }
    applyFrame(node, widget);
    const body = node.querySelector(".widget-body");
    const focused = document.activeElement && body.contains(document.activeElement);
    if (focused) continue;
    body.replaceChildren(renderWidgetBody(widget, state, rows));
  }
}

function syncChrome() {
  document.body.classList.toggle("is-editing", editing);
  document.querySelector("#toggle-edit").textContent = editing ? "Готово" : "Править";
  document.querySelector("#add-widget").hidden = !editing;
  document.querySelector("#reset-layout").hidden = !editing;
  document.querySelector("#delete-dashboard").hidden = !(editing && dashboards.length > 1);
  const title = document.querySelector("#dash-title");
  title.readOnly = !editing;
  title.value = layout.title;
  for (const buttonNode of document.querySelectorAll(".range button")) {
    buttonNode.setAttribute("aria-pressed", buttonNode.dataset.range === layout.range ? "true" : "false");
  }
  renderMenu();
}

function renderMenu() {
  const host = document.querySelector("#dashboard-list");
  host.replaceChildren();
  for (const item of dashboards) {
    const node = button(item.title, "dash", () => { openDashboard(item.id); });
    if (item.id === layout.id) node.setAttribute("aria-current", "page");
    host.append(node);
  }
}

function applyDocument(doc) {
  const fresh = defaultLayout();
  layout = {
    id: doc.id,
    title: typeof doc.title === "string" && doc.title.trim() ? doc.title.trim() : fresh.title,
    range: doc.range || fresh.range,
    nextId: doc.nextId || fresh.nextId,
    widgets: Array.isArray(doc.widgets) && doc.widgets.length ? doc.widgets : fresh.widgets,
  };
}

async function maybeMigrate(activeId) {
  if (localStorage.getItem("fvz-dashboard-migrated")) return;
  const raw = localStorage.getItem(LAYOUT_KEY);
  localStorage.setItem("fvz-dashboard-migrated", "1");
  if (!raw || !activeId) return;
  let saved = null;
  try {
    saved = JSON.parse(raw);
  } catch (error) {
    return;
  }
  if (!saved || !Array.isArray(saved.widgets) || !saved.widgets.length) return;
  await fetch("/api/dashboards/" + activeId, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: saved.title || "Узел T/RH",
      range: saved.range || "12h",
      nextId: saved.nextId || 10,
      widgets: saved.widgets,
    }),
  });
}

async function loadFromServer() {
  const listResponse = await fetch("/api/dashboards");
  const list = await readJson(listResponse);
  if (!listResponse.ok) throw new Error(list.error || "list");
  await maybeMigrate(list.active);
  const docResponse = await fetch("/api/dashboards/" + list.active);
  const doc = await readJson(docResponse);
  if (!docResponse.ok) throw new Error(doc.error || "dashboard");
  applyDocument(doc);
  const again = await fetch("/api/dashboards");
  const listed = await readJson(again);
  dashboards = again.ok && Array.isArray(listed.dashboards) ? listed.dashboards : [];
  renderMenu();
  syncChrome();
}

async function openDashboard(id) {
  if (!id || id === layout.id) return;
  await flushLayout();
  const response = await fetch("/api/dashboards/active", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id }),
  });
  const body = await readJson(response);
  if (!response.ok) {
    setPageStatus(body.error || "Дашборд не открылся", "bad");
    return;
  }
  dashboards = body.dashboards || dashboards;
  applyDocument(body.dashboard);
  document.querySelector("#canvas").replaceChildren();
  lastSignature = "";
  renderMenu();
  syncChrome();
  await refresh(true);
}

async function createDashboard() {
  await flushLayout();
  const response = await fetch("/api/dashboards", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "Новый дашборд" }),
  });
  const body = await readJson(response);
  if (!response.ok) {
    setPageStatus(body.error || "Дашборд не создался", "bad");
    return;
  }
  dashboards = body.dashboards || dashboards;
  applyDocument(body.dashboard);
  document.querySelector("#canvas").replaceChildren();
  lastSignature = "";
  editing = true;
  renderMenu();
  syncChrome();
  await refresh(true);
}

async function removeCurrentDashboard() {
  if (!layout.id || dashboards.length < 2) return;
  if (!window.confirm("Удалить дашборд «" + layout.title + "»? Журнал показаний останется.")) return;
  const response = await fetch("/api/dashboards/" + layout.id, { method: "DELETE" });
  const body = await readJson(response);
  if (!response.ok) {
    setPageStatus(body.error || "Дашборд не удалился", "bad");
    return;
  }
  dashboards = body.dashboards || dashboards;
  applyDocument(body.dashboard);
  document.querySelector("#canvas").replaceChildren();
  lastSignature = "";
  renderMenu();
  syncChrome();
  await refresh(true);
}

function addWidget(type) {
  const spec = WIDGET_TYPES.find((item) => item[0] === type);
  if (!spec) return;
  layout.nextId += 1;
  const widget = Object.assign({ id: "w" + layout.nextId, type, title: spec[1] }, JSON.parse(JSON.stringify(spec[3])));
  layout.widgets.push(widget);
  saveLayout();
  document.querySelector("#picker").close();
  refresh(true);
}

function openPicker() {
  const list = document.querySelector("#picker-list");
  list.replaceChildren();
  for (const [type, title, blurb] of WIDGET_TYPES) {
    const item = button("", "picker-item", () => addWidget(type));
    item.append(el("strong", null, title), el("span", null, blurb));
    list.append(item);
  }
  document.querySelector("#picker").showModal();
}

function choiceRow(host, values, current, onPick) {
  host.replaceChildren();
  for (const value of values) {
    const node = button(String(value), "", () => {
      onPick(value);
      choiceRow(host, values, value, onPick);
    });
    node.setAttribute("aria-pressed", value === current ? "true" : "false");
    host.append(node);
  }
}

function sensorOptions() {
  const ids = [];
  for (const row of lastRows) {
    if (!ids.includes(row.sensor_id)) ids.push(row.sensor_id);
  }
  return ids;
}

function fillEditor(draft) {
  const form = document.querySelector("#editor-form");
  form.elements.title.value = draft.title || "";
  choiceRow(document.querySelector("#editor-width"), WIDTHS, draft.w, (value) => { draft.w = value; });
  choiceRow(document.querySelector("#editor-height"), HEIGHTS, draft.h, (value) => { draft.h = value; });
  const extra = document.querySelector("#editor-extra");
  extra.replaceChildren();
  if (draft.type === "value") {
    const sensorLabel = el("label", "span-2");
    sensorLabel.append(document.createTextNode("Экземпляр. Пусто — тот, что выбран для решения"));
    const sensor = document.createElement("select");
    sensor.append(new Option("как для решения", ""));
    for (const id of sensorOptions()) sensor.append(new Option(id, id));
    sensor.value = draft.sensor || "";
    sensor.addEventListener("change", () => { draft.sensor = sensor.value; });
    sensorLabel.append(sensor);
    const quantityLabel = el("label", "span-2");
    quantityLabel.append(document.createTextNode("Величина"));
    const quantity = document.createElement("select");
    for (const [value, label] of Object.entries(QUANTITY_LABELS)) quantity.append(new Option(label, value));
    quantity.value = draft.quantity || "air_temperature";
    quantity.addEventListener("change", () => { draft.quantity = quantity.value; });
    quantityLabel.append(quantity);
    const accent = el("div", "choice");
    const accents = [["", "обычная"], ["green", "зелёная"], ["amber", "янтарная"]];
    function paintAccents() {
      accent.replaceChildren();
      for (const [value, label] of accents) {
        const node = button(label, "", () => { draft.accent = value; paintAccents(); });
        node.setAttribute("aria-pressed", draft.accent === value ? "true" : "false");
        accent.append(node);
      }
    }
    paintAccents();
    extra.append(sensorLabel, quantityLabel, el("p", "hint", "Цвет плитки"), accent);
  }
  if (draft.type === "note") {
    const label = el("label", "span-2");
    label.append(document.createTextNode("Текст"));
    const area = document.createElement("textarea");
    area.value = draft.text || "";
    area.addEventListener("input", () => { draft.text = area.value; });
    label.append(area);
    extra.append(label);
  }
  if (draft.type === "timeseries") fillChartEditor(extra, draft);
}

function fillChartEditor(extra, draft) {
  const available = collectSeries(ranged(lastRows));
  extra.replaceChildren();
  extra.append(el("p", "hint span-2", "Кривые. Градусы с градусами, проценты с процентами."));
  if (!available.length) {
    extra.append(el("p", "detail span-2", "В этом окне точек нет."));
    return;
  }
  const list = el("div", "series-list span-2");
  for (const series of available) {
    const label = el("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = (draft.series || []).includes(series.key);
    input.addEventListener("change", () => {
      toggleDraftSeries(draft, series.key, available);
      fillChartEditor(extra, draft);
    });
    label.append(input, document.createTextNode(seriesLabel(series)));
    list.append(label);
  }
  extra.append(list);
  const parts = splitSeries(draft, available);
  if (parts.conflict || draft.pending) {
    const offer = el("div", "offer span-2");
    offer.append(el("p", "detail", "На одной шкале одна единица. Можно вторую ось или второй график."));
    const actions = el("div", "dialog-actions");
    actions.append(
      button("Вторая ось", "quiet", () => {
        draft.dual = true;
        if (draft.pending && !(draft.series || []).includes(draft.pending)) draft.series.push(draft.pending);
        draft.pending = null;
        fillChartEditor(extra, draft);
      }),
      button("Второй график", "quiet", () => {
        const key = draft.pending;
        draft.pending = null;
        layout.nextId += 1;
        layout.widgets.push({
          id: "w" + layout.nextId,
          type: "timeseries",
          title: "Второй график",
          w: 6,
          h: 4,
          series: key ? [key] : [],
          dual: false,
          seriesSet: true,
        });
        saveLayout();
        fillChartEditor(extra, draft);
        refresh(true);
      }),
    );
    offer.append(actions);
    extra.append(offer);
  }
}

function toggleDraftSeries(draft, key, available) {
  draft.seriesSet = true;
  draft.series = draft.series || [];
  if (draft.series.includes(key)) {
    draft.series = draft.series.filter((item) => item !== key);
    draft.pending = null;
    const units = new Set(draft.series.map((item) => {
      const found = available.find((series) => series.key === item);
      return found ? found.unit : "";
    }));
    if (units.size < 2) draft.dual = false;
    return;
  }
  const adding = available.find((series) => series.key === key);
  const units = new Set(draft.series.map((item) => {
    const found = available.find((series) => series.key === item);
    return found ? found.unit : "";
  }));
  if (adding) units.add(adding.unit);
  if ((units.size > 1 && !draft.dual) || units.size > 2) draft.pending = key;
  else {
    draft.series.push(key);
    draft.pending = null;
  }
}

function openEditor(id) {
  const widget = layout.widgets.find((item) => item.id === id);
  if (!widget) return;
  editorDraft = JSON.parse(JSON.stringify(widget));
  fillEditor(editorDraft);
  document.querySelector("#editor").showModal();
}

function applyEditor(event) {
  event.preventDefault();
  const widget = layout.widgets.find((item) => item.id === editorDraft.id);
  if (!widget) {
    document.querySelector("#editor").close();
    return;
  }
  editorDraft.title = document.querySelector("#editor-form").elements.title.value.trim() || widget.title;
  Object.assign(widget, editorDraft);
  saveLayout();
  document.querySelector("#editor").close();
  editorDraft = null;
  refresh(true);
}

function copyWidget() {
  if (!editorDraft) return;
  layout.nextId += 1;
  const copy = JSON.parse(JSON.stringify(editorDraft));
  copy.id = "w" + layout.nextId;
  copy.title = (copy.title || "Карточка") + " 2";
  const index = layout.widgets.findIndex((widget) => widget.id === editorDraft.id);
  layout.widgets.splice(index + 1, 0, copy);
  saveLayout();
  document.querySelector("#editor").close();
  refresh(true);
}

async function refresh(force) {
  const token = ++renderToken;
  try {
    const [stateResponse, seriesResponse] = await Promise.all([
      fetch("/api/state"),
      fetch("/api/readings?limit=800"),
    ]);
    const state = await readJson(stateResponse);
    const series = await readJson(seriesResponse);
    if (token !== renderToken) return;
    if (!stateResponse.ok) {
      document.querySelector("#load-error").textContent = state.error || "Сервер не отдал экран.";
      return;
    }
    document.querySelector("#load-error").textContent = "";
    const rows = seriesResponse.ok && Array.isArray(series.readings) ? series.readings : [];
    const signature = JSON.stringify(state) + "\n" + JSON.stringify(rows) + "\n" + layout.range;
    if (!force && signature === lastSignature) return;
    lastSignature = signature;
    lastState = state;
    lastRows = rows;
    renderAll(state, rows);
  } catch (error) {
    if (token !== renderToken) return;
    document.querySelector("#load-error").textContent = "Страница не достучалась до сервера.";
  }
}

function toLocalInput(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) +
    "T" + pad(date.getHours()) + ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds());
}

function fromLocalInput(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const pad = (part) => String(Math.trunc(Math.abs(part))).padStart(2, "0");
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) +
    "T" + pad(date.getHours()) + ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds()) +
    sign + pad(Math.trunc(Math.abs(offset) / 60)) + ":" + pad(Math.abs(offset) % 60);
}

async function submitReading(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = document.querySelector("#form-status");
  const quantity = form.elements.quantity.value;
  const value = Number(form.elements.value.value);
  if (!Number.isFinite(value)) {
    status.textContent = "Число не разбирается";
    status.className = "status bad span-2";
    return;
  }
  const payload = {
    node_id: form.elements.node_id.value,
    sensor_id: form.elements.sensor_id.value,
    quantity,
    unit: QUANTITY_UNITS[quantity],
    value,
  };
  const observed = fromLocalInput(form.elements.observed_at.value);
  if (observed) payload.observed_at = observed;
  const experiment = form.elements.experiment.value.trim();
  const note = form.elements.note.value.trim();
  if (experiment) payload.experiment = experiment;
  if (note) payload.note = note;
  const response = await fetch("/api/readings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await readJson(response);
  if (!response.ok) {
    status.textContent = body.error || "Строка не записалась";
    status.className = "status bad span-2";
    return;
  }
  status.textContent = "Строка в журнале";
  status.className = "status ok span-2";
  form.elements.value.value = "";
  form.elements.observed_at.value = "";
  await refresh(true);
}

function init() {
  document.querySelector("#dash-title").addEventListener("change", (event) => {
    layout.title = event.target.value.trim() || "Узел T/RH";
    event.target.value = layout.title;
    const current = dashboards.find((item) => item.id === layout.id);
    if (current) current.title = layout.title;
    saveLayout();
    renderMenu();
  });
  document.querySelector("#toggle-edit").addEventListener("click", () => {
    editing = !editing;
    syncChrome();
  });
  document.querySelector("#add-widget").addEventListener("click", openPicker);
  document.querySelector("#new-dashboard").addEventListener("click", () => { createDashboard(); });
  const nav = document.querySelector("#nav");
  const navToggle = document.querySelector("#nav-toggle");
  function setNavCollapsed(collapsed) {
    nav.classList.toggle("is-collapsed", collapsed);
    navToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    navToggle.textContent = collapsed ? "›" : "‹";
    navToggle.setAttribute("aria-label", collapsed ? "Развернуть меню" : "Свернуть меню");
    localStorage.setItem("fvz-nav-collapsed", collapsed ? "1" : "0");
  }
  navToggle.addEventListener("click", () => setNavCollapsed(!nav.classList.contains("is-collapsed")));
  setNavCollapsed(localStorage.getItem("fvz-nav-collapsed") === "1");
  document.querySelector("#delete-dashboard").addEventListener("click", () => { removeCurrentDashboard(); });
  document.querySelector("#reset-layout").addEventListener("click", () => {
    const ident = layout.id;
    const title = layout.title;
    layout = defaultLayout();
    layout.id = ident;
    layout.title = title;
    saveLayout();
    document.querySelector("#canvas").replaceChildren();
    refresh(true);
  });
  for (const node of document.querySelectorAll(".range button")) {
    node.addEventListener("click", () => {
      layout.range = node.dataset.range;
      saveLayout();
      syncChrome();
      refresh(true);
    });
  }
  document.querySelector("#editor-form").addEventListener("submit", applyEditor);
  document.querySelector("#editor-cancel").addEventListener("click", () => {
    editorDraft = null;
    document.querySelector("#editor").close();
  });
  document.querySelector("#editor-copy").addEventListener("click", copyWidget);
  const form = document.querySelector("#reading-form");
  form.addEventListener("submit", submitReading);
  form.elements.quantity.addEventListener("change", () => {
    const unit = QUANTITY_UNITS[form.elements.quantity.value];
    document.querySelector("#unit-hint").textContent = "Единица в строке: " + unitLabel(unit) + ". Меняется вместе с величиной.";
  });
  document.querySelector("#time-now").addEventListener("click", () => {
    form.elements.observed_at.value = toLocalInput(new Date());
  });
  document.querySelector("#time-40").addEventListener("click", () => {
    form.elements.observed_at.value = toLocalInput(new Date(Date.now() - 40 * 60 * 1000));
  });
  stopWheel(form.elements.value);
  loadFromServer().then(() => {
    refresh(true);
  }).catch(() => {
    document.querySelector("#load-error").textContent = "Дашборды с сервера не прочитались.";
    syncChrome();
    refresh(true);
  });
  setInterval(() => refresh(false), 5000);
}

init();
