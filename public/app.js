const state = {
  token: localStorage.getItem("safewheelsToken"),
  date: new Date().toISOString().slice(0, 10),
  viewMode: "day",
  activeTab: "bookings",
  bookings: [],
  expenses: [],
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

init();

function init() {
  selectedDate.value = state.date;
  expenseMonth.value = state.date.slice(0, 7);
  bindEvents();
  if (state.token) showApp();
}

function bindEvents() {
  $("#loginForm").addEventListener("submit", login);
  $("#logoutBtn").addEventListener("click", logout);
  $("#bookingsTab").addEventListener("click", () => switchTab("bookings"));
  $("#expensesTab").addEventListener("click", () => switchTab("expenses"));
  $("#prevDay").addEventListener("click", () => changeDay(-1));
  $("#nextDay").addEventListener("click", () => changeDay(1));
  $("#todayBtn").addEventListener("click", () => setDate(new Date().toISOString().slice(0, 10)));
  selectedDate.addEventListener("change", () => setDate(selectedDate.value));
  $("#dailyPlanBtn").addEventListener("click", () => setViewMode("day"));
  $("#weeklyPlanBtn").addEventListener("click", () => setViewMode("week"));
  $("#monthlyPlanBtn").addEventListener("click", () => setViewMode("month"));
  $("#searchInput").addEventListener("input", debounce(loadBookings, 220));
  $("#addBookingBtn").addEventListener("click", () => openBooking());
  $("#closeDialog").addEventListener("click", () => bookingDialog.close());
  $("#cancelBtn").addEventListener("click", () => bookingDialog.close());
  $("#deleteBtn").addEventListener("click", deleteBooking);
  $("#printBtn").addEventListener("click", () => window.print());
  bookingForm.addEventListener("submit", saveBooking);

  expenseMonth.addEventListener("change", loadExpenses);
  $("#addExpenseBtn").addEventListener("click", () => openExpense());
  $("#closeExpenseDialog").addEventListener("click", () => expenseDialog.close());
  $("#cancelExpenseBtn").addEventListener("click", () => expenseDialog.close());
  $("#deleteExpenseBtn").addEventListener("click", deleteExpense);
  expenseForm.addEventListener("submit", saveExpense);
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
  loadBookings();
  loadExpenses();
}

function switchTab(tab) {
  state.activeTab = tab;
  $("#bookingsView").hidden = tab !== "bookings";
  $("#expensesView").hidden = tab !== "expenses";
  $("#bookingsTab").classList.toggle("active", tab === "bookings");
  $("#expensesTab").classList.toggle("active", tab === "expenses");
  if (tab === "expenses") loadExpenses();
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

async function loadBookings() {
  const q = $("#searchInput").value.trim();
  const range = currentRange();
  const params = new URLSearchParams();
  if (q) {
    params.set("q", q);
  } else if (state.viewMode === "day") {
    params.set("date", state.date);
  } else {
    params.set("start", range.start);
    params.set("end", range.end);
  }
  const totalsParams = new URLSearchParams({ start: range.start, end: range.end });
  const [bookings, totals] = await Promise.all([
    api(`/api/bookings?${params.toString()}`),
    api(`/api/totals?${totalsParams.toString()}`)
  ]);
  state.bookings = bookings;
  renderBookings();
  renderTotals(totals);
}

function renderBookings() {
  const list = $("#bookingList");
  const range = currentRange();
  $("#planTitle").textContent = range.title;
  $("#planMeta").textContent = `${state.bookings.length} transfer`;
  if (!state.bookings.length) {
    list.innerHTML = `<div class="empty">Δεν υπάρχουν κρατήσεις για αυτή την προβολή.</div>`;
    return;
  }
  let lastDate = "";
  list.innerHTML = state.bookings.map((booking) => {
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
              <span>${escapeHtml(booking.route || "Χωρίς διαδρομή")}</span>
              <span>${escapeHtml(booking.hotel || "Χωρίς ξενοδοχείο")} · ${escapeHtml(booking.phone || "Χωρίς τηλέφωνο")}</span>
              <span>${booking.passengers} άτομα · ${booking.luggage} αποσκευές · ${escapeHtml(booking.vehicle)}</span>
              <span>Πτήση/Ferry: ${escapeHtml(booking.travelTime || "-")} · Οδηγός: ${escapeHtml(booking.driver || "-")}</span>
            </div>
          </div>
          <span class="status-badge" data-status="${escapeHtml(booking.status)}">${statusLabels[booking.status] || booking.status}</span>
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
}

function renderTotals(totals) {
  $("#bookingCount").textContent = totals.bookings;
  $("#cashTotal").textContent = money(totals.cash);
  $("#cardTotal").textContent = money(totals.card);
  $("#grandTotal").textContent = money(totals.total);
}

function openBooking(booking = null) {
  state.editingId = booking?.id || null;
  bookingForm.reset();
  $("#formError").textContent = "";
  $("#dialogTitle").textContent = booking ? "Επεξεργασία κράτησης" : "Νέα κράτηση";
  $("#deleteBtn").hidden = !booking;
  const values = booking || {
    date: state.date,
    passengers: 1,
    luggage: 0,
    price: 0,
    paymentStatus: "Unpaid",
    paymentMethod: "Μετρητά",
    vehicle: "OPEL VIVARO",
    driver: "",
    status: "Pending"
  };
  Object.entries(values).forEach(([key, value]) => {
    if (bookingForm.elements[key]) bookingForm.elements[key].value = value ?? "";
  });
  bookingDialog.showModal();
}

async function saveBooking(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(bookingForm));
  const id = data.id || state.editingId;
  try {
    await api(id ? `/api/bookings/${id}` : "/api/bookings", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(data)
    });
    bookingDialog.close();
    setDate(data.date || state.date);
  } catch (error) {
    $("#formError").textContent = error.message;
  }
}

async function deleteBooking() {
  if (!state.editingId) return;
  if (!confirm("Να διαγραφεί οριστικά αυτή η κράτηση;")) return;
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
            <span>${escapeHtml(expense.paymentMethod || "Μετρητά")} · ${escapeHtml(expense.notes || "Χωρίς σημειώσεις")}</span>
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
    paymentMethod: "Μετρητά"
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
  setDate(current.toISOString().slice(0, 10));
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
