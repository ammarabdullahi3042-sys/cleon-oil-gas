import { createClient } from "npm:@supabase/supabase-js@2";

function defaultApiKeySet(name: string): string {
  try {
    const value = JSON.parse(Deno.env.get(name) ?? "{}");
    return value && typeof value.default === "string" ? value.default : "";
  } catch {
    return "";
  }
}

const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
const anonKey = defaultApiKeySet("SUPABASE_PUBLISHABLE_KEYS")
  || Deno.env.get("SUPABASE_PUBLISHABLE_KEY")
  || Deno.env.get("SUPABASE_ANON_KEY")
  || "";
const serviceKey = defaultApiKeySet("SUPABASE_SECRET_KEYS")
  || Deno.env.get("SUPABASE_SECRET_KEY")
  || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")
  || "";
const publisherToken = Deno.env.get("CLEON_WEBSITE_PUBLISH_TOKEN") ?? "";
const bucket = "cleon-website-documents";
const maxJsonBytes = 5 * 1024 * 1024;
const maxDocumentBytes = 10 * 1024 * 1024;
const roles = new Set(["super_admin", "admin", "manager", "member", "staff"]);
const roleSections: Record<string, Set<string>> = {
  super_admin: new Set(["dashboard", "reports"]),
  admin: new Set(["dashboard", "reports"]),
  manager: new Set(["dashboard", "reports"]),
  member: new Set(["reports"]),
  staff: new Set(["dashboard", "reports"]),
};
const allowedTypes = new Set([
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/gif",
  "image/webp",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
]);
const previewTypes = new Set([
  "application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp",
]);

const admin = supabaseUrl && serviceKey
  ? createClient(supabaseUrl, serviceKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  })
  : null;

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function json(status: number, body: unknown, headers = new Headers()): Response {
  headers.set("Content-Type", "application/json; charset=utf-8");
  headers.set("Cache-Control", "no-store");
  headers.set("X-Content-Type-Options", "nosniff");
  return new Response(JSON.stringify(body), { status, headers });
}

function corsHeaders(): Headers {
  return new Headers({
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-document-name, x-cleon-publish-token",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  });
}

function bearer(request: Request): string {
  const [scheme, token] = (request.headers.get("Authorization") ?? "").split(/\s+/, 2);
  return scheme?.toLowerCase() === "bearer" ? token ?? "" : "";
}

function tokenExpiry(token: string): string {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return new Date(Number(payload.exp) * 1000).toISOString();
  } catch {
    return new Date().toISOString();
  }
}

function sameSecret(left: string, right: string): boolean {
  if (!left || !right || left.length !== right.length) return false;
  let difference = 0;
  for (let i = 0; i < left.length; i++) difference |= left.charCodeAt(i) ^ right.charCodeAt(i);
  return difference === 0;
}

async function readJson(request: Request, maxBytes = maxJsonBytes): Promise<Record<string, unknown>> {
  const length = Number(request.headers.get("Content-Length") ?? "0");
  if (length > maxBytes) throw new ApiError(413, "Request body is too large.");
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (!bytes.length) throw new ApiError(400, "Request body is required.");
  if (bytes.length > maxBytes) throw new ApiError(413, "Request body is too large.");
  let value: unknown;
  try {
    value = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new ApiError(400, "Request body must be valid JSON.");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError(400, "Request body must be a JSON object.");
  }
  return value as Record<string, unknown>;
}

async function memberFor(request: Request) {
  if (!admin) throw new ApiError(503, "Portal API is not configured on the server.");
  const token = bearer(request);
  if (!token) throw new ApiError(401, "Sign in with a member account.");
  const { data: userResult, error: userError } = await admin.auth.getUser(token);
  if (userError || !userResult.user) throw new ApiError(401, "Your session has expired. Sign in again.");
  const { data: row, error } = await admin
    .from("website_member_roles")
    .select("role, active")
    .eq("user_id", userResult.user.id)
    .maybeSingle();
  if (error) throw new ApiError(500, "Could not verify your portal access.");
  if (!row || row.active !== true || !roles.has(row.role)) {
    throw new ApiError(403, "This account is not enabled for the CLEON member portal.");
  }
  return {
    id: userResult.user.id,
    email: userResult.user.email ?? "",
    role: row.role as string,
    expires_at: tokenExpiry(token),
  };
}

async function authRequest(path: string, token: string, body?: unknown): Promise<Response> {
  const headers = new Headers({ apikey: anonKey, Authorization: `Bearer ${token}` });
  if (body !== undefined) headers.set("Content-Type", "application/json");
  return await fetch(`${supabaseUrl}/auth/v1/${path}`, {
    method: "POST",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function login(body: Record<string, unknown>): Promise<Response> {
  if (!anonKey || !supabaseUrl || !admin) throw new ApiError(503, "Portal API is not configured on the server.");
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  const password = typeof body.password === "string" ? body.password : "";
  if (!email || !password || email.length > 254 || password.length > 1024) {
    throw new ApiError(400, "Enter a valid email and password.");
  }
  const response = await fetch(`${supabaseUrl}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: { apikey: anonKey, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const session = await response.json().catch(() => ({}));
  if (!response.ok || !session.access_token || !session.user?.id) {
    throw new ApiError(401, "Invalid member email or password.");
  }
  const { data: roleRow, error } = await admin
    .from("website_member_roles")
    .select("role, active")
    .eq("user_id", session.user.id)
    .maybeSingle();
  if (error) throw new ApiError(500, "Could not verify portal access.");
  if (!roleRow || roleRow.active !== true || !roles.has(roleRow.role)) {
    await authRequest("logout", session.access_token).catch(() => undefined);
    throw new ApiError(403, "This account is not enabled for the CLEON member portal.");
  }
  return json(200, {
    token: session.access_token,
    refresh_token: session.refresh_token,
    email: session.user.email ?? email,
    role: roleRow.role,
    expires_at: new Date(Number(session.expires_at ?? (Date.now() / 1000 + session.expires_in)) * 1000).toISOString(),
  });
}

function validSnapshot(section: string, payload: Record<string, unknown>): boolean {
  if (typeof payload.published_at !== "string" || !Number.isFinite(Date.parse(payload.published_at))) return false;
  if (section === "dashboard") return typeof payload.date === "string" && !!payload.metrics && typeof payload.metrics === "object";
  const reports = payload.reports;
  return !!payload.period && typeof payload.period === "object"
    && !!payload.summary && typeof payload.summary === "object"
    && !!reports && typeof reports === "object" && !Array.isArray(reports)
    && Object.values(reports as Record<string, unknown>).every((report) => {
      if (!report || typeof report !== "object") return false;
      const item = report as Record<string, unknown>;
      return Array.isArray(item.headers) && Array.isArray(item.rows);
    });
}

function documentName(value: string): string {
  const filename = decodeURIComponent(value).replaceAll("\\", "/").split("/").pop()?.trim() ?? "";
  if (!filename || filename.length > 200 || /[\u0000-\u001f\u007f]/.test(filename)) {
    throw new ApiError(400, "A valid document filename is required.");
  }
  return filename;
}

function contentDisposition(filename: string, disposition: "inline" | "attachment"): string {
  const ascii = filename.replace(/[^\x20-\x7E]/g, "_").replace(/["\\]/g, "_") || "document";
  return `${disposition}; filename="${ascii}"; filename*=UTF-8''${encodeURIComponent(filename)}`;
}

function csvCell(value: unknown): string {
  let text = value == null ? "" : String(value);
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

async function exportCsv(reportName: string, report: Record<string, unknown>, period: Record<string, unknown>): Promise<Response> {
  const rows = report.rows as unknown[][];
  const headers = report.headers as unknown[];
  const lines = [headers.map(csvCell).join(","), ...rows.map((row) => row.map(csvCell).join(","))];
  const body = new TextEncoder().encode(`\uFEFF${lines.join("\r\n")}`);
  const safeName = reportName.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "report";
  const headersOut = corsHeaders();
  headersOut.set("Content-Type", "text/csv; charset=utf-8");
  headersOut.set("Content-Disposition", contentDisposition(`${safeName}_report.csv`, "attachment"));
  headersOut.set("Cache-Control", "no-store");
  return new Response(body, { status: 200, headers: headersOut });
}

function safeReportName(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "report";
}

async function exportXlsx(reportName: string, report: Record<string, unknown>): Promise<Response> {
  const XLSX = await import("npm:xlsx@0.18.5");
  const workbook = XLSX.utils.book_new();
  const sheet = XLSX.utils.aoa_to_sheet([report.headers, ...report.rows as unknown[][]]);
  sheet["!freeze"] = { xSplit: 0, ySplit: 1 };
  XLSX.utils.book_append_sheet(workbook, sheet, reportName.replace(/[\[\]*?:/\\]/g, "_").slice(0, 31) || "Report");
  const bytes = XLSX.write(workbook, { bookType: "xlsx", type: "array" }) as Uint8Array;
  const headersOut = corsHeaders();
  headersOut.set("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  headersOut.set("Content-Disposition", contentDisposition(`${safeReportName(reportName)}_report.xlsx`, "attachment"));
  headersOut.set("Cache-Control", "no-store");
  return new Response(bytes, { status: 200, headers: headersOut });
}

function pdfText(value: unknown): string {
  return (value == null ? "" : String(value)).normalize("NFKD").replace(/[^\x20-\x7E]/g, "?");
}

function fitText(value: unknown, font: { widthOfTextAtSize(text: string, size: number): number }, size: number, width: number): string {
  let text = pdfText(value);
  while (text && font.widthOfTextAtSize(text, size) > width) text = `${text.slice(0, -3)}...`;
  return text;
}

async function exportPdf(
  reportName: string,
  report: Record<string, unknown>,
  period: Record<string, unknown>,
): Promise<Response> {
  const { PDFDocument, StandardFonts, rgb } = await import("npm:pdf-lib@1.17.1");
  const pdf = await PDFDocument.create();
  const font = await pdf.embedFont(StandardFonts.Helvetica);
  const bold = await pdf.embedFont(StandardFonts.HelveticaBold);
  const pageSize: [number, number] = [842, 595];
  const margin = 34;
  const headers = report.headers as unknown[];
  const rows = report.rows as unknown[][];
  const colWidth = (pageSize[0] - margin * 2) / Math.max(headers.length, 1);
  const rowHeight = 15;
  const rowsPerPage = 31;
  const pageCount = Math.max(1, Math.ceil(rows.length / rowsPerPage));
  for (let pageIndex = 0; pageIndex < pageCount; pageIndex++) {
    const page = pdf.addPage(pageSize);
    const { width, height } = page.getSize();
    page.drawText(`CLEON Oil & Gas - ${pdfText(reportName)}`, {
      x: margin, y: height - 38, size: 17, font: bold, color: rgb(0.08, 0.14, 0.21),
    });
    page.drawText(`Period: ${pdfText(period.from)} to ${pdfText(period.to)}    Page ${pageIndex + 1} of ${pageCount}`, {
      x: margin, y: height - 57, size: 9, font, color: rgb(0.28, 0.34, 0.41),
    });
    const tableTop = height - 76;
    page.drawRectangle({ x: margin, y: tableTop - rowHeight, width: width - margin * 2, height: rowHeight, color: rgb(0.14, 0.21, 0.29) });
    headers.forEach((value, column) => page.drawText(fitText(value, bold, 7, colWidth - 8), {
      x: margin + column * colWidth + 4, y: tableTop - 10.5, size: 7, font: bold, color: rgb(1, 1, 1),
    }));
    const pageRows = rows.slice(pageIndex * rowsPerPage, (pageIndex + 1) * rowsPerPage);
    pageRows.forEach((row, rowIndex) => {
      const top = tableTop - rowHeight * (rowIndex + 1);
      const y = top - rowHeight;
      if (rowIndex % 2 === 0) page.drawRectangle({ x: margin, y, width: width - margin * 2, height: rowHeight, color: rgb(0.94, 0.96, 0.98) });
      row.slice(0, headers.length).forEach((value, column) => page.drawText(fitText(value, font, 6.5, colWidth - 8), {
        x: margin + column * colWidth + 4, y: y + 4, size: 6.5, font, color: rgb(0.12, 0.16, 0.2),
      }));
      page.drawLine({ start: { x: margin, y }, end: { x: width - margin, y }, thickness: 0.25, color: rgb(0.78, 0.82, 0.86) });
    });
  }
  const headersOut = corsHeaders();
  headersOut.set("Content-Type", "application/pdf");
  headersOut.set("Content-Disposition", contentDisposition(`${safeReportName(reportName)}_report.pdf`, "attachment"));
  headersOut.set("Cache-Control", "no-store");
  return new Response(await pdf.save(), { status: 200, headers: headersOut });
}

async function handler(request: Request): Promise<Response> {
  const headers = corsHeaders();
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });
  if (!supabaseUrl || !serviceKey || !admin) {
    throw new ApiError(503, "Portal database credentials are not configured on the server.");
  }
  const url = new URL(request.url);
  const marker = "/functions/v1/cleon-portal";
  const markerIndex = url.pathname.indexOf(marker);
  const path = markerIndex >= 0 ? url.pathname.slice(markerIndex + marker.length) || "/" : url.pathname;
  const method = request.method.toUpperCase();
  const incomingToken =
    request.headers.get("X-CLEON-Publish-Token") ?? bearer(request);

  console.log("has_auth_header", !!request.headers.get("Authorization"));
  console.log("has_publish_header", !!request.headers.get("X-CLEON-Publish-Token"));
  console.log("incoming_length", incomingToken.length);
  console.log("expected_length", publisherToken.length);

  const publisher = sameSecret(
    incomingToken,
    publisherToken,
  );

  console.log("publisher_match", publisher);

  if (method === "POST" && path === "/api/v1/login") return await login(await readJson(request, 16 * 1024));
  if (method === "POST" && path === "/api/v1/logout") {
    const token = bearer(request);
    if (token) await authRequest("logout", token).catch(() => undefined);
    return json(200, { logged_out: true });
  }

  const publishMatch = path.match(/^\/api\/v1\/publish\/(dashboard|reports)$/);
  if (method === "POST" && publishMatch) {
    if (!publisherToken) throw new ApiError(503, "Website publishing is not configured on the server.");
    if (!publisher) throw new ApiError(401, "Website publishing authorization required.");
    const section = publishMatch[1];
    const payload = await readJson(request);
    if (!validSnapshot(section, payload)) throw new ApiError(400, `Invalid ${section} snapshot.`);
    const publishedAt = new Date(payload.published_at as string).toISOString();
    const { data: existing, error: existingError } = await admin
      .from("website_snapshots").select("published_at").eq("section", section).maybeSingle();
    if (existingError) throw new ApiError(500, "Could not check the latest published snapshot.");
    if (existing?.published_at && Date.parse(existing.published_at) > Date.parse(publishedAt)) {
      throw new ApiError(409, "A newer snapshot is already published.");
    }
    const { error } = await admin.from("website_snapshots").upsert({
      section, payload, published_at: publishedAt, updated_at: new Date().toISOString(),
    }, { onConflict: "section" });
    if (error) throw new ApiError(500, "Could not publish the snapshot.");
    return json(200, { section, updated_at: new Date().toISOString() });
  }

  if (method === "POST" && path === "/api/v1/documents") {
    if (!publisher) throw new ApiError(401, "Admin publishing authorization required.");
    const filename = documentName(request.headers.get("X-Document-Name") ?? "");
    const contentType = (request.headers.get("Content-Type") ?? "").split(";")[0].toLowerCase();
    if (!allowedTypes.has(contentType)) throw new ApiError(415, "Upload a PDF, image, or Office document.");
    const bytes = new Uint8Array(await request.arrayBuffer());
    if (!bytes.length || bytes.length > maxDocumentBytes) throw new ApiError(413, "Document must be under 10 MB.");
    const signatures: Record<string, number[]> = {
      "application/pdf": [0x25, 0x50, 0x44, 0x46],
      "image/jpeg": [0xff, 0xd8, 0xff],
      "image/png": [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a],
      "image/gif": [0x47, 0x49, 0x46, 0x38],
      "image/webp": [0x52, 0x49, 0x46, 0x46],
    };
    const signature = signatures[contentType];
    if (signature && !signature.every((byte, index) => bytes[index] === byte)) {
      throw new ApiError(415, "File content does not match its type.");
    }
    if (contentType === "image/webp" && new TextDecoder().decode(bytes.slice(8, 12)) !== "WEBP") {
      throw new ApiError(415, "File content does not match its type.");
    }
    const documentId = crypto.randomUUID();
    const storagePath = `${documentId}/${filename}`;
    const { error: uploadError } = await admin.storage.from(bucket).upload(storagePath, bytes, {
      contentType, upsert: false,
    });
    if (uploadError) throw new ApiError(500, "Could not store the document in Supabase Storage.");
    const uploadedAt = new Date().toISOString();
    const { error: rowError } = await admin.from("website_documents").insert({
      document_id: documentId, filename, content_type: contentType, storage_path: storagePath, uploaded_at: uploadedAt,
    });
    if (rowError) {
      await admin.storage.from(bucket).remove([storagePath]);
      throw new ApiError(500, "Could not save document details.");
    }
    return json(201, { document_id: documentId, filename, content_type: contentType, uploaded_at: uploadedAt });
  }

  if (path === "/api/v1/entries/pending" && method === "GET") {
    if (!publisherToken || !publisher) throw new ApiError(401, "Station sync authorization required.");
    const { data, error } = await admin.from("website_entry_submissions")
      .select("entry_id,member_email,entry_type,payload,created_at")
      .eq("status", "pending").order("created_at", { ascending: true }).limit(50);
    if (error) throw new ApiError(500, "Could not load pending station entries.");
    return json(200, { entries: data ?? [] });
  }

  const entryResultMatch = path.match(/^\/api\/v1\/entries\/([^/]+)\/result$/);
  if (entryResultMatch && method === "POST") {
    if (!publisherToken || !publisher) throw new ApiError(401, "Station sync authorization required.");
    const body = await readJson(request, 8 * 1024);
    const status = body.status;
    if (status !== "accepted" && status !== "rejected") throw new ApiError(400, "Choose accepted or rejected.");
    const note = typeof body.note === "string" ? body.note.slice(0, 500) : "";
    const { data, error } = await admin.from("website_entry_submissions")
      .update({ status, processing_note: note, processed_at: new Date().toISOString() })
      .eq("entry_id", entryResultMatch[1]).eq("status", "pending")
      .select("entry_id").maybeSingle();
    if (error) throw new ApiError(500, "Could not update the station entry status.");
    if (!data) throw new ApiError(404, "Pending station entry was not found.");
    return json(200, { entry_id: data.entry_id, status });
  }

  const docMatch = path.match(/^\/api\/v1\/documents\/([^/]+)$/);
  const docList = path === "/api/v1/documents";
  if (method === "GET" && (docList || docMatch)) {
    let member: Awaited<ReturnType<typeof memberFor>> | null = null;
    if (!publisher) member = await memberFor(request);
    if (docList) {
      const { data, error } = await admin.from("website_documents")
        .select("document_id,filename,content_type,uploaded_at")
        .order("uploaded_at", { ascending: false });
      if (error) throw new ApiError(500, "Could not list published documents.");
      return json(200, { documents: (data ?? []).map((item) => ({
        ...item, previewable: previewTypes.has(item.content_type),
      })) });
    }
    const documentId = decodeURIComponent(docMatch![1]);
    const download = url.searchParams.get("download") === "1";
    if (download && !publisher && !["admin", "super_admin"].includes(member!.role)) {
      throw new ApiError(403, "Document downloads require an admin role.");
    }
    const { data: document, error: documentError } = await admin.from("website_documents")
      .select("filename,content_type,storage_path")
      .eq("document_id", documentId).maybeSingle();
    if (documentError) throw new ApiError(500, "Could not read the document details.");
    if (!document) throw new ApiError(404, "Document not found.");
    if (!download && !previewTypes.has(document.content_type)) {
      throw new ApiError(415, "This document type cannot be previewed online.");
    }
    const { data: file, error: fileError } = await admin.storage.from(bucket).download(document.storage_path);
    if (fileError || !file) throw new ApiError(404, "Document file not found.");
    const fileHeaders = corsHeaders();
    fileHeaders.set("Content-Type", document.content_type);
    fileHeaders.set("Content-Disposition", contentDisposition(document.filename, download ? "attachment" : "inline"));
    fileHeaders.set("Cache-Control", "private, no-store");
    fileHeaders.set("X-Content-Type-Options", "nosniff");
    return new Response(file.stream(), { status: 200, headers: fileHeaders });
  }

  const member = await memberFor(request);
  if (method === "GET" && path === "/api/v1/me") return json(200, {
    email: member.email, role: member.role, expires_at: member.expires_at,
  });

  if (method === "GET" && path === "/api/v1/snapshot") {
    const permitted = [...(roleSections[member.role] ?? new Set<string>())];
    const { data, error } = await admin.from("website_snapshots")
      .select("section,payload,updated_at").in("section", permitted);
    if (error) throw new ApiError(500, "Could not read the published dashboard data.");
    return json(200, Object.fromEntries((data ?? []).map((row) => [row.section, {
      data: row.payload, updated_at: row.updated_at,
    }])));
  }

  if (method === "POST" && path === "/api/v1/entries") {
    if (!["staff", "admin", "super_admin"].includes(member.role)) {
      throw new ApiError(403, "Station entry access has not been assigned to this account.");
    }
    const body = await readJson(request, 64 * 1024);
    const entryType = body.entry_type;
    const payload = body.payload;
    if (!["pump_session", "fuel_receipt", "account_activity", "tank_dip"].includes(String(entryType))) {
      throw new ApiError(400, "Choose a supported station entry type.");
    }
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new ApiError(400, "Entry details are required.");
    }
    const item = payload as Record<string, unknown>;
    const numericFields = [
      "opening_meter", "closing_meter", "opening_dip", "closing_dip", "rtt_litres", "cash_collected", "pos_amount", "expenses",
      "invoice_quantity", "actual_quantity", "cost_per_litre", "amount",
    ];
    for (const field of numericFields) {
      if (field in item && (typeof item[field] !== "number" || !Number.isFinite(item[field]) || Number(item[field]) < 0)) {
        throw new ApiError(400, `Enter a valid non-negative ${field.replaceAll("_", " ")}.`);
      }
    }
    for (const [field, value] of Object.entries(item)) {
      if (typeof value === "string" && value.length > 500) {
        throw new ApiError(400, `${field.replaceAll("_", " ")} is too long.`);
      }
    }
    const required: Record<string, string[]> = {
      pump_session: ["pump_number", "attendant_name", "session_date", "opening_meter", "closing_meter"],
      fuel_receipt: ["tank", "product", "receipt_date", "supplier", "invoice_number", "invoice_quantity", "actual_quantity", "cost_per_litre", "vehicle_number", "driver_name", "driver_phone"],
      account_activity: ["transaction_type", "transaction_date", "amount", "account", "reference"],
      tank_dip: ["tank", "dip_date", "opening_dip", "closing_dip"],
    };
    for (const field of required[String(entryType)]) {
      if (item[field] === undefined || item[field] === null || String(item[field]).trim() === "") {
        throw new ApiError(400, `Complete the ${field.replaceAll("_", " ")} field.`);
      }
    }
    if (entryType === "pump_session") {
      if (Number(item.closing_meter) < Number(item.opening_meter)) throw new ApiError(400, "Closing meter cannot be below opening meter.");
      if (Number(item.rtt_litres ?? 0) > Number(item.closing_meter) - Number(item.opening_meter)) throw new ApiError(400, "RTT litres cannot exceed meter movement.");
    }
    if (entryType === "fuel_receipt") {
      if (!(["PMS", "AGO"].includes(String(item.product).trim().toUpperCase()))) throw new ApiError(400, "Choose PMS or AGO for the receipt product.");
      if (["invoice_quantity", "actual_quantity", "cost_per_litre"].some((field) => Number(item[field]) <= 0)) throw new ApiError(400, "Receipt quantities and cost must be greater than zero.");
    }
    if (entryType === "account_activity") {
      const ledgerTypes = ["Account Receipt", "Cash Count", "Cash Expense", "POS Transaction", "Account Expense", "Product Payment", "Bank Deposit", "Account Payment / Amount Sent", "Account Transfer", "Opening Balance"];
      if (!ledgerTypes.includes(String(item.transaction_type))) throw new ApiError(400, "Choose a valid account activity type.");
    }
    if (entryType === "tank_dip" && Number(item.opening_dip) === 0 && Number(item.closing_dip) === 0) {
      throw new ApiError(400, "Enter a measured opening or closing stock value.");
    }
    const { data, error } = await admin.from("website_entry_submissions").insert({
      member_id: member.id,
      member_email: member.email,
      entry_type: entryType,
      payload: item,
    }).select("entry_id,created_at").single();
    if (error || !data) throw new ApiError(500, "Could not save this station entry.");
    return json(201, { entry_id: data.entry_id, status: "pending", created_at: data.created_at });
  }

  if (method === "GET" && path === "/api/v1/entries") {
    if (!["staff", "admin", "super_admin"].includes(member.role)) {
      throw new ApiError(403, "Station entry access has not been assigned to this account.");
    }
    const { data, error } = await admin.from("website_entry_submissions")
      .select("entry_id,entry_type,status,created_at,processing_note")
      .eq("member_id", member.id).order("created_at", { ascending: false }).limit(50);
    if (error) throw new ApiError(500, "Could not load your submitted entries.");
    return json(200, { entries: data ?? [] });
  }

  if (method === "GET" && path === "/api/v1/export") {
    if (!["admin", "super_admin"].includes(member.role)) {
      throw new ApiError(403, "Report downloads require an admin role.");
    }
    const { data: snapshot, error } = await admin.from("website_snapshots")
      .select("payload").eq("section", "reports").maybeSingle();
    if (error) throw new ApiError(500, "Could not read reports.");
    if (!snapshot) throw new ApiError(404, "No reports have been published.");
    const reportName = url.searchParams.get("report") ?? "";
    const report = snapshot.payload?.reports?.[reportName];
    if (!report || !Array.isArray(report.headers) || !Array.isArray(report.rows)) {
      throw new ApiError(404, "Report not found.");
    }
    const format = (url.searchParams.get("format") ?? "").toLowerCase();
    if (format === "csv") return await exportCsv(reportName, report, snapshot.payload.period ?? {});
    if (format === "xlsx") return await exportXlsx(reportName, report);
    if (format === "pdf") return await exportPdf(reportName, report, snapshot.payload.period ?? {});
    throw new ApiError(400, "Choose csv, xlsx, or pdf.");
  }

  throw new ApiError(404, "Not found.");
}

Deno.serve(async (request) => {
  const headers = corsHeaders();
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });
  try {
    return await handler(request);
  } catch (error) {
    if (error instanceof ApiError) {
      console.log(
        "API_ERROR",
        JSON.stringify({
          status: error.status,
          message: error.message,
        }),
      );

      return json(
        error.status,
        { error: error.message },
        headers,
      );
    }

    console.error("CLEON portal API error", error);

    return json(
      500,
      { error: "The CLEON portal could not complete the request." },
      headers,
    );
  }
});
