const fs = require("fs");
const readline = require("readline");
const { chromium } = require("playwright");

const SERVICE_BASE_URL = "https://pintia.cn";
const CURRENT_USER_URL = "https://passport.pintia.cn/api/u/current";
const PASSPORT_BASE_URL = "https://passport.pintia.cn";
const SERVICE_ORIGINS = [SERVICE_BASE_URL, PASSPORT_BASE_URL];
const ACCOUNT_ID_KEYS = [
  "username",
  "user_name",
  "userName",
  "login",
  "account",
  "account_name",
  "accountName",
  "studentId",
  "student_id",
  "studentNo",
  "student_no",
  "studentNumber",
  "student_number",
  "email",
  "phone",
  "mobile",
  "code",
  "uid",
  "id",
];
const DISPLAY_NAME_KEYS = [
  "nickname",
  "nick_name",
  "nickName",
  "displayName",
  "display_name",
  "realName",
  "real_name",
  "fullName",
  "full_name",
  "name",
  "username",
  "userName",
  "account",
];
const GUEST_MARKERS = [
  "用户不存在",
  "Guest",
  '"guest"',
];

let loginContext = null;
let loginPage = null;
let workerBrowser = null;
let workerContext = null;
let workerPage = null;
let cachedStorageState = null;
let activeProfileDir = "";
let activeBrowserExecutable = "";
let activeStartUrl = SERVICE_BASE_URL;

function resolveBrowserExecutable(explicitPath) {
  const candidates = [
    explicitPath,
    process.env.PTA_BROWSER_EXECUTABLE,
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  ].filter(Boolean);
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  throw new Error("Could not find Edge or Chrome. Set PTA_BROWSER_EXECUTABLE to continue.");
}

function makeResponse(id, ok, data = {}) {
  return { id, ok, ...data };
}

function writeResponse(id, ok, data = {}) {
  process.stdout.write(JSON.stringify(makeResponse(id, ok, data)) + "\n");
}

function normalizeUrl(url, baseUrl = SERVICE_BASE_URL) {
  return new URL(url, baseUrl).toString();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isObject(value) {
  return Boolean(value) && typeof value === "object";
}

function asNonEmptyString(value) {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed || "";
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return "";
}

function domainMatches(hostname, cookieDomain) {
  const normalizedDomain = (cookieDomain || "").replace(/^\./, "").toLowerCase();
  const normalizedHost = (hostname || "").toLowerCase();
  return normalizedHost === normalizedDomain || normalizedHost.endsWith(`.${normalizedDomain}`);
}

function pathMatches(requestPath, cookiePath) {
  const normalizedRequestPath = requestPath || "/";
  const normalizedCookiePath = cookiePath || "/";
  return normalizedRequestPath.startsWith(normalizedCookiePath);
}

function cookieAppliesToUrl(cookie, targetUrl) {
  const url = new URL(targetUrl);
  if (cookie.expires && cookie.expires > 0 && cookie.expires * 1000 <= Date.now()) {
    return false;
  }
  if (cookie.secure && url.protocol !== "https:") {
    return false;
  }
  return domainMatches(url.hostname, cookie.domain) && pathMatches(url.pathname, cookie.path);
}

function cookieHeaderFromStorageState(storageState, targetUrl) {
  const cookies = Array.isArray(storageState && storageState.cookies) ? storageState.cookies : [];
  return cookies
    .filter((cookie) => cookieAppliesToUrl(cookie, targetUrl))
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join("; ");
}

async function refreshCachedStorageState() {
  if (!loginContext) {
    return cachedStorageState;
  }
  cachedStorageState = await loginContext.storageState();
  return cachedStorageState;
}

async function closeLoginContext() {
  if (loginContext) {
    await loginContext.close().catch(() => {});
  }
  loginContext = null;
  loginPage = null;
}

async function closeWorkerContext() {
  if (workerContext) {
    await workerContext.close().catch(() => {});
  }
  workerContext = null;
  workerPage = null;
}

function responseContainsGuest(dataText) {
  const text = String(dataText || "");
  const lower = text.toLowerCase();
  return GUEST_MARKERS.some((marker) => lower.includes(String(marker).toLowerCase()));
}

async function waitForReady(page) {
  await page.waitForLoadState("domcontentloaded", { timeout: 15000 }).catch(() => {});
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
}

async function expandAll(page) {
  for (let round = 0; round < 4; round += 1) {
    const clicked = await page.evaluate(() => {
      const expandPattern = /^(展开|更多|显示全部|查看全部|show more|more)$/i;
      let count = 0;
      const elements = Array.from(
        document.querySelectorAll('button, summary, [role="button"], .cursor-pointer')
      );
      for (const element of elements) {
        const text = (element.textContent || "").replace(/\s+/g, " ").trim();
        const expanded = element.getAttribute("aria-expanded");
        const hidden = element.getAttribute("aria-hidden");
        if (hidden === "true") {
          continue;
        }
        if (expanded === "false" || expandPattern.test(text)) {
          element.click();
          count += 1;
        }
      }
      return count;
    });
    if (!clicked) {
      break;
    }
    await sleep(300);
    await waitForReady(page);
  }
}

async function autoScrollUntilStable(page, options = {}) {
  const selector = options.problemSelector || "";
  const settleRepeats = Math.max(Number(options.settleRepeats || 3), 1);
  const maxScrollSteps = Math.max(Number(options.maxScrollSteps || 20), settleRepeats + 1);
  const scrollDelayMs = Math.max(Number(options.scrollDelayMs || 350), 100);
  let stableRepeats = 0;
  let lastHeight = -1;
  let lastCount = -1;

  for (let step = 0; step < maxScrollSteps; step += 1) {
    await page.evaluate(() => {
      window.scrollTo(0, document.body.scrollHeight);
    });
    await sleep(scrollDelayMs);
    await waitForReady(page);

    const current = await page.evaluate((problemSelector) => {
      return {
        height: document.body ? document.body.scrollHeight : 0,
        count: problemSelector ? document.querySelectorAll(problemSelector).length : 0,
      };
    }, selector);

    if (current.height === lastHeight && current.count === lastCount) {
      stableRepeats += 1;
    } else {
      stableRepeats = 0;
      lastHeight = current.height;
      lastCount = current.count;
    }

    if (stableRepeats >= settleRepeats) {
      break;
    }
  }
}

async function preparePage(page, options = {}) {
  if (options.expandAll) {
    await expandAll(page);
  }
  if (options.autoScroll || options.waitForProblemCountStable) {
    await autoScrollUntilStable(page, options);
  }
}

function selectPreferredField(root, preferredKeys) {
  if (!isObject(root)) {
    return null;
  }
  const priorities = new Map(preferredKeys.map((key, index) => [key.toLowerCase(), index]));
  const queue = [root];
  const seen = new Set();
  let best = null;

  while (queue.length) {
    const value = queue.shift();
    if (!isObject(value) || seen.has(value)) {
      continue;
    }
    seen.add(value);

    if (Array.isArray(value)) {
      for (const item of value) {
        if (isObject(item)) {
          queue.push(item);
        }
      }
      continue;
    }

    for (const [key, fieldValue] of Object.entries(value)) {
      const priority = priorities.get(key.toLowerCase());
      const normalizedValue = asNonEmptyString(fieldValue);
      if (priority !== undefined && normalizedValue) {
        if (!best || priority < best.priority) {
          best = {
            key,
            value: normalizedValue,
            priority,
          };
        }
      }
      if (isObject(fieldValue)) {
        queue.push(fieldValue);
      }
    }
  }

  return best;
}

function extractUserCandidate(payload) {
  if (!isObject(payload)) {
    return null;
  }

  const directCandidates = [
    payload.user,
    payload.data && payload.data.user,
    payload.data && payload.data.result,
    payload.data,
    payload.result && payload.result.user,
    payload.result && payload.result.data,
    payload.result,
    payload,
  ];

  for (const candidate of directCandidates) {
    if (isObject(candidate) && !Array.isArray(candidate)) {
      return candidate;
    }
  }

  return null;
}

function extractUserIdentity(userObject) {
  if (!isObject(userObject)) {
    return {
      accountId: "",
      accountKey: "",
      displayName: "",
      displayKey: "",
    };
  }

  const account = selectPreferredField(userObject, ACCOUNT_ID_KEYS);
  const display = selectPreferredField(userObject, DISPLAY_NAME_KEYS);
  const accountId = account ? account.value : "";
  const displayName = display ? display.value : accountId;

  return {
    accountId,
    accountKey: account ? account.key : "",
    displayName,
    displayKey: display ? display.key : "",
  };
}

function buildAuthenticatedState(userObject) {
  const identity = extractUserIdentity(userObject);
  if (!identity.accountId) {
    return {
      authenticated: true,
      user: userObject,
      accountId: "",
      displayName: identity.displayName || "",
      message: "已检测到登录状态，但无法识别当前账号。",
    };
  }
  return {
    authenticated: true,
    user: userObject,
    accountId: identity.accountId,
    displayName: identity.displayName || identity.accountId,
    message: `已检测到登录账号：${identity.displayName || identity.accountId}`,
  };
}

async function ensureBrowserStarted(payload = {}) {
  const requestedProfileDir = payload.profileDir || activeProfileDir;
  const requestedBrowserExecutable = resolveBrowserExecutable(
    payload.browserExecutable || activeBrowserExecutable
  );
  const requestedStartUrl = payload.startUrl || activeStartUrl || SERVICE_BASE_URL;

  if (!requestedProfileDir) {
    throw new Error("Missing profile directory for browser startup.");
  }

  if (
    loginContext &&
    activeProfileDir === requestedProfileDir &&
    activeBrowserExecutable === requestedBrowserExecutable
  ) {
    loginPage =
      loginPage && !loginPage.isClosed()
        ? loginPage
        : loginContext.pages()[0] || (await loginContext.newPage());
    const currentUrl = loginPage.url();
    activeStartUrl = requestedStartUrl;
    if (requestedStartUrl && currentUrl !== requestedStartUrl) {
      await loginPage.goto(requestedStartUrl, { waitUntil: "domcontentloaded" });
    }
    return;
  }

  await shutdown();

  fs.mkdirSync(requestedProfileDir, { recursive: true });
  loginContext = await chromium.launchPersistentContext(requestedProfileDir, {
    headless: false,
    executablePath: requestedBrowserExecutable,
    viewport: { width: 1440, height: 960 },
    args: ["--disable-blink-features=AutomationControlled"],
  });
  activeProfileDir = requestedProfileDir;
  activeBrowserExecutable = requestedBrowserExecutable;
  activeStartUrl = requestedStartUrl;
  loginPage = loginContext.pages()[0] || (await loginContext.newPage());
  if (requestedStartUrl) {
    await loginPage.goto(requestedStartUrl, { waitUntil: "domcontentloaded" });
  }
}

async function ensureWorkerPage() {
  if (!workerBrowser) {
    workerBrowser = await chromium.launch({
      headless: true,
      executablePath: activeBrowserExecutable,
    });
  }
  await closeWorkerContext();
  const storageState = loginContext ? await refreshCachedStorageState() : cachedStorageState;
  if (!storageState) {
    throw new Error("Browser has not been started yet.");
  }
  workerContext = await workerBrowser.newContext({
    storageState,
    viewport: { width: 1440, height: 960 },
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  });
  workerPage = await workerContext.newPage();
  return workerPage;
}

async function getCookieHeader(targetUrl) {
  const storageState = loginContext ? await refreshCachedStorageState() : cachedStorageState;
  if (!storageState) {
    throw new Error("Browser has not been started yet.");
  }
  return cookieHeaderFromStorageState(storageState, targetUrl);
}

async function fetchTextWithCookies(targetUrl, extraHeaders = {}) {
  const cookieHeader = await getCookieHeader(targetUrl);
  const headers = {
    accept: "text/html,application/json,text/plain,*/*",
    cookie: cookieHeader,
    "user-agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ...extraHeaders,
  };
  const response = await fetch(targetUrl, { headers });
  const text = await response.text();
  let json = null;
  try {
    json = JSON.parse(text);
  } catch {
    json = null;
  }
  return {
    status: response.status,
    text,
    json,
    headers: Object.fromEntries(response.headers.entries()),
  };
}

async function fetchBinaryWithCookies(targetUrl, extraHeaders = {}) {
  const cookieHeader = await getCookieHeader(targetUrl);
  const headers = {
    accept: "*/*",
    cookie: cookieHeader,
    "user-agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ...extraHeaders,
  };
  const response = await fetch(targetUrl, { headers });
  const arrayBuffer = await response.arrayBuffer();
  return {
    status: response.status,
    bytes: Buffer.from(arrayBuffer),
    headers: Object.fromEntries(response.headers.entries()),
  };
}

async function authState() {
  if (!loginContext && !cachedStorageState) {
    return { authenticated: false, message: "浏览器尚未启动。" };
  }

  const current = await fetchTextWithCookies(CURRENT_USER_URL);
  const text = current.text || "";
  if (current.status >= 400) {
    return {
      authenticated: false,
      message: `登录态校验失败：HTTP ${current.status}`,
      status: current.status,
      raw: text,
    };
  }
  if (responseContainsGuest(text)) {
    return {
      authenticated: false,
      message: "未检测到有效登录状态，请先在浏览器中完成登录。",
      raw: text,
    };
  }

  const candidate = extractUserCandidate(current.json);
  if (candidate && !responseContainsGuest(JSON.stringify(candidate))) {
    return buildAuthenticatedState(candidate);
  }

  return {
    authenticated: false,
    message: "未检测到有效登录状态，请先在浏览器中完成登录。",
    raw: text,
  };
}

async function waitForLogin(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const state = await authState();
    if (state.authenticated) {
      await refreshCachedStorageState();
      await closeLoginContext();
      return {
        ...state,
        loginWindowClosed: true,
      };
    }
    await sleep(1500);
  }
  return {
    authenticated: false,
    message: "等待登录超时，请确认你已在浏览器中完成登录。",
  };
}

async function closeLoginWindow() {
  const state = await authState();
  if (!state.authenticated) {
    throw new Error(state.message || "未检测到有效登录状态。");
  }
  await refreshCachedStorageState();
  await closeLoginContext();
  return {
    ...state,
    loginWindowClosed: true,
    message: "已确认当前账号并关闭登录浏览器窗口。",
  };
}

async function clearOriginStorage(page, originUrl) {
  await page.goto(originUrl, { waitUntil: "domcontentloaded" }).catch(() => {});
  await page.evaluate(async () => {
    try {
      window.localStorage.clear();
    } catch {}
    try {
      window.sessionStorage.clear();
    } catch {}
    try {
      if (window.indexedDB && typeof window.indexedDB.databases === "function") {
        const databases = await window.indexedDB.databases();
        await Promise.all(
          databases.map((entry) => {
            if (!entry || !entry.name) {
              return Promise.resolve();
            }
            return new Promise((resolve) => {
              const request = window.indexedDB.deleteDatabase(entry.name);
              request.onsuccess = () => resolve();
              request.onerror = () => resolve();
              request.onblocked = () => resolve();
            });
          })
        );
      }
    } catch {}
  });
}

async function switchAccount(payload = {}) {
  await ensureBrowserStarted(payload);
  await closeWorkerContext();
  cachedStorageState = null;

  if (!loginContext) {
    throw new Error("Browser has not been started yet.");
  }

  await loginContext.clearCookies().catch(() => {});
  loginPage =
    loginPage && !loginPage.isClosed()
      ? loginPage
      : loginContext.pages()[0] || (await loginContext.newPage());

  for (const origin of SERVICE_ORIGINS) {
    await clearOriginStorage(loginPage, origin);
  }

  const startUrl = payload.startUrl || activeStartUrl || SERVICE_BASE_URL;
  activeStartUrl = startUrl;
  await loginPage.goto(startUrl, { waitUntil: "domcontentloaded" }).catch(() => {});
  await waitForReady(loginPage);
  await refreshCachedStorageState();

  return {
    authenticated: false,
    accountId: "",
    displayName: "",
    message: "已清除 PTA 登录态，请在浏览器中登录目标账号。",
    finalUrl: startUrl,
  };
}

async function snapshotPage(payload) {
  const auth = await authState();
  if (!auth.authenticated) {
    throw new Error(auth.message);
  }

  const page = await ensureWorkerPage();
  const targetUrl = normalizeUrl(payload.url);
  await page.goto(targetUrl, { waitUntil: "domcontentloaded" });
  await waitForReady(page);
  await preparePage(page, payload.options || {});

  const result = await page.evaluate((problemSelector) => {
    const bodyText = document.body ? document.body.innerText : "";
    const links = Array.from(document.querySelectorAll("a[href]")).map((anchor) => ({
      text: (anchor.textContent || "").replace(/\s+/g, " ").trim(),
      href: anchor.href,
    }));
    return {
      finalUrl: window.location.href,
      title: document.title || "",
      html: document.documentElement.outerHTML,
      links,
      bodyText,
      problemCount: problemSelector ? document.querySelectorAll(problemSelector).length : 0,
    };
  }, payload.options && payload.options.problemSelector ? payload.options.problemSelector : "");

  if (
    result.bodyText.includes("用户不存在") ||
    (result.bodyText.includes("错误信息") && result.bodyText.includes("重新加载"))
  ) {
    throw new Error("登录态无效或页面返回错误页，请重新登录 PTA。");
  }

  return result;
}

async function downloadBinary(payload) {
  const auth = await authState();
  if (!auth.authenticated) {
    throw new Error(auth.message);
  }
  const url = normalizeUrl(payload.url, payload.baseUrl || SERVICE_BASE_URL);
  const headers = {};
  if (payload.referer) {
    headers.referer = payload.referer;
  }
  const response = await fetchBinaryWithCookies(url, headers);
  if (response.status >= 400) {
    throw new Error(`图片下载失败：HTTP ${response.status}`);
  }
  return {
    url,
    contentType: response.headers["content-type"] || "application/octet-stream",
    dataBase64: response.bytes.toString("base64"),
  };
}

async function shutdown() {
  await closeWorkerContext();
  if (workerBrowser) {
    await workerBrowser.close().catch(() => {});
  }
  await closeLoginContext();
  workerBrowser = null;
  cachedStorageState = null;
  activeProfileDir = "";
  activeBrowserExecutable = "";
  activeStartUrl = SERVICE_BASE_URL;
}

async function handleCommand(id, command, payload) {
  if (command === "ensure_browser_started") {
    await ensureBrowserStarted(payload);
    return {
      message: "浏览器已打开，等待登录完成。",
      finalUrl: payload.startUrl || activeStartUrl || SERVICE_BASE_URL,
      title: "PTA Login",
    };
  }
  if (command === "wait_for_login") {
    return await waitForLogin(Number(payload.timeoutMs || 300000));
  }
  if (command === "is_authenticated") {
    return await authState();
  }
  if (command === "get_current_user") {
    return await authState();
  }
  if (command === "close_login_window") {
    return await closeLoginWindow();
  }
  if (command === "switch_account") {
    return await switchAccount(payload);
  }
  if (command === "snapshot") {
    return await snapshotPage(payload);
  }
  if (command === "download") {
    return await downloadBinary(payload);
  }
  if (command === "shutdown") {
    await shutdown();
    return { message: "浏览器服务已关闭。" };
  }
  throw new Error(`Unsupported command: ${command}`);
}

function startService() {
  const readlineInterface = readline.createInterface({
    input: process.stdin,
    crlfDelay: Infinity,
  });

  readlineInterface.on("line", async (line) => {
    if (!line.trim()) {
      return;
    }
    let envelope;
    try {
      envelope = JSON.parse(line);
    } catch (error) {
      writeResponse("unknown", false, { message: `Invalid JSON input: ${error.message}` });
      return;
    }
    const { id = "unknown", command, payload = {} } = envelope;
    try {
      const data = await handleCommand(id, command, payload);
      writeResponse(id, true, data);
      if (command === "shutdown") {
        process.exit(0);
      }
    } catch (error) {
      writeResponse(id, false, {
        message: error && error.message ? error.message : String(error),
      });
    }
  });

  process.on("SIGTERM", async () => {
    await shutdown();
    process.exit(0);
  });
}

module.exports = {
  extractUserCandidate,
  extractUserIdentity,
  responseContainsGuest,
};

if (require.main === module) {
  startService();
}
