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

  const rolePages = {
    super_admin: new Set(["dashboard", "reports", "profile"]),
    admin: new Set(["dashboard", "reports"]),
    manager: new Set(["dashboard", "reports"]),
    member: new Set(["reports", "profile"]),
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
    let response = await fetch(`${apiBase}${path}`, { ...options, headers });

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

    if (label.includes("Sales") || label.includes("Cash Collected") || label.includes("POS Collected")) {
      amount.classList.add("success");
    }

    if (label.includes("Fuel Stock") || label.includes("RTT")) {
      amount.classList.add("info");
    }

    if (label.includes("Expenses")) {
      amount.classList.add("warning");
    }

    if (label.includes("Short")) {
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
    const reportsSnapshot = snapshots.reports;

    if (!dashboard || !reportsSnapshot) {
      throw new Error("The app has not published both dashboard and reports yet.");
    }

    const metrics = dashboard.data.metrics || {};
    const kpis = document.getElementById("dashboard-kpis");
    kpis.replaceChildren();

    [
      ["Sales", metrics.sales_amount],
      ["Fuel Stock", metrics.fuel_stock],
      ["Net Litres Sold", metrics.litres_sold],
      ["Cash Short / Over", metrics.cash_short_over],
      ["RTT", metrics.rtt_litres],
      ["RTT Cost", metrics.rtt_cost],
      ["Expenses", metrics.expenses],
      ["Cash Collected", metrics.cash_collected],
      ["POS Collected", metrics.pos_collected],
      ["Expected Sales", metrics.expected_sales],
    ].forEach(([label, value]) => addKpi(kpis, label, value));

    document.getElementById("dashboard-updated").textContent =
      `Dashboard date: ${dashboard.data.date || "—"} · Updated ${dashboard.updated_at || "—"}.`;

    const tankRows = (metrics.tank_levels || []).map(tank => [
      tank[0], tank[1], tank[3], tank[2], tank[4], tank[5], tank[8],
    ]);

    renderTable(
      document.querySelector("#tank-rows").closest("table").tHead,
      document.getElementById("tank-rows"),
      ["Tank", "Product", "Stock (L)", "Capacity (L)", "Sold today (L)", "Received today (L)", "Variance (L)"],
      tankRows,
    );

    const lowStock = metrics.low_stock_tanks || [];
    document.getElementById("stock-warning").textContent = lowStock.length
      ? `Restock advised: ${lowStock.map(tank => `${tank[0]} ${tank[1]} (${displayValue(tank[2], "Stock (L)")})`).join(", ")}`
      : tankRows.length ? "All tanks are above the low-stock threshold." : "No tanks have been added.";

    renderTable(
      document.querySelector("#price-rows").closest("table").tHead,
      document.getElementById("price-rows"),
      ["Product", "Current Price", "Previous Price"],
      metrics.selling_prices || [],
    );
  }

  function renderReports(snapshot) {
    const reportData = snapshot.reports.data;
    reports = reportData.reports || {};
    document.getElementById("reports-period").textContent =
      `Published period: ${reportData.period?.from || "—"} to ${reportData.period?.to || "—"} · Updated ${snapshot.reports.updated_at || "—"}.`;

    const summary = document.getElementById("report-summary");
    summary.replaceChildren();
    Object.entries(reportData.summary?.cards || {}).forEach(([label, value]) => addKpi(summary, label, value));

    const select = document.getElementById("report-select");
    const previous = select.value;
    select.replaceChildren();

    Object.keys(reports).forEach(name => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      select.appendChild(option);
    });

    if (Object.hasOwn(reports, previous)) select.value = previous;
    renderSelectedReport();
  }

  async function renderDocuments() {
    const list = document.getElementById("document-list");
    const message = document.getElementById("documents-status");
    const preview = document.getElementById("document-preview");
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
    const report = reports[document.getElementById("report-select").value];
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

  async function loadPageData() {
    requireApi();
    if (!token) {
      window.location.replace("login.html");
      return;
    }

    currentMember = await requestJson("/api/v1/me");
    if (!rolePages[currentMember.role]?.has(page)) {
      const defaultPage = currentMember.role === "member" ? "reports.html" : "dashboard.html";
      window.location.replace(defaultPage);
      return;
    }

    const snapshots = await requestJson("/api/v1/snapshot");
    if (page === "dashboard") renderDashboard(snapshots);
    if (page === "reports") {
      renderReports(snapshots);
      await renderDocuments();
      const exports = document.getElementById("report-exports");
      exports.hidden = !["admin", "super_admin"].includes(currentMember.role);
    }
    if (page === "profile") {
      document.getElementById("profile-email").textContent = currentMember.email;
      document.getElementById("profile-expiry").textContent = new Date(currentMember.expires_at).toLocaleString();
    }

    document.querySelectorAll("[data-page-link]").forEach(link => {
      link.hidden = !rolePages[currentMember.role]?.has(link.dataset.pageLink);
    });

    setStatus("Latest published data loaded.");
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

        window.location.assign(result.role === "member" ? "reports.html" : "dashboard.html");
      } catch (error) {
        setStatus(error.message, true);
      }
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

    loadPageData().catch(error => setStatus(error.message, true));

    if (page === "dashboard" || page === "reports") {
      refreshTimer = setInterval(() => {
        loadPageData().catch(error => setStatus(error.message, true));
      }, 60000);
    }
  }
})();

.kpi{
  background:#132541;
  border: 1px solid #223a57;
  border - radius: 18px;
  padding: 18px;
  box - shadow: 0 8px 24px rgba(0, 0, 0, .25);
}

.kpi - title{
  display: block;
  color: #b8c7db;
  font - size: .9rem;
  margin - bottom: 10px;
}

.kpi - value{
  font - size: 1.8rem;
  font - weight: 700;
}

.hero - kpi{
  grid - column:span 2;
  text - align: center;
}

.hero - kpi.kpi - value{
  font - size: 4rem;
  font - weight: 800;
}

.success{
  color:#22d864;
}

.info{
  color:#46b7ff;
}

.warning{
  color: #ffc83d;
}

.danger{
  color: #ff6b6b;
}

.accent{
  color: #f58220;
}