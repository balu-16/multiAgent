import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { randomBytes } from "node:crypto";
import { chromium, expect } from "@playwright/test";

const output = new URL("../artifacts/", import.meta.url);
const screenshots = new URL("screenshots/", output);
await mkdir(screenshots, { recursive: true });
const checks = [];
const errors = [];
let browser;
let page;
const check = (name, condition, detail = {}) => {
  assert.ok(condition, name);
  const result = { name, passed: true, ...detail };
  checks.push(result);
  console.log(JSON.stringify(result));
};
const shot = async (name) => {
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: new URL(name + ".png", screenshots).pathname, fullPage: true, animations: "disabled" });
};
const noOverflow = async (name) => {
  const dimensions = await page.evaluate(() => ({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth }));
  if (dimensions.scrollWidth > dimensions.width + 1) {
    console.log(JSON.stringify({ layout_overflow: await page.evaluate(() => [...document.querySelectorAll("body *")].map((element) => ({ tag: element.tagName, class: element.className?.toString(), left: element.getBoundingClientRect().left, right: element.getBoundingClientRect().right })).filter((element) => element.left < -1 || element.right > innerWidth + 1).slice(0, 12)), ...dimensions }));
  }
  check(name, dimensions.scrollWidth <= dimensions.width + 1, dimensions);
};

try {
  browser = await chromium.launch({ headless: true, channel: "chromium" });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: "reduce" });
  const marker = await context.request.get("http://localhost:8000/__integration");
  assert.equal(marker.status(), 200, "Browser harness requires the separate integration fixture backend");
  assert.equal((await marker.json()).fixture, true);
  await context.addInitScript(() => {
    const OriginalSocket = window.WebSocket;
    window.__backchannelTestSockets = [];
    window.WebSocket = class extends OriginalSocket {
      constructor(...args) {
        super(...args);
        window.__backchannelTestSockets.push(this);
      }
    };
  });
  page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  const requests = [];
  let socketCount = 0;
  page.on("request", (request) => {
    if (request.url().includes(":8000/api/")) requests.push({ method: request.method(), path: new URL(request.url()).pathname, body: request.postData() });
  });
  page.on("websocket", () => { socketCount += 1; });
  await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
  await expect(page.getByRole("button", { name: "Take a seat" })).toBeVisible();
  check("login_screen", true);
  await shot("login-desktop");
  await page.setViewportSize({ width: 360, height: 800 });
  await noOverflow("login_mobile_no_overflow");
  await shot("login-mobile");
  await page.setViewportSize({ width: 1440, height: 1000 });
  const email = `browser-${randomBytes(6).toString("hex")}@example.com`;
  const password = randomBytes(18).toString("base64url");
  await page.getByRole("button", { name: "Sign up", exact: true }).click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create your account" }).click();
  await expect(page.getByLabel("What’s on your mind?")).toBeVisible();
  const session = (await context.cookies()).find((cookie) => cookie.name === "bc_session");
  check("signup_with_private_cookie", session?.httpOnly === true && session?.sameSite === "Lax");
  check("no_browser_token_storage", await page.evaluate(() => ![...Object.keys(localStorage), ...Object.keys(sessionStorage)].some((key) => /token|jwt|session/i.test(key)) && !document.cookie.includes("bc_session")));
  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByLabel("What’s on your mind?")).toBeVisible();
  check("session_survives_reload", true);
  await shot("setup-desktop");
  await page.setViewportSize({ width: 360, height: 800 });
  await noOverflow("setup_mobile_no_overflow");
  await shot("setup-mobile");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByLabel("What’s on your mind?").fill("Can a group chat turn a weekend idea into a real business?");
  await page.getByLabel("Room for how many messages?").fill("10");
  await page.getByRole("button", { name: /Generate Friend Group/ }).click();
  await expect(page.getByLabel("Friend 1 name")).toBeVisible();
  check("generated_default_four_personas", await page.locator(".persona-card").count() === 4);
  await page.getByLabel("Friend 1 name").fill("Aarav QA");
  await page.getByLabel("Aarav QA role", { exact: true }).fill("The relentless prototype builder");
  await shot("roster-desktop");
  await page.setViewportSize({ width: 360, height: 800 });
  await noOverflow("roster_mobile_no_overflow");
  await shot("roster-mobile");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: /Start Live Group Chat/ }).click();
  await expect(page.locator(".chat-shell")).toBeVisible();
  await expect(page.locator(".message-bubble").first()).toBeVisible();
  const start = requests.findLast((request) => request.path === "/api/rooms/start");
  const submitted = JSON.parse(start.body);
  check("edited_persona_submitted", submitted.personas[0].name === "Aarav QA" && submitted.personas[0].role_in_group === "The relentless prototype builder" && submitted.personas[0].id === "agent_1");
  await shot("live-desktop");
  const beforeReconnect = socketCount;
  const closed = await page.evaluate(() => {
    const socket = window.__backchannelTestSockets.findLast((candidate) => candidate.readyState === 1);
    if (!socket) return false;
    socket.close(4000, "Integration reconnect test");
    return true;
  });
  await expect(page.locator(".message-counter")).toHaveAttribute("aria-label", "10 of 10 messages", { timeout: 20_000 });
  await expect(page.getByText("Saved. Just for you.", { exact: true })).toBeVisible({ timeout: 15_000 });
  check("room_completes_and_saves", true);
  check("socket_reconnect_restores_terminal_room", closed && socketCount > beforeReconnect);
  check("no_duplicate_bubbles_after_reconnect", await page.locator(".message-bubble").count() === 10);
  await page.setViewportSize({ width: 360, height: 800 });
  await noOverflow("chat_mobile_no_overflow");
  await shot("chat-mobile");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "Start another conversation" }).click();
  await expect(page.locator(".archive-card")).toHaveCount(1);
  const beforeArchive = requests.length;
  const socketsBeforeArchive = socketCount;
  await page.locator(".archive-card").click();
  await expect(page.getByText("SAVED CONVERSATION", { exact: true })).toBeVisible();
  await expect(page.locator(".message-bubble")).toHaveCount(10);
  check("archive_opens_without_generation_or_socket", !requests.slice(beforeArchive).some((request) => request.method === "POST") && socketCount === socketsBeforeArchive);
  await shot("archive-desktop");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("button", { name: "Take a seat" })).toBeVisible();
  check("logout_clears_transcript", await page.locator(".message-bubble").count() === 0);
  await page.getByRole("button", { name: "Sign up", exact: true }).click();
  await page.getByLabel("Email address").fill(`browser-other-${randomBytes(6).toString("hex")}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create your account" }).click();
  await expect(page.getByText("Nothing on the shelf. Yet.", { exact: true })).toBeVisible();
  check("second_user_cannot_see_first_archive", await page.locator(".archive-card").count() === 0);
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Take a seat" }).click();
  await expect(page.locator(".archive-card")).toHaveCount(1);
  check("login_restores_own_archive", true);
  check("zero_javascript_runtime_errors", errors.length === 0);
  await context.close();
} catch (error) {
  checks.push({ name: "browser_pipeline_completed", passed: false, error: error.message });
  if (page) await shot("failure").catch(() => {});
  console.error(error.message);
} finally {
  await browser?.close();
  const report = { kind: "deterministic_browser_full_transport", passed: checks.length > 0 && checks.every((check) => check.passed), checks, runtime_errors: errors };
  await writeFile(new URL("browser.json", output), JSON.stringify(report, null, 2) + "\n");
  process.exitCode = report.passed ? 0 : 1;
}
