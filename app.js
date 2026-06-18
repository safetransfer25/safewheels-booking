const state = {
  token: localStorage.getItem("safewheelsToken"),
  date: localDateIso(),
  viewMode: "day",
  driverFilter: "",
  taxFilter: "",
  activeTab: "bookings",
  bookings: [],
  previousBookings: [],
  monthlyRevenue: null,
  adminDebug: null,
  expenses: [],
  options: {
    vehicles: ["OPEL VIVARO", "PEUGEOT 5008"],
    drivers: ["Θεόδωρος Τσιάμης", "Γεώργιος Τσιάμης", "Ιωάννης Τσιάμης"],
    bookingSources: ["PRIVATE", "WELCOME", "CONNECTO"],
    paymentMethods: ["Μετρητά", "Κάρτα", "Πίστωση"],
    taxStatuses: ["Καταχωρημένο", "Μη Καταχωρημένο"],
    optionDetails: { vehicles: [], drivers: [], sources: [] }
  },
  editingId: null,
  editingExpenseId: null
};

const $ = (selector) => document.querySelector(selector);
const loginScreen = $("#loginScreen");
const app = $("#app");
const bookingDialog = $("#bookingDialog");
const bookingForm = $("#bookingForm");
const expenseDialog = $("#expenseDialog");
const expenseForm = $("#expenseForm");
const selectedDate = $("#selectedDate");
const expenseMonth = $("#expenseMonth");
const revenueYear = $("#revenueYear");
const previousSearchInput = $("#previousSearchInput");

const statusLabels = {
  Pending: "Σε αναμονή",
  Confirmed: "Επιβεβαιωμένη",
  Completed: "Ολοκληρωμένη",
  Cancelled: "Ακυρωμένη"
};
const paymentLabels = {
  Unpaid: "Απλήρωτο",
  Paid: "Πληρωμένο"
};

function taxBadgeLabel(value) {
  return value === "Καταχωρημένο" ? "Καταχωρημένο στην ΑΑΔΕ" : "Μη Καταχωρημένο στην ΑΑΔΕ";
}

init();

function init() {
  selectedDate.value = state.date;
  expenseMonth.value = state.date.slice(0, 7);
  revenueYear.value = new Date(`${state.date}T12:00:00`).getFullYear();
  bindEvents();
  if (state.token) showApp();
}

function bindEvents() {
  $("#loginForm").addEventListener("submit", login);
  $("#logoutBtn").addEventListener("click", logout);
  $("#bookingsTab").addEventListener("click", () => switchTab("bookings"));
  $("#expensesTab").addEventListener("click", () => switchTab("expenses"));
  $("#previousTab").addEventListener("click", () => switchTab("previous"));
  $("#revenueTab").addEventListener("click", () => switchTab("revenue"));
  $("#fleetTab").addEventListener("click", () => switchTab("fleet"));
  $("#prevDay").addEventListener("click", () => changeDay(-1));
  $("#nextDay").addEventListener("click", () => changeDay(1));
  $("#todayBtn").addEventListener("click", () => setDate(localDateIso()));
  selectedDate.addEventListener("change", () => setDate(selectedDate.value));
  $("#dailyPlanBtn").addEventListener("click", () => setViewMode("day"));
  $("#weeklyPlanBtn").addEventListener("click", () => setViewMode("week"));
  $("#monthlyPlanBtn").addEventListener("click", () => setViewMode("month"));
  document.querySelectorAll(".driver-tab").forEach((button) => {
    button.addEventListener("click", () => setDriverFilter(button.dataset.driver || ""));
  });
  document.querySelectorAll(".tax-tab").forEach((button) => {
    button.addEventListener("click", () => setTaxFilter(button.dataset.tax || ""));
  });
  $("#searchInput").addEventListener("input", debounce(loadBookings, 220));
  previousSearchInput.addEventListener("input", debounce(loadPreviousBookings, 220));
  $("#addBookingBtn").addEventListener("click", () => openBooking());
  $("#closeDialog").addEventListener("click", () => bookingDialog.close());
  $("#cancelBtn").addEventListener("click", () => bookingDialog.close());
  $("#deleteBtn").addEventListener("click", deleteBooking);
  $("#printBtn").addEventListener("click", () => window.print());
  $("#refreshPreviousBtn").addEventListener("click", loadPreviousBookings);
  $("#refreshRevenueBtn").addEventListener("click", loadMonthlyRevenue);
  $("#refreshAdminDebugBtn").addEventListener("click", loadAdminDebug);
  revenueYear.addEventListener("change", loadMonthlyRevenue);
  bookingForm.addEventListener("submit", saveBooking);
  bookingForm.querySelectorAll(".time-entry").forEach((input) => bindTimeEntry(input));

  expenseMonth.addEventListener("change", loadExpenses);
  $("#addExpenseBtn").addEventListener("click", () => openExpense());
  $("#closeExpenseDialog").addEventListener("click", () => expenseDialog.close());
  $("#cancelExpenseBtn").addEventListener("click", () => expenseDialog.close());
  $("#deleteExpenseBtn").addEventListener("click", deleteExpense);
  expenseForm.addEventListener("submit", saveExpense);
  $("#vehicleForm").addEventListener("submit", (event) => saveOption(event, "vehicles"));
  $("#driverForm").addEventListener("submit", (event) => saveOption(event, "drivers"));
  $("#sourceForm").addEventListener("submit", (event) => saveOption(event, "sources"));
}

async function login(event) {
  event.preventDefault();
  const loginButton = $("#loginButton");
  loginButton.disabled = true;
  loginButton.textContent = "Σύνδεση...";
  $("#loginError").textContent = "";
  const data = Object.fromEntries(new FormData(event.currentTarget));
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    state.token = result.token;
    localStorage.setItem("safewheelsToken", state.token);
    showApp();
  } catch (error) {
    $("#loginError").textContent = error.message || "Δεν ήταν δυνατή η σύνδεση.";
  } finally {
    loginButton.disabled = false;
    loginButton.textContent = "Σύνδεση";
  }
}

function logout() {
  state.token = null;
  localStorage.removeItem("safewheelsToken");
  app.hidden = true;
  loginScreen.hidden = false;
}

function showApp() {
  loginScreen.hidden = true;
  app.hidden = false;
  loadOptions().then(() => {
    loadBookings();
    loadExpenses();
    loadPreviousBookings();
    loadMonthlyRevenue();
  });
}

function switchTab(tab) {
  state.activeTab = tab;
  $("#bookingsView").hidden = tab !== "bookings";
  $("#expensesView").hidden = tab !== "expenses";
  $("#previousView").hidden = tab !== "previous";
  $("#revenueView").hidden = tab !== "revenue";
  $("#fleetView").hidden = tab !== "fleet";
  $("#bookingsTab").classList.toggle("active", tab === "bookings");
  $("#expensesTab").classList.toggle("active", tab === "expenses");
  $("#previousTab").classList.toggle("active", tab === "previous");
  $("#revenueTab").classList.toggle("active", tab === "revenue");
  $("#fleetTab").classList.toggle("active", tab === "fleet");
  if (tab === "expenses") loadExpenses();
  if (tab === "previous") loadPreviousBookings();
  if (tab === "revenue") loadMonthlyRevenue();
  if (tab === "fleet") {
    renderOptionsManager();
    loadAdminDebug();
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "x-safewheels-session": state.token,
      ...(options.headers || {})
    }
  });
  if (response.status === 401) {
    logout();
    throw new Error("Η σύνδεση έληξε.");
  }
  if (response.status === 204) return null;
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Κάτι πήγε στραβά.");
  return result;
}

async function loadOptions() {
  if (!state.token) return;
  state.options = await api("/api/options");
  renderDynamicControls();
  renderOptionsManager();
  renderAdminDebug();
}

function renderDynamicControls() {
  fillSelect(bookingForm.elements.vehicle, state.options.vehicles);
  fillSelect(bookingForm.elements.driver, state.options.drivers, "Χωρίς οδηγό");
  fillSelect(bookingForm.elements.paymentMethod, state.options.paymentMethods);
  fillSelect(bookingForm.elements.bookingSource, state.options.bookingSources);
  fillSelect(expenseForm.elements.paymentMethod, state.options.paymentMethods);
  fillSelect(expenseForm.elements.vehicle, state.options.vehicles, "Χωρίς όχημα");

  const driverTabs = document.querySelector(".driver-tabs");
  const activeDriver = state.driverFilter;
  driverTabs.innerHTML = `<button class="driver-tab ${!activeDriver ? "active" : ""}" type="button" data-driver="">Όλοι οι οδηγοί</button>`
    + state.options.drivers.map((driver) => `
      <button class="driver-tab ${driver === activeDriver ? "active" : ""}" type="button" data-driver="${escapeHtml(driver)}">${escapeHtml(shortDriverName(driver))}</button>
    `).join("");
  driverTabs.querySelectorAll(".driver-tab").forEach((button) => {
    button.addEventListener("click", () => setDriverFilter(button.dataset.driver || ""));
  });
}

function fillSelect(select, values, emptyLabel = "") {
  if (!select) return;
  const current = select.value;
  select.innerHTML = `${emptyLabel ? `<option value="">${escapeHtml(emptyLabel)}</option>` : ""}`
    + values.map((value) => `<option>${escapeHtml(value)}</option>`).join("");
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function shortDriverName(name) {
  return String(name || "").trim().split(/\s+/)[0] || name;
}

async function loadBookings() {
  const q = $("#searchInput").value.trim();
  const range = currentRange();
  const params = new URLSearchParams();
  if (state.viewMode === "day") {
    params.set("date", state.date);
  } else {
    params.set("start", range.start);
    params.set("end", range.end);
  }
  if (q) params.set("q", q);
  if (state.taxFilter) params.set("tax", state.taxFilter);
  const totalsParams = new URLSearchParams({ start: range.start, end: range.end });
  const [bookings] = await Promise.all([
    api(`/api/bookings?${params.toString()}`),
    api(`/api/totals?${totalsParams.toString()}`)
  ]);
  state.bookings = bookings;
  renderBookings();
  renderTotals(calculateTotals(filteredBookings()));
  if (state.activeTab === "previous") loadPreviousBookings();
  if (state.activeTab === "fleet") loadAdminDebug();
}

async function loadAdminDebug() {
  if (!state.token) return;
  const range = currentRange();
  const params = new URLSearchParams({ start: range.start, end: range.end });
  const q = $("#searchInput").value.trim();
  if (q) params.set("q", q);
  if (state.taxFilter) params.set("tax", state.taxFilter);
  if (state.driverFilter) params.set("driver", state.driverFilter);
  state.adminDebug = await api(`/api/admin/debug?${params.toString()}`);
  renderAdminDebug();
}

function renderAdminDebug() {
  const panel = $("#adminDebugPanel");
  if (!panel) return;
  const data = state.adminDebug;
  if (!data) {
    $("#adminDebugMeta").textContent = "Δεν έχει φορτωθεί";
    panel.innerHTML = `<div class="empty">Πατήστε Ανανέωση για διαγνωστικό έλεγχο.</div>`;
    return;
  }
  $("#adminDebugMeta").textContent = `${data.databaseRowsCount} γραμμές βάσης`;
  panel.innerHTML = `
    <div><span>${data.totalBookings}</span><small>Total bookings</small></div>
    <div><span>${data.upcoming}</span><small>Upcoming</small></div>
    <div><span>${data.completed}</span><small>Completed</small></div>
    <div><span>${data.cancelled}</span><small>Cancelled</small></div>
    <div><span>${data.hiddenByFilters}</span><small>Hidden by filters</small></div>
    <div><span>${data.databaseRowsCount}</span><small>Database rows count</small></div>
    <div><span>${data.auditRowsCount}</span><small>Audit rows</small></div>
  `;
}

function renderBookings() {
  const list = $("#bookingList");
  const range = currentRange();
  const bookings = filteredBookings();
  $("#planTitle").textContent = state.driverFilter ? `${range.title} · ${state.driverFilter}` : range.title;
  $("#planMeta").textContent = `${bookings.length} transfer`;
  if (!bookings.length) {
    list.innerHTML = `<div class="empty">Δεν υπάρχουν κρατήσεις για αυτή την προβολή.</div>`;
    return;
  }
  let lastDate = "";
  list.innerHTML = bookings.map((booking) => {
    const dateHeader = booking.date !== lastDate && state.viewMode !== "day"
      ? `<div class="date-divider">${formatDate(booking.date)}</div>`
      : "";
    lastDate = booking.date;
    return `
      ${dateHeader}
      <article class="booking-card" data-status="${escapeHtml(booking.status)}" role="button" tabindex="0" data-id="${booking.id}">
        <div class="booking-main">
          <div class="time-pill">${escapeHtml(booking.pickupTime)}</div>
          <div>
            <h3>${escapeHtml(booking.customerName)}</h3>
            <div class="booking-details">
              ${routeBlock(booking.route)}
              ${flightBlock(booking.flightNumber)}
              <span>${escapeHtml(booking.phone || "Χωρίς τηλέφωνο")}</span>
              <span>${booking.passengers} άτομα · ${escapeHtml(booking.vehicle)}</span>
              <span>Πτήση/Ferry ώρα: ${escapeHtml(booking.travelTime || "-")} · Οδηγός: ${escapeHtml(booking.driver || "-")}</span>
              <span>Πηγή: ${escapeHtml(booking.bookingSource || "PRIVATE")} · Πληρωμή: ${escapeHtml(booking.paymentMethod || "Μετρητά")} · ${paymentLabels[booking.paymentStatus] || booking.paymentStatus}</span>
              <span>Σημειώσεις: ${escapeHtml(booking.notes || "-")}</span>
            </div>
            ${bookingDebugBlock(booking)}
          </div>
          <div class="booking-badges">
            <span class="tax-badge" data-tax="${escapeHtml(booking.taxStatus || "Μη Καταχωρημένο")}">${taxBadgeLabel(booking.taxStatus)}</span>
            <button type="button" class="small-btn tax-toggle-btn" data-id="${booking.id}" data-tax="${escapeHtml(booking.taxStatus || "Μη Καταχωρημένο")}">${booking.taxStatus === "Καταχωρημένο" ? "Μη καταχωρημένο" : "Καταχωρήθηκε"}</button>
            <button type="button" class="small-btn complete-booking-btn" data-id="${booking.id}">Ολοκληρώθηκε</button>
          </div>
        </div>
        <div class="booking-money">
          <span>Τιμή ${money(booking.price)}</span>
          <span>${escapeHtml(booking.paymentMethod || "Μετρητά")}</span>
          <span>${paymentLabels[booking.paymentStatus] || booking.paymentStatus}</span>
        </div>
      </article>
    `;
  }).join("");
  list.querySelectorAll(".booking-card").forEach((card) => {
    card.addEventListener("click", () => openBooking(state.bookings.find((item) => item.id === Number(card.dataset.id))));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter") card.click();
    });
  });
  list.querySelectorAll(".tax-toggle-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleTaxStatus(Number(button.dataset.id), button.dataset.tax);
    });
  });
  list.querySelectorAll(".complete-booking-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      completeBooking(Number(button.dataset.id));
    });
  });
}

function filteredBookings() {
  if (!state.driverFilter) return state.bookings;
  return state.bookings.filter((booking) => booking.driver === state.driverFilter);
}

function bookingDebugBlock(booking) {
  return `
    <div class="booking-debug">
      <span>ID: ${escapeHtml(booking.id)}</span>
      <span>Ημ/νία DB: ${escapeHtml(booking.date || "-")}</span>
      <span>Ώρα DB: ${escapeHtml(booking.pickupTime || "-")}</span>
      <span>Status: ${escapeHtml(booking.status || "-")}</span>
      <span>Οδηγός: ${escapeHtml(booking.driver || "-")}</span>
      <span>Όχημα: ${escapeHtml(booking.vehicle || "-")}</span>
      <span>Πληρωμή: ${escapeHtml(booking.paymentMethod || "-")} / ${escapeHtml(paymentLabels[booking.paymentStatus] || booking.paymentStatus || "-")}</span>
      <span>Πηγή: ${escapeHtml(booking.bookingSource || "PRIVATE")}</span>
    </div>
  `;
}

function calculateTotals(bookings) {
  return bookings.reduce((totals, booking) => {
    if (booking.status === "Cancelled") return totals;
    const price = Number(booking.price || 0);
    totals.bookings += 1;
    totals.total += price;
    if (booking.paymentMethod === "Κάρτα" || booking.paymentMethod === "Πίστωση") {
      totals.card += price;
    } else if (booking.paymentMethod === "Μετρητά") {
      totals.cash += price;
    }
    return totals;
  }, { bookings: 0, cash: 0, card: 0, total: 0 });
}

async function loadPreviousBookings() {
  if (!state.token) return;
  const params = new URLSearchParams({ history: "1" });
  const q = previousSearchInput.value.trim();
  if (q) params.set("q", q);
  const previous = await api(`/api/bookings?${params.toString()}`);
  state.previousBookings = previous;
  renderPreviousBookings();
}

function renderPreviousBookings() {
  const list = $("#previousList");
  $("#previousMeta").textContent = `${state.previousBookings.length} ολοκληρωμένες μεταφορές`;
  if (!state.previousBookings.length) {
    list.innerHTML = `<div class="empty">Δεν υπάρχουν προηγούμενες μεταφορές.</div>`;
    return;
  }
  list.innerHTML = state.previousBookings.map((booking) => `
    <article class="previous-card" data-id="${booking.id}">
      <div class="previous-main">
        <div class="previous-date">
          <strong>${shortDate(booking.date)}</strong>
          <span>${escapeHtml(booking.pickupTime)}</span>
        </div>
        <div>
          <h3>${escapeHtml(booking.customerName)}</h3>
          ${routeBlock(booking.route)}
          ${flightBlock(booking.flightNumber)}
          <div class="previous-grid">
            <span><b>Ημερομηνία:</b> ${formatDate(booking.date)}</span>
            <span><b>Ώρα:</b> ${escapeHtml(booking.pickupTime || "-")}</span>
            <span><b>Πελάτης:</b> ${escapeHtml(booking.customerName || "-")}</span>
            <span><b>Τηλέφωνο:</b> ${escapeHtml(booking.phone || "Χωρίς τηλέφωνο")}</span>
            <span><b>Άτομα:</b> ${escapeHtml(booking.passengers || 0)}</span>
            <span><b>Όχημα:</b> ${escapeHtml(booking.vehicle || "-")}</span>
            <span><b>Οδηγός:</b> ${escapeHtml(booking.driver || "-")}</span>
            <span><b>Τιμή:</b> ${money(booking.price)}</span>
            <span><b>Τρόπος πληρωμής:</b> ${escapeHtml(booking.paymentMethod || "Μετρητά")}</span>
            <span><b>Κατάσταση πληρωμής:</b> ${paymentLabels[booking.paymentStatus] || escapeHtml(booking.paymentStatus || "-")}</span>
            <span><b>Πηγή κράτησης:</b> ${escapeHtml(booking.bookingSource || "PRIVATE")}</span>
            <span><b>ΑΑΔΕ:</b> ${taxBadgeLabel(booking.taxStatus)}</span>
            <span class="wide-info"><b>Σημειώσεις:</b> ${escapeHtml(booking.notes || "-")}</span>
          </div>
        </div>
        <div class="previous-money">
          <strong>${money(booking.price)}</strong>
          <span>${escapeHtml(booking.paymentMethod || "Μετρητά")}</span>
        </div>
        <div class="previous-actions">
          <span class="tax-badge" data-tax="${escapeHtml(booking.taxStatus || "Μη Καταχωρημένο")}">${taxBadgeLabel(booking.taxStatus)}</span>
          <button type="button" class="small-btn restore-booking-btn" data-id="${booking.id}">Επαναφορά σε Επερχόμενη</button>
          <button type="button" class="small-btn clone-booking-btn" data-id="${booking.id}">Νέα κράτηση</button>
          <button type="button" class="small-btn ghost edit-previous-btn" data-id="${booking.id}">Επεξεργασία</button>
        </div>
      </div>
    </article>
  `).join("");
  list.querySelectorAll(".clone-booking-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      newBookingFromPrevious(Number(button.dataset.id));
    });
  });
  list.querySelectorAll(".edit-previous-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openBooking(state.previousBookings.find((item) => item.id === Number(button.dataset.id)));
    });
  });
  list.querySelectorAll(".restore-booking-btn").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      restoreBooking(Number(button.dataset.id));
    });
  });
}

function routeBlock(route) {
  const parts = splitRoute(route);
  if (!parts) return `<span class="route-chip">${escapeHtml(route || "Χωρίς διαδρομή")}</span>`;
  return `
    <span class="route-chip">
      <strong>${escapeHtml(parts.from)}</strong>
      <i></i>
      <strong>${escapeHtml(parts.to)}</strong>
    </span>
  `;
}

function flightBlock(flightNumber) {
  if (!flightNumber) return `<span class="flight-chip">✈ -</span>`;
  return `<span class="flight-chip">✈ ${escapeHtml(flightNumber)}</span>`;
}

function splitRoute(route) {
  const clean = String(route || "").trim();
  if (!clean) return null;
  const parts = clean.split(/\s*(?:->|→|-)\s*/).filter(Boolean);
  if (parts.length < 2) return null;
  return { from: parts[0].toUpperCase(), to: parts.slice(1).join(" ").toUpperCase() };
}

function renderTotals(totals) {
  $("#bookingCount").textContent = totals.bookings;
  $("#cashTotal").textContent = money(totals.cash);
  $("#cardTotal").textContent = money(totals.card);
  $("#grandTotal").textContent = money(totals.total);
}

function bindTimeEntry(input) {
  input.addEventListener("input", () => {
    input.value = formatTimeInput(input.value, false);
    input.setSelectionRange(input.value.length, input.value.length);
  });
  input.addEventListener("blur", () => {
    input.value = formatTimeInput(input.value, true);
  });
}

function formatTimeInput(value, complete) {
  const digits = String(value || "").replace(/\D/g, "").slice(0, 4);
  if (!digits) return "";
  if (digits.length === 1) return digits;
  const hour = Math.min(Number(digits.slice(0, 2)), 23).toString().padStart(2, "0");
  if (digits.length === 2) return complete ? `${hour}:00` : `${hour}:`;
  const minuteDigits = digits.slice(2, 4);
  const minute = complete && minuteDigits.length === 1
    ? `${minuteDigits}0`
    : minuteDigits;
  if (minute.length === 2) {
    return `${hour}:${Math.min(Number(minute), 59).toString().padStart(2, "0")}`;
  }
  return `${hour}:${minute}`;
}

function openBooking(booking = null) {
  state.editingId = booking?.id || null;
  bookingForm.reset();
  $("#formError").textContent = "";
  $("#dialogTitle").textContent = booking ? "Επεξεργασία κράτησης" : "Νέα κράτηση";
  $("#deleteBtn").hidden = !booking || booking.status === "Completed";
  const values = booking || {
    date: state.date,
    passengers: 1,
    price: 0,
    flightNumber: "",
    paymentStatus: "Unpaid",
    paymentMethod: "Μετρητά",
    vehicle: state.options.vehicles[0] || "OPEL VIVARO",
    driver: "",
    bookingSource: state.options.bookingSources[0] || "PRIVATE",
    taxStatus: "Μη Καταχωρημένο",
    status: "Pending"
  };
  Object.entries(values).forEach(([key, value]) => {
    if (bookingForm.elements[key]) {
      if (key === "price") {
        // Display price with comma decimal separator (el-GR style)
        const num = parseFloat(String(value).replace(",", ".")) || 0;
        bookingForm.elements[key].value = num % 1 === 0 ? String(num) : num.toFixed(2).replace(".", ",");
      } else {
        bookingForm.elements[key].value = value ?? "";
      }
    }
  });
  syncBookingStatusControl(booking);
  bookingDialog.showModal();
}

function syncBookingStatusControl(booking) {
  const statusSelect = bookingForm.elements.status;
  const completedOption = [...statusSelect.options].find((option) => option.value === "Completed");
  if (completedOption) completedOption.disabled = booking?.status !== "Completed";
}

function newBookingFromPrevious(id) {
  const previous = state.previousBookings.find((booking) => booking.id === id);
  if (!previous) return;
  openBooking({
    date: state.date,
    pickupTime: "",
    travelTime: "",
    flightNumber: "",
    customerName: previous.customerName || "",
    phone: previous.phone || "",
    route: previous.route || "",
    passengers: previous.passengers || 1,
    luggage: previous.luggage || 0,
    price: previous.price || 0,
    paymentStatus: "Unpaid",
    paymentMethod: previous.paymentMethod || "Μετρητά",
    vehicle: previous.vehicle || state.options.vehicles[0] || "OPEL VIVARO",
    driver: previous.driver || "",
    bookingSource: previous.bookingSource || state.options.bookingSources[0] || "PRIVATE",
    taxStatus: "Μη Καταχωρημένο",
    status: "Pending",
    notes: previous.notes || ""
  });
  state.editingId = null;
  bookingForm.elements.id.value = "";
  $("#dialogTitle").textContent = "Νέα κράτηση";
  $("#deleteBtn").hidden = true;
}

async function saveBooking(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(bookingForm));
  data.pickupTime = formatTimeInput(data.pickupTime, true);
  data.travelTime = formatTimeInput(data.travelTime, true);
  const id = data.id || state.editingId;
  try {
    await api(id ? `/api/bookings/${id}` : "/api/bookings", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(data)
    });
    bookingDialog.close();
    setDate(data.date || state.date);
    loadPreviousBookings();
    loadMonthlyRevenue();
  } catch (error) {
    $("#formError").textContent = error.message;
  }
}

async function deleteBooking() {
  if (!state.editingId) return;
  if (!confirm("Η κράτηση θα διαγραφεί οριστικά.")) return;
  await api(`/api/bookings/${state.editingId}`, { method: "DELETE" });
  bookingDialog.close();
  loadBookings();
}

async function loadExpenses() {
  if (!state.token) return;
  const month = expenseMonth.value || state.date.slice(0, 7);
  const [expenses, summary] = await Promise.all([
    api(`/api/expenses?month=${month}`),
    api(`/api/expense-summary?month=${month}`)
  ]);
  state.expenses = expenses;
  renderExpenses(summary);
}

function renderExpenses(summary) {
  $("#monthlyRevenue").textContent = money(summary.revenue);
  $("#monthlyExpenses").textContent = money(summary.expenses);
  $("#monthlyNet").textContent = money(summary.net);
  $("#monthlyNet").classList.toggle("negative", Number(summary.net) < 0);
  $("#expenseMeta").textContent = `${state.expenses.length} εγγραφές`;
  $("#categorySummary").innerHTML = summary.byCategory.length
    ? summary.byCategory.map((item) => `<span>${escapeHtml(item.category)}: <strong>${money(item.total)}</strong></span>`).join("")
    : `<span>Δεν υπάρχουν έξοδα για τον μήνα.</span>`;
  const list = $("#expenseList");
  if (!state.expenses.length) {
    list.innerHTML = `<div class="empty">Δεν υπάρχουν έξοδα για αυτόν τον μήνα.</div>`;
    return;
  }
  list.innerHTML = state.expenses.map((expense) => `
    <article class="booking-card expense-card" role="button" tabindex="0" data-id="${expense.id}">
      <div class="booking-main">
        <div class="time-pill">${expense.date.slice(8, 10)}/${expense.date.slice(5, 7)}</div>
        <div>
          <h3>${escapeHtml(expense.category)}</h3>
          <div class="booking-details">
            <span>${escapeHtml(expense.description || "Χωρίς περιγραφή")}</span>
            <span>${escapeHtml(expense.paymentMethod || "Μετρητά")} · Όχημα: ${escapeHtml(expense.vehicle || "-")} · ${escapeHtml(expense.notes || "Χωρίς σημειώσεις")}</span>
          </div>
        </div>
        <span class="amount-badge">${money(expense.amount)}</span>
      </div>
    </article>
  `).join("");
  list.querySelectorAll(".expense-card").forEach((card) => {
    card.addEventListener("click", () => openExpense(state.expenses.find((item) => item.id === Number(card.dataset.id))));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter") card.click();
    });
  });
}

function openExpense(expense = null) {
  state.editingExpenseId = expense?.id || null;
  expenseForm.reset();
  $("#expenseFormError").textContent = "";
  $("#expenseDialogTitle").textContent = expense ? "Επεξεργασία εξόδου" : "Νέο έξοδο";
  $("#deleteExpenseBtn").hidden = !expense;
  const values = expense || {
    date: state.date,
    category: "Καύσιμα",
    amount: 0,
    paymentMethod: "Μετρητά",
    vehicle: ""
  };
  Object.entries(values).forEach(([key, value]) => {
    if (expenseForm.elements[key]) expenseForm.elements[key].value = value ?? "";
  });
  expenseDialog.showModal();
}

async function saveExpense(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(expenseForm));
  const id = data.id || state.editingExpenseId;
  try {
    await api(id ? `/api/expenses/${id}` : "/api/expenses", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(data)
    });
    expenseDialog.close();
    expenseMonth.value = (data.date || state.date).slice(0, 7);
    loadExpenses();
    loadBookings();
    loadMonthlyRevenue();
  } catch (error) {
    $("#expenseFormError").textContent = error.message;
  }
}

async function deleteExpense() {
  if (!state.editingExpenseId) return;
  if (!confirm("Να διαγραφεί οριστικά αυτό το έξοδο;")) return;
  await api(`/api/expenses/${state.editingExpenseId}`, { method: "DELETE" });
  expenseDialog.close();
  loadExpenses();
  loadMonthlyRevenue();
}

async function loadMonthlyRevenue() {
  if (!state.token) return;
  const year = revenueYear.value || new Date(`${state.date}T12:00:00`).getFullYear();
  const data = await api(`/api/monthly-revenue?year=${year}`);
  state.monthlyRevenue = data;
  renderMonthlyRevenue();
}

function renderMonthlyRevenue() {
  const data = state.monthlyRevenue;
  if (!data) return;
  $("#seasonCash").textContent = money(data.season.cash);
  $("#seasonCard").textContent = money(data.season.card);
  $("#seasonTotal").textContent = money(data.season.total);
  $("#seasonExpenses").textContent = money(data.season.expenses);
  $("#seasonNet").textContent = money(data.season.net);
  $("#seasonNet").classList.toggle("negative", Number(data.season.net) < 0);
  $("#revenueMeta").textContent = `Απρίλιος - Νοέμβριος ${data.year}`;

  $("#revenueMonthList").innerHTML = data.months.map((month, index) => `
    <article class="month-card month-${month.month}">
      <header class="month-card-header">
        <div>
          <h3>${escapeHtml(month.name)} ${data.year}</h3>
          <p>${month.entries.length} γραμμές</p>
          <div class="month-print-actions">
            <button type="button" class="small-btn print-month-btn" data-index="${index}">Εκτύπωση ${escapeHtml(month.name)}</button>
            <button type="button" class="small-btn ghost pdf-month-btn" data-index="${index}">Εξαγωγή PDF</button>
          </div>
        </div>
        <div class="month-totals">
          <span>Μετρητά <strong class="amount-cash">${money(month.cash)}</strong></span>
          <span>Κάρτα <strong class="amount-card">${money(month.card)}</strong></span>
          <span>Γενικό <strong class="amount-total">${money(month.total)}</strong></span>
          <span>Έξοδα <strong class="amount-expense">${money(month.expenses)}</strong></span>
          <span>Καθαρά <strong class="amount-net ${Number(month.net) < 0 ? "negative" : ""}">${money(month.net)}</strong></span>
        </div>
      </header>
      <div class="revenue-table-wrap">
        <table class="revenue-table">
          <thead>
            <tr>
              <th>Ημερομηνία</th>
              <th>Ώρα</th>
              <th>Δρομολόγιο</th>
              <th>Πελάτης</th>
              <th>Μετρητά</th>
              <th>Κάρτα</th>
              <th>Έξοδα</th>
              <th>Περιγραφή</th>
            </tr>
          </thead>
          <tbody>
            ${month.entries.length ? month.entries.map((entry) => `
              <tr class="${entry.type === "expense" ? "expense-row" : ""}">
                <td>${shortDate(entry.date)}</td>
                <td>${escapeHtml(entry.time || "-")}</td>
                <td>${escapeHtml(entry.route || "-")}</td>
                <td>${escapeHtml(entry.customer || "-")}</td>
                <td class="amount-cash">${entry.cash ? money(entry.cash) : ""}</td>
                <td class="amount-card">${entry.card ? money(entry.card) : ""}</td>
                <td class="amount-expense">${entry.expenses ? money(entry.expenses) : ""}</td>
                <td>${escapeHtml(entry.description || "")}</td>
              </tr>
            `).join("") : `<tr><td colspan="8" class="empty-cell">Δεν υπάρχουν καταχωρήσεις για τον μήνα.</td></tr>`}
          </tbody>
          <tfoot>
            <tr>
              <th colspan="4">Σύνολα</th>
              <th class="amount-cash">${money(month.cash)}</th>
              <th class="amount-card">${money(month.card)}</th>
              <th class="amount-expense">${money(month.expenses)}</th>
              <th><span class="amount-total">Γενικό: ${money(month.total)}</span><br><span class="amount-net">Καθαρά: ${money(month.net)}</span></th>
            </tr>
          </tfoot>
        </table>
      </div>
    </article>
  `).join("");
  $("#revenueMonthList").querySelectorAll(".print-month-btn").forEach((button) => {
    button.addEventListener("click", () => printRevenueMonth(Number(button.dataset.index), "print"));
  });
  $("#revenueMonthList").querySelectorAll(".pdf-month-btn").forEach((button) => {
    button.addEventListener("click", () => printRevenueMonth(Number(button.dataset.index), "pdf"));
  });
}

function printRevenueMonth(index, mode) {
  const data = state.monthlyRevenue;
  const month = data?.months?.[index];
  if (!month) return;
  const printArea = $("#printArea");
  const title = `TRANSFER - Σύνολο Εσόδων Μήνα - ${month.name} ${data.year}`;
  printArea.innerHTML = buildRevenuePrintHtml(month, data.year);
  document.title = title;
  document.body.classList.add("printing-revenue");
  document.body.classList.remove("print-landscape");
  setPrintPageMode("portrait");

  requestAnimationFrame(() => {
    const table = printArea.querySelector(".print-revenue-table");
    const needsLandscape = table && table.scrollWidth > printArea.clientWidth + 4;
    if (needsLandscape) {
      document.body.classList.add("print-landscape");
      setPrintPageMode("landscape");
    }
    window.print();
    window.setTimeout(() => {
      document.body.classList.remove("printing-revenue", "print-landscape");
      printArea.innerHTML = "";
      document.title = "SafeWheels Kos | Κρατήσεις Transfer";
      setPrintPageMode("portrait");
    }, 500);
  });
}

function setPrintPageMode(mode) {
  let style = document.querySelector("#dynamicPrintPage");
  if (!style) {
    style = document.createElement("style");
    style.id = "dynamicPrintPage";
    document.head.appendChild(style);
  }
  style.textContent = `@page { size: A4 ${mode}; margin: 10mm; }`;
}

function buildRevenuePrintHtml(month, year) {
  return `
    <section class="print-sheet month-${month.month}">
      <header class="print-header">
        <p>TRANSFER</p>
        <h1>Σύνολο Εσόδων Μήνα</h1>
        <h2>${escapeHtml(month.name)} ${year}</h2>
      </header>
      <table class="revenue-table print-revenue-table">
        <thead>
          <tr>
            <th>Ημερομηνία</th>
            <th>Ώρα</th>
            <th>Δρομολόγιο</th>
            <th>Πελάτης</th>
            <th>Μετρητά</th>
            <th>Κάρτα</th>
            <th>Έξοδα</th>
            <th>Περιγραφή</th>
          </tr>
        </thead>
        <tbody>
          ${month.entries.length ? month.entries.map((entry) => `
            <tr class="${entry.type === "expense" ? "expense-row" : ""}">
              <td>${shortDate(entry.date)}</td>
              <td>${escapeHtml(entry.time || "-")}</td>
              <td>${escapeHtml(entry.route || "-")}</td>
              <td>${escapeHtml(entry.customer || "-")}</td>
              <td class="amount-cash">${entry.cash ? money(entry.cash) : ""}</td>
              <td class="amount-card">${entry.card ? money(entry.card) : ""}</td>
              <td class="amount-expense">${entry.expenses ? money(entry.expenses) : ""}</td>
              <td>${escapeHtml(entry.description || "")}</td>
            </tr>
          `).join("") : `<tr><td colspan="8" class="empty-cell">Δεν υπάρχουν καταχωρήσεις για τον μήνα.</td></tr>`}
        </tbody>
        <tfoot>
          <tr>
            <th colspan="4">Σύνολα</th>
            <th class="amount-cash">${money(month.cash)}</th>
            <th class="amount-card">${money(month.card)}</th>
            <th class="amount-expense">${money(month.expenses)}</th>
            <th><span class="amount-total">Γενικό: ${money(month.total)}</span><br><span class="amount-net">Καθαρά: ${money(month.net)}</span></th>
          </tr>
        </tfoot>
      </table>
      <footer class="print-totals">
        <div><span>Σύνολο Μετρητών</span><strong class="amount-cash">${money(month.cash)}</strong></div>
        <div><span>Σύνολο Κάρτας</span><strong class="amount-card">${money(month.card)}</strong></div>
        <div><span>Γενικό Σύνολο</span><strong class="amount-total">${money(month.total)}</strong></div>
        <div><span>Σύνολο Εξόδων</span><strong class="amount-expense">${money(month.expenses)}</strong></div>
        <div><span>Καθαρά Έσοδα</span><strong class="amount-net">${money(month.net)}</strong></div>
      </footer>
    </section>
  `;
}

async function saveOption(event, kind) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  await api(`/api/options/${kind}`, {
    method: "POST",
    body: JSON.stringify(data)
  });
  form.reset();
  await loadOptions();
}

function renderOptionsManager() {
  if (!$("#vehicleList")) return;
  renderOptionList("vehicles", state.options.vehicles, $("#vehicleList"), $("#vehicleMeta"), "οχήματα");
  renderOptionList("drivers", state.options.drivers, $("#driverList"), $("#driverMeta"), "οδηγοί");
  renderOptionList("sources", state.options.bookingSources, $("#sourceList"), $("#sourceMeta"), "πηγές");
}

function renderOptionList(kind, items, container, meta, label) {
  meta.textContent = `${items.length} ${label}`;
  container.innerHTML = items.map((name) => `
    <article class="option-row" data-kind="${kind}" data-name="${escapeHtml(name)}">
      <input value="${escapeHtml(name)}" aria-label="Όνομα">
      <div>
        <button type="button" class="small-btn save-option-btn">Αποθήκευση</button>
        <button type="button" class="small-btn danger delete-option-btn">Διαγραφή</button>
      </div>
    </article>
  `).join("");
  container.querySelectorAll(".option-row").forEach((row) => {
    row.querySelector(".save-option-btn").addEventListener("click", () => updateOption(kind, row.dataset.name, row.querySelector("input").value));
    row.querySelector(".delete-option-btn").addEventListener("click", () => deleteOption(kind, row.dataset.name));
  });
}

async function updateOption(kind, oldName, newName) {
  const id = await findOptionId(kind, oldName);
  if (!id) return;
  await api(`/api/options/${kind}/${id}`, {
    method: "PUT",
    body: JSON.stringify({ name: newName })
  });
  await loadOptions();
}

async function deleteOption(kind, name) {
  if (!confirm(`Να διαγραφεί από τη λίστα: ${name};`)) return;
  const id = await findOptionId(kind, name);
  if (!id) return;
  await api(`/api/options/${kind}/${id}`, { method: "DELETE" });
  await loadOptions();
}

async function findOptionId(kind, name) {
  return state.options.optionDetails?.[kind]?.find((item) => item.name === name)?.id;
}

async function toggleTaxStatus(id, current) {
  const next = current === "Καταχωρημένο" ? "Μη Καταχωρημένο" : "Καταχωρημένο";
  await api(`/api/bookings/${id}/tax-status`, {
    method: "PUT",
    body: JSON.stringify({ taxStatus: next })
  });
  loadBookings();
}

async function completeBooking(id) {
  if (!confirm("Θέλετε σίγουρα να ολοκληρώσετε αυτή τη μεταφορά;")) return;
  await setBookingStatus(id, "Completed");
}

async function restoreBooking(id) {
  await setBookingStatus(id, "Confirmed");
}

async function setBookingStatus(id, status) {
  await api(`/api/bookings/${id}/status`, {
    method: "PUT",
    body: JSON.stringify({ status })
  });
  await loadBookings();
  if (state.activeTab === "previous") await loadPreviousBookings();
}

function setDriverFilter(driver) {
  state.driverFilter = driver;
  document.querySelectorAll(".driver-tab").forEach((button) => {
    button.classList.toggle("active", (button.dataset.driver || "") === driver);
  });
  renderBookings();
  renderTotals(calculateTotals(filteredBookings()));
}

function setTaxFilter(tax) {
  state.taxFilter = tax;
  document.querySelectorAll(".tax-tab").forEach((button) => {
    button.classList.toggle("active", (button.dataset.tax || "") === tax);
  });
  loadBookings();
}

function setViewMode(mode) {
  state.viewMode = mode;
  $("#dailyPlanBtn").classList.toggle("active", mode === "day");
  $("#weeklyPlanBtn").classList.toggle("active", mode === "week");
  $("#monthlyPlanBtn").classList.toggle("active", mode === "month");
  loadBookings();
}

function changeDay(offset) {
  const current = new Date(`${state.date}T12:00:00`);
  current.setDate(current.getDate() + offset);
  setDate(localDateIso(current));
}

function setDate(date) {
  state.date = date;
  selectedDate.value = date;
  expenseMonth.value = date.slice(0, 7);
  loadBookings();
}

function currentRange() {
  const current = new Date(`${state.date}T12:00:00`);
  if (state.viewMode === "week") {
    const day = current.getDay() || 7;
    const start = new Date(current);
    start.setDate(current.getDate() - day + 1);
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    return {
      start: toIso(start),
      end: toIso(end),
      title: `Εβδομαδιαίο πλάνο ${shortDate(toIso(start))} - ${shortDate(toIso(end))}`
    };
  }
  if (state.viewMode === "month") {
    const start = new Date(current.getFullYear(), current.getMonth(), 1, 12);
    const end = new Date(current.getFullYear(), current.getMonth() + 1, 0, 12);
    return {
      start: toIso(start),
      end: toIso(end),
      title: new Intl.DateTimeFormat("el-GR", { month: "long", year: "numeric" }).format(current)
    };
  }
  return {
    start: state.date,
    end: state.date,
    title: formatDate(state.date)
  };
}

function localDateIso(date = new Date()) {
  const local = new Date(date.getFullYear(), date.getMonth(), date.getDate(), 12);
  return toIso(local);
}

function toIso(date) {
  return date.toISOString().slice(0, 10);
}

function formatDate(value) {
  return new Intl.DateTimeFormat("el-GR", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date(`${value}T12:00:00`));
}

function shortDate(value) {
  return new Intl.DateTimeFormat("el-GR", { day: "2-digit", month: "2-digit" }).format(new Date(`${value}T12:00:00`));
}

function money(value) {
  return new Intl.NumberFormat("el-GR", { style: "currency", currency: "EUR" }).format(Number(value || 0));
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[char]));
}

function debounce(fn, wait) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), wait);
  };
}
