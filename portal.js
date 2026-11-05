(() => {
  const page = document.body.dataset.portalPage;
  const apiBase = (document.querySelector('meta[name="cleon-api-url"]')?.content || "")
    .trim()
    .replace(/\/+$/, "");
  const publishableKey = "sb_publishable_0sjd4-0ktuqR-lCY6j8fdA_qFCqBsJn";
  const tokenKey = "cleon-portal-token";
  const refreshKey = "cleon-portal-refresh-token";
  const emailKey = "cleon-portal-email";
  const expiryKey = "cleon-portal-expiry";
  const status = document.getElementById("page-status");
  let token = sessionStorage.getItem(tokenKey) || "";
  let refreshToken = sessionStorage.getItem(refreshKey) || "";
  let refreshTimer = null;
  let reports = {};
  let currentMember = null;
  let previewObjectUrl = null;

  const entryPages = ["pump-session", "fuel-receipt", "account-activity", "expenses", "tank-dip"];
  const rolePages = {
    super_admin: new Set(["dashboard", "reports", "profile", "pump-session", "fuel-receipt", "account-activity", "expenses", "tank-dip"]),
    admin: new Set(["dashboard", "reports", "pump-session", "fuel-receipt", "account-activity", "expenses", "tank-dip"]),
    manager: new Set(["dashboard", "reports"]),
    member: new Set(["reports", "profile"]),
    staff: new Set(["pump-session", "fuel-receipt", "account-activity", "expenses", "tank-dip"]),
  };

  function setStatus(message, isError = false) {
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("error", isError);
  }

  function clearSession() {
    sessionStorage.removeItem(tokenKey);
    sessionStorage.removeItem(refreshKey);
    sessionStorage.removeItem(emailKey);
    sessionStorage.removeItem(expiryKey);
    token = "";
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = null;
  }

  function requireApi() {
    if (!apiBase) throw new Error("The secure website API has not been configured yet.");
    const url = new URL(apiBase, window.location.href);
    if (url.protocol !== "https:" &&
      !(url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname))) {
      throw new Error("Member sign-in requires an HTTPS API connection.");
    }
  }

  async function requestJson(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("apikey", publishableKey);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    let response;
    try {
      response = await fetch(`${apiBase}${path}`, { ...options, headers });
    } catch (error) {
      throw new Error("Could not connect to the CLEON website service. Check your connection and try again.");
    }

    if (response.status === 401 && token && refreshToken &&
      !["/api/v1/login", "/api/v1/logout"].includes(path)) {
      const refreshResponse = await fetch(
        `${new URL(apiBase).origin}/auth/v1/token?grant_type=refresh_token`,
        {
          method: "POST",
          headers: { apikey: publishableKey, "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        },
      );
      if (refreshResponse.ok) {
        const refreshed = await refreshResponse.json();
        token = refreshed.access_token || "";
        refreshToken = refreshed.refresh_token || "";
        if (token && refreshToken) {
          sessionStorage.setItem(tokenKey, token);
          sessionStorage.setItem(refreshKey, refreshToken);
          headers.set("Authorization", `Bearer ${token}`);
          response = await fetch(`${apiBase}${path}`, { ...options, headers });
        }
      }
    }

    let result;
    try {
      result = await response.json();
    } catch (error) {
      throw new Error(`Website API returned an invalid response (HTTP ${response.status}).`);
    }

    if (!response.ok) {
      if (response.status === 401 && page !== "login") {
        clearSession();
        window.location.replace("login.html?expired=1");
      }
      throw new Error(result.error || `Website API returned HTTP ${response.status}.`);
    }
    return result;
  }

  function displayValue(value, label) {
    if (typeof value !== "number") return value ?? "—";
    const name = label.toLowerCase();
    if (["sales", "cost", "expense", "cash", "pos", "short", "expected", "price", "amount"].some(term => name.includes(term))) {
      return `₦${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
    if (["litre", "stock", "capacity", "(l)"].some(term => name.includes(term))) {
      return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} L`;
    }
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function addKpi(container, label, value) {
    const card = document.createElement("article");
    card.className = "kpi";

    if (label === "Net Litres Sold") {
      card.classList.add("hero-kpi");
    }

    const title = document.createElement("span");
    title.className = "kpi-title";
    title.textContent = label;

    const amount = document.createElement("strong");
    amount.className = "kpi-value";
    amount.textContent = displayValue(value, label);

    const reportValueColors = {
      "Net litres sold": "info",
      "Litres received": "info",
      "Cumulative tank dip variance": "success",
      "Dip variance estimate (not profit)": "success",
      "Sales value": "info",
      "Gross profit": "success",
      "Recorded expenses": "warning",
      "Net profit": "success",
      "Current stock": "danger",
      "RTT returned": "info",
      "RTT cost": "warning",
      "Tank baseline cost (not profit)": "warning",
      "True tank variance": "danger",
    };
    if (reportValueColors[label]) {
      amount.classList.add(reportValueColors[label]);
    } else if (label.includes("Sales") || label.includes("Cash Collected") || label.includes("POS Collected")) {
      amount.classList.add("success");
    } else if (label.includes("Fuel Stock") || label.includes("RTT")) {
      amount.classList.add("info");
    } else if (label.includes("Expenses")) {
      amount.classList.add("warning");
    } else if (label.includes("Short")) {
      amount.classList.add("danger");
    }

    if (label === "Net Litres Sold") {
      amount.classList.add("accent");
    }

    card.append(title, amount);
    container.appendChild(card);
  }

  function renderTable(head, body, headers, rows) {
    head.replaceChildren();
    body.replaceChildren();
    const headerRow = document.createElement("tr");

    headers.forEach(value => {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = value ?? "";
      headerRow.appendChild(cell);
    });

    head.appendChild(headerRow);

    if (!rows.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = Math.max(headers.length, 1);
      cell.textContent = "No rows in this published period.";
      row.appendChild(cell);
      body.appendChild(row);
      return;
    }

    rows.forEach(values => {
      const row = document.createElement("tr");
      values.forEach((value, index) => {
        const cell = document.createElement("td");
        cell.textContent = displayValue(value, headers[index] || "");
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
  }

  function renderDashboard(snapshots) {
    const dashboard = snapshots.dashboard;
    if (!dashboard) throw new Error("The desktop app has not published a dashboard snapshot yet.");

    const metrics = dashboard.data.metrics || {};
    const money = value => displayValue(Number(value || 0), "sales");
    const litres = value => displayValue(Number(value || 0), "litres");
    document.getElementById("sales-value").textContent = money(metrics.sales_amount);
    document.getElementById("cash-value").textContent = `Cash ${money(metrics.cash_collected)}`;
    document.getElementById("pos-value").textContent = `POS ${money(metrics.pos_collected)}`;
    document.getElementById("rtt-sales-value").textContent = `RTT ${money(metrics.rtt_sales_value)}`;
    document.getElementById("session-expenses-value").textContent = `Expenses ${money(metrics.session_expenses)}`;
    document.getElementById("short-over-value").textContent = `Short/Over ${money(metrics.cash_short_over)}`;
    document.getElementById("expected-sales-value").textContent = `Expected ${money(metrics.expected_sales)}`;
    const salesBasis = Math.max(1, Number(metrics.expected_sales || metrics.sales_amount || 0));
    document.getElementById("cash-gauge").style.width = `${Math.min(100, Math.abs(Number(metrics.cash_collected || 0)) / salesBasis * 100)}%`;
    document.getElementById("pos-gauge").style.width = `${Math.min(100, Math.abs(Number(metrics.pos_collected || 0)) / salesBasis * 100)}%`;
    document.getElementById("rtt-gauge").style.width = `${Math.min(100, Math.abs(Number(metrics.cash_short_over || 0)) / salesBasis * 100)}%`;
    document.getElementById("fuel-stock-value").textContent = litres(metrics.fuel_stock);
    document.getElementById("litres-value").textContent = litres(metrics.litres_sold);
    document.getElementById("cash-short-value").textContent = money(metrics.cash_short_over);
    document.getElementById("rtt-value").textContent = litres(metrics.rtt_litres);
    document.getElementById("rtt-cost-value").textContent = money(metrics.rtt_cost);
    document.getElementById("expenses-value").textContent = money(metrics.expenses);

    const shownDate = metrics.records_date || dashboard.data.date || "—";
    const selectedDate = dashboard.data.date || "—";
    const dateNote = metrics.has_sales_records === false
      ? `No sales records on or before ${selectedDate}.`
      : shownDate < selectedDate
        ? `No sales on ${selectedDate}; showing the latest session from ${shownDate}.`
        : `Showing session values for ${shownDate}.`;
    document.getElementById("dashboard-updated").textContent =
      `${dateNote} · Snapshot updated ${dashboard.updated_at || "—"}.`;
    const tankRows = metrics.tank_levels || [];
    const lowStock = metrics.low_stock_tanks || [];
    document.getElementById("stock-warning").textContent = lowStock.length
      ? `Restock advised: ${lowStock.map(tank => `${tank[0]} ${tank[1]} (${displayValue(tank[2], "Stock (L)")})`).join(", ")}`
      : tankRows.length ? "All tanks are above the low-stock threshold." : "No tanks have been added.";
    const tankList = document.getElementById("tank-gauges");
    tankList.replaceChildren();
    tankRows.forEach(tank => {
      const box = document.createElement("div"); box.className = "tank-meter";
      const title = document.createElement("div"); title.className = "tank-meter-title"; title.textContent = `${tank[0]} | ${tank[1]}`;
      const track = document.createElement("div"); track.className = "tank-meter-track";
      const fill = document.createElement("i");
      fill.style.width = `${Math.max(0, Math.min(100, Number(tank[2]) ? Number(tank[3]) / Number(tank[2]) * 100 : 0))}%`; track.append(fill);
      const detail = document.createElement("div"); detail.className = "tank-meter-detail";
      detail.textContent = `${litres(tank[3])} / ${litres(tank[2])} | Baseline ${litres(tank[9])} | True variance ${tank[8] == null ? "pending dip" : `${Number(tank[8]).toLocaleString()} L`}`;
      box.append(title, track, detail); tankList.append(box);
    });
    const variance = document.getElementById("tank-variance");
    variance.replaceChildren();
    document.getElementById("daily-variance").textContent = `Daily combined variance: ${Number(metrics.daily_tank_variance || 0) >= 0 ? "+" : ""}${Number(metrics.daily_tank_variance || 0).toLocaleString()} L`;
    tankRows.forEach(tank => { const row = document.createElement("div"); row.className = "tank-variance-row"; const label = document.createElement("span"); const val = tank[8] == null ? "no dip" : `${Number(tank[8]) >= 0 ? "overage" : "shortage"} ${Math.abs(Number(tank[8])).toLocaleString()} L`; label.textContent = `${tank[0]} ${tank[1]}: ${litres(tank[4])} sold | ${val}`; row.append(label); variance.append(row); });
    const priceList = document.getElementById("price-list"); priceList.replaceChildren();
    (metrics.selling_prices || []).forEach(row => { const item = document.createElement("div"); item.className = "price-item"; const product = document.createElement("b"); product.textContent = row[0]; const price = document.createElement("strong"); price.textContent = `${money(row[1])} / L`; const previous = Number(row[2] || 0), current = Number(row[1] || 0); const change = previous ? (current - previous) / previous * 100 : 0; const changeLabel = document.createElement("small"); changeLabel.textContent = previous ? `${change >= 0 ? "▲" : "▼"} ${Math.abs(change).toFixed(1)}% from last price` : "No previous price"; item.append(product, price, changeLabel); priceList.append(item); });
    const prev = Number(metrics.previous_sale_litres || 0), current = Number(metrics.litres_sold || 0);
    document.getElementById("litres-comparison").textContent = prev ? `${current >= prev ? "▲" : "▼"} ${Math.abs((current - prev) / prev * 100).toFixed(1)}% vs previous sales day` : "No previous sales day";
  }

  function renderProfitLossBreakdown(list, values) {
    const labels = [
      "Gross profit", "Expenses", "Attendant shorts", "Delivery shortage",
      "Net profit", "Tank dip variance less baseline cost",
    ];
    list.replaceChildren();
    if (!Array.isArray(values) || !values.length) {
      const empty = document.createElement("li");
      empty.className = "breakdown-empty";
      empty.textContent = "No profit and loss values have been published for this period.";
      list.appendChild(empty);
      return;
    }

    const numericValues = values.map(Number);
    const maximum = Math.max(1, ...numericValues.filter(Number.isFinite).map(Math.abs));
    numericValues.forEach((value, index) => {
      if (!Number.isFinite(value)) return;
      const label = labels[index] || `Value ${index + 1}`;
      const item = document.createElement("li");
      item.className = `breakdown-item${value < 0 ? " negative" : ""}`;
      item.setAttribute("aria-label", `${label}: ${displayValue(value, "amount")}`);

      const heading = document.createElement("div");
      heading.className = "breakdown-heading";
      const title = document.createElement("span");
      title.className = "breakdown-label";
      title.textContent = label;
      const amount = document.createElement("strong");
      amount.className = "breakdown-value";
      amount.textContent = `${value < 0 ? "−" : ""}₦${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
      heading.append(title, amount);
      const track = document.createElement("div");
      track.className = "breakdown-track";
      track.setAttribute("aria-hidden", "true");
      const fill = document.createElement("i");
      fill.style.width = `${value === 0 ? 0 : Math.max(2, Math.abs(value) / maximum * 100)}%`;
      track.appendChild(fill);
      item.append(heading, track);
      list.appendChild(item);
    });
    if (!list.children.length) {
      const empty = document.createElement("li");
      empty.className = "breakdown-empty";
      empty.textContent = "Published values are unavailable for this period.";
      list.appendChild(empty);
    }
  }

  function renderReports(snapshot) {
    if (!snapshot.reports) throw new Error("The desktop app has not published a Reports Centre snapshot yet.");
    const reportData = snapshot.reports.data;
    reports = reportData.reports || {};
    document.getElementById("reports-period").textContent =
      `Published period: ${reportData.period?.from || "—"} to ${reportData.period?.to || "—"} · Updated ${snapshot.reports.updated_at || "—"}.`;
    document.getElementById("report-from").value = reportData.period?.from || "";
    document.getElementById("report-to").value = reportData.period?.to || "";
    const email = reportData.summary?.email || {};
    document.getElementById("report-email-sender").textContent = email.sender || "Set in desktop Reports Centre";
    document.getElementById("report-email-recipient").textContent = email.recipient || "Set in desktop Reports Centre";
    document.getElementById("report-email-status").textContent = email.enabled === false ? "Product-finished email is disabled." : "Product-finished email is enabled in the desktop app.";
    const summary = document.getElementById("report-summary");
    summary.replaceChildren();
    Object.entries(reportData.summary?.cards || {}).forEach(([label, value]) => addKpi(summary, label, value));

    renderProfitLossBreakdown(document.getElementById("report-breakdown-rows"), reportData.summary?.chart);

    const select = document.getElementById("report-select");
    const previous = select.value;
    select.replaceChildren();
    select.appendChild(new Option("Summary", ""));

    Object.keys(reports).forEach(name => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      select.appendChild(option);
    });

    const tabs = document.getElementById("report-tabs");
    tabs.replaceChildren();
    ["Summary", ...Object.keys(reports), "Documents"].forEach(name => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "report-tab";
      tab.textContent = name;
      tab.setAttribute("aria-pressed", "false");
      tab.addEventListener("click", () => {
        if (name === "Documents") { document.getElementById("published-documents").scrollIntoView({ behavior: "smooth" }); return; }
        if (name === "Summary") { select.value = ""; renderSelectedReport(); return; }
        select.value = name;
        renderSelectedReport();
      });
      tabs.appendChild(tab);
    });

    if (Object.hasOwn(reports, previous)) select.value = previous;
    renderSelectedReport();
  }

  async function renderDocuments() {
    const list = document.getElementById("document-list");
    const message = document.getElementById("documents-status");
    const preview = document.getElementById("document-preview");
    message.classList.remove("error");
    message.textContent = "Loading published documents…";
    const response = await requestJson("/api/v1/documents");

    list.replaceChildren();
    preview.replaceChildren();
    preview.hidden = true;

    if (previewObjectUrl) {
      URL.revokeObjectURL(previewObjectUrl);
      previewObjectUrl = null;
    }

    if (!response.documents.length) {
      message.textContent = "No documents have been published.";
      return;
    }

    message.textContent = "Select a PDF or image to preview it in your browser.";
    response.documents.forEach(documentInfo => {
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = `${documentInfo.filename} · ${documentInfo.uploaded_at}`;
      item.appendChild(label);

      if (documentInfo.previewable) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = "Preview";
        button.addEventListener("click", () => {
          previewDocument(documentInfo).catch(error => {
            message.textContent = error.message;
            message.classList.add("error");
          });
        });
        item.appendChild(button);
      } else {
        const note = document.createElement("span");
        note.className = "muted";
        note.textContent = "Preview unavailable";
        item.appendChild(note);
      }
      list.appendChild(item);
    });
  }

  async function previewDocument(documentInfo) {
    const response = await fetch(
      `${apiBase}/api/v1/documents/${encodeURIComponent(documentInfo.document_id)}`,
      { headers: { apikey: publishableKey, Authorization: `Bearer ${token}` } },
    );

    if (!response.ok) {
      if (response.status === 401) {
        clearSession();
        window.location.replace("login.html?expired=1");
      }
      throw new Error(`Could not preview document (HTTP ${response.status}).`);
    }

    const blob = await response.blob();
    if (!["application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"].includes(blob.type)) {
      throw new Error("This document type cannot be previewed online.");
    }

    const preview = document.getElementById("document-preview");
    preview.replaceChildren();

    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = URL.createObjectURL(blob);

    if (blob.type === "application/pdf") {
      const frame = document.createElement("iframe");
      frame.title = `Preview of ${documentInfo.filename}`;
      frame.src = `${previewObjectUrl}#toolbar=0&navpanes=0`;
      preview.appendChild(frame);
    } else {
      const image = document.createElement("img");
      image.alt = `Preview of ${documentInfo.filename}`;
      image.src = previewObjectUrl;
      preview.appendChild(image);
    }
    preview.hidden = false;
  }

  function renderSelectedReport() {
    const reportSelect = document.getElementById("report-select");
    const report = reports[reportSelect.value];
    const exports = document.getElementById("report-exports");
    exports.hidden = (
      !["admin", "super_admin"].includes(currentMember?.role) ||
      !report
    );
    document.querySelectorAll(".report-tab").forEach(tab => {
      tab.setAttribute("aria-pressed", String(tab.textContent === (report ? reportSelect.value : "Summary")));
    });
    if (!report) {
      renderTable(document.getElementById("report-head"), document.getElementById("report-rows"), [], []);
      return;
    }
    renderTable(
      document.getElementById("report-head"),
      document.getElementById("report-rows"),
      report.headers || [],
      report.rows || [],
    );
  }

  function renderEntryHistory(entries) {
    const body = document.getElementById("entry-history-rows");
    if (!body) return;
    body.replaceChildren();
    if (!entries.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 5;
      cell.textContent = "No submissions yet.";
      row.appendChild(cell);
      body.appendChild(row);
      return;
    }
    entries.forEach(entry => {
      const row = document.createElement("tr");
      [entry.entry_type.replaceAll("_", " "), new Date(entry.created_at).toLocaleString(), entry.status,
        entry.entry_id.slice(0, 8), entry.processing_note || "—"].forEach((value, index) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        if (index === 2) cell.className = `entry-status ${entry.status}`;
        if (index === 3) cell.title = entry.entry_id;
        row.appendChild(cell);
      });
      body.appendChild(row);
    });
  }

  async function loadEntryHistory() {
    const result = await requestJson("/api/v1/entries");
    renderEntryHistory(result.entries || []);
  }

  async function submitStationEntry(form) {
    const submit = form.querySelector('button[type="submit"]');
    const message = document.getElementById("entry-form-status");
    const payload = Object.fromEntries(new FormData(form).entries());
    const numericFields = new Set([
      "opening_meter", "closing_meter", "opening_dip", "closing_dip", "rtt_litres",
      "cash_collected", "pos_amount", "expenses", "invoice_quantity", "actual_quantity",
      "cost_per_litre", "amount",
    ]);
    for (const [key, value] of Object.entries(payload)) {
      if (numericFields.has(key)) payload[key] = value === "" ? 0 : Number(value);
    }
    submit.disabled = true;
    message.textContent = "Submitting securely…";
    message.classList.remove("error");
    try {
      const result = await requestJson("/api/v1/entries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entry_type: form.dataset.entryType, payload }),
      });
      message.textContent = `Saved to the station queue · reference ${result.entry_id.slice(0, 8)}. The desktop app must process it before local records change.`;
      form.reset();
      const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
      form.querySelectorAll('input[type="date"]').forEach(input => { input.value = today; });
      await loadEntryHistory();
    } catch (error) {
      message.textContent = error.message;
      message.classList.add("error");
    } finally {
      submit.disabled = false;
    }
  }

  async function loadPageData() {
    requireApi();
    setStatus("Loading latest published data…");
    if (!token) {
      window.location.replace("login.html");
      return;
    }

    currentMember = await requestJson("/api/v1/me");
    if (!rolePages[currentMember.role]?.has(page)) {
      const defaultPage = currentMember.role === "member" ? "reports.html" : currentMember.role === "staff" ? "pump-session.html" : "dashboard.html";
      window.location.replace(defaultPage);
      return;
    }

    document.querySelectorAll("[data-page-link]").forEach(link => {
      link.hidden = !rolePages[currentMember.role]?.has(link.dataset.pageLink);
    });

    if (entryPages.includes(page)) {
      const snapshots = await requestJson("/api/v1/snapshot");
      const metrics = snapshots.dashboard?.data?.metrics || {};
      if (page === "pump-session") {
        fillPumpSessionOptions(metrics);
      }
      if (page === "tank-dip") fillTankDipOptions(metrics);
      if (page === "account-activity") fillAccountOptions(metrics);
      await loadEntryHistory();
      document.querySelectorAll('input[type="date"]').forEach(input => {
        if (!input.value) input.value = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
      });
      setStatus("Station entry access verified for this account.");
      return;
    }

    const snapshots = await requestJson("/api/v1/snapshot");
    if (page === "dashboard") renderDashboard(snapshots);
    if (page === "reports") {
      renderReports(snapshots);
      await renderDocuments();
    }
    if (page === "profile") {
      document.getElementById("profile-email").textContent = currentMember.email;
      document.getElementById("profile-expiry").textContent = new Date(currentMember.expires_at).toLocaleString();
    }

    setStatus("Latest published data loaded.");
  }

  function fillPumpSessionOptions(metrics) {
    const pumpSelect = document.getElementById("pump-select");
    const attendantSelect = document.getElementById("attendant-select");
    if (!pumpSelect || !attendantSelect) return;
    const pumps = metrics.pump_session_options || [];
    pumpSelect.replaceChildren(new Option(pumps.length ? "Choose pump" : "No open product runs", ""));
    pumps.forEach(item => pumpSelect.add(new Option(`${item.pump_number} · ${item.product}`, item.pump_number)));
    attendantSelect.replaceChildren(new Option("Choose attendant", ""));
    (metrics.attendant_options || []).forEach(name => attendantSelect.add(new Option(name, name)));
    const product = document.getElementById("pump-product");
    const opening = document.getElementById("opening-meter");
    const refreshMeter = () => {
      const selected = pumps.find(item => item.pump_number === pumpSelect.value);
      product.value = selected?.product || "";
      opening.value = selected?.opening_meter == null ? "" : Number(selected.opening_meter).toFixed(2);
    };
    pumpSelect.addEventListener("change", refreshMeter);
    refreshMeter();
    const submit = document.querySelector("#station-entry-form button[type=submit]");
    if (submit) submit.disabled = pumps.length === 0 || !(metrics.attendant_options || []).length;
  }

  function fillTankDipOptions(metrics) {
    const tankSelect = document.getElementById("tank-select");
    if (!tankSelect) return;
    const tanks = metrics.tank_dip_options || [];
    tankSelect.replaceChildren(new Option(tanks.length ? "Choose tank" : "No active tanks published", ""));
    tanks.forEach(tank => tankSelect.add(new Option(`${tank.tank_number} · ${tank.product}`, tank.tank_number)));
    const opening = document.getElementById("opening-dip");
    const capacity = document.getElementById("tank-capacity");
    const hint = document.getElementById("opening-dip-hint");
    const refresh = () => {
      const selected = tanks.find(tank => tank.tank_number === tankSelect.value);
      capacity.value = selected?.capacity ? Number(selected.capacity).toLocaleString() : "";
      if (selected?.opening_dip != null) {
        opening.value = Number(selected.opening_dip).toFixed(2);
        opening.readOnly = true;
        hint.textContent = "Carried forward from the latest recorded dip on or before the published date.";
      } else {
        opening.value = "";
        opening.readOnly = false;
        hint.textContent = "No earlier dip is available; enter the measured opening dip.";
      }
    };
    tankSelect.addEventListener("change", refresh);
    refresh();
    const submit = document.querySelector("#station-entry-form button[type=submit]");
    if (submit) submit.disabled = tanks.length === 0;
  }

  function fillAccountOptions(metrics) {
    const accounts = metrics.account_options || [];
    [document.getElementById("source-account"), document.getElementById("target-account")].forEach(select => {
      if (!select) return;
      select.replaceChildren(new Option(select.id === "source-account" ? "Choose source account" : "Choose destination account", ""));
      accounts.forEach(account => select.add(new Option(`${account.name} · ${account.type}`, account.name)));
    });
    const type = document.querySelector('[name="transaction_type"]');
    const receipt = document.querySelector('[name="receipt_id"]');
    const target = document.getElementById("target-account");
    const refresh = () => {
      const needsReceipt = type?.value === "Product Payment";
      if (receipt) receipt.required = needsReceipt;
      if (target) target.required = type?.value === "Account Transfer";
    };
    type?.addEventListener("change", refresh);
    refresh();
    const submit = document.querySelector("#station-entry-form button[type=submit]");
    if (submit) submit.disabled = accounts.length === 0;
  }

  async function signOut() {
    setStatus("Signing out…");
    try {
      requireApi();
      await requestJson("/api/v1/logout", { method: "POST" });
      setStatus("Signed out.");
    } catch (error) {
      setStatus(`Signed out locally. ${error.message}`, true);
    } finally {
      clearSession();
      window.location.replace("login.html");
    }
  }

  async function exportReport(format) {
    requireApi();
    const reportName = document.getElementById("report-select").value;
    if (!reportName) throw new Error("There are no reports available to export.");

    const query = new URLSearchParams({ report: reportName, format });
    const response = await fetch(`${apiBase}/api/v1/export?${query}`, {
      headers: { apikey: publishableKey, Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      let message = `Export failed (HTTP ${response.status}).`;
      try {
        const result = await response.json();
        message = result.error || message;
      } catch (error) {
        if (!(error instanceof SyntaxError)) throw error;
      }
      if (response.status === 401) {
        clearSession();
        window.location.replace("login.html?expired=1");
      }
      throw new Error(message);
    }

    const blob = await response.blob();
    const disposition = response.headers.get("Content-Disposition") || "";
    const filename = disposition.match(/filename="([^"]+)"/)?.[1] || `cleon_report.${format}`;
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(objectUrl);
    setStatus(`${reportName} report exported as ${format.toUpperCase()}.`);
  }

  if (page === "login") {
    const params = new URLSearchParams(window.location.search);
    if (params.get("expired") === "1") {
      setStatus("Your session expired. Please sign in again.", true);
    }

    try {
      requireApi();
    } catch (error) {
      document.getElementById("member-email").disabled = true;
      document.getElementById("member-password").disabled = true;
      document.querySelector("#login-form button[type=submit]").disabled = true;
      setStatus(error.message, true);
    }

    document.getElementById("login-form").addEventListener("submit", async event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      setStatus("Signing in…");

      try {
        requireApi();
        const result = await requestJson("/api/v1/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: form.get("email"),
            password: form.get("password"),
          }),
        });

        if (!result.token || !result.email) throw new Error("The API returned an incomplete sign-in response.");

        token = result.token;
        refreshToken = result.refresh_token || "";
        sessionStorage.setItem(tokenKey, result.token);
        if (refreshToken) sessionStorage.setItem(refreshKey, refreshToken);
        sessionStorage.setItem(emailKey, result.email);
        sessionStorage.setItem(expiryKey, result.expires_at || "");

        const destination = result.role === "member" ? "reports.html" : result.role === "staff" ? "pump-session.html" : "dashboard.html";
        window.location.assign(destination);
      } catch (error) {
        setStatus(error.message, true);
      }
    });
    document.getElementById("register-form")?.addEventListener("submit", async event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      setStatus("Submitting your access request…");
      try {
        requireApi();
        await requestJson("/api/v1/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: form.get("name"), email: form.get("email"), role: form.get("role"), password: form.get("password") }) });
        event.currentTarget.reset();
        setStatus("Request received. A CLEON super admin must approve it before you can sign in.");
      } catch (error) { setStatus(error.message, true); }
    });
  } else {
    if (!token) {
      window.location.replace("login.html");
      return;
    }

    document.querySelectorAll("[data-sign-out]").forEach(button => {
      button.addEventListener("click", signOut);
    });

    document.querySelectorAll("[data-refresh]").forEach(button => {
      button.addEventListener("click", () => loadPageData().catch(error => setStatus(error.message, true)));
    });

    if (page === "profile") {
      document.getElementById("profile-email").textContent = "Loading…";
      document.getElementById("profile-expiry").textContent = "Loading…";
    }

    if (page === "reports") {
      document.getElementById("report-select").addEventListener("change", renderSelectedReport);
      document.querySelectorAll("[data-export]").forEach(button => {
        button.addEventListener("click", () => {
          exportReport(button.dataset.export).catch(error => setStatus(error.message, true));
        });
      });
    }

    if (entryPages.includes(page)) {
      document.getElementById("station-entry-form").addEventListener("submit", event => {
        event.preventDefault();
        submitStationEntry(event.currentTarget);
      });
      document.querySelector("[data-entry-refresh]").addEventListener("click", () => {
        loadEntryHistory().catch(error => setStatus(error.message, true));
      });
    }

    loadPageData().catch(error => setStatus(error.message, true));

    if (page === "dashboard" || page === "reports") {
      refreshTimer = setInterval(() => {
        loadPageData().catch(error => setStatus(error.message, true));
      }, 60000);
    }
  }
})();
