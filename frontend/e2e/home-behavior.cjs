const assert = require("node:assert/strict");
const { chromium, request } = require("playwright");

const WEB_URL = process.env.GRAPHWORLD_WEB_URL || "http://127.0.0.1:5173";
const API_URL = process.env.GRAPHWORLD_API_URL || "http://127.0.0.1:8010";
const VERSION_ID = "simple_home_1f__v28";

function node(scene, id) {
  const found = scene.nodes.find((item) => item.id === id);
  assert(found, `missing node: ${id}`);
  return found;
}

function edge(scene, targetId) {
  return scene.edges.find((item) => item.target_id === targetId
    && ["at", "in", "on", "inside", "inside_room", "contains", "held_by", "held_by_left", "held_by_right", "held_by_both"].includes(item.relation));
}

function roomFor(scene, nodeId) {
  const rooms = new Set(scene.nodes.filter((item) => item.node_type === "room").map((item) => item.id));
  const seen = new Set();
  let current = nodeId;
  while (current && !seen.has(current)) {
    if (rooms.has(current)) return current;
    seen.add(current);
    current = edge(scene, current)?.source_id || "";
  }
  return "";
}

async function runApiContracts() {
  const api = await request.newContext({ baseURL: API_URL });
  const login = await api.post("/api/auth/login", { data: { username: "admin", password: "admin123" } });
  assert(login.ok(), `API login failed: ${login.status()} ${await login.text()}`);
  const token = (await login.json()).access_token;
  const headers = { Authorization: `Bearer ${token}` };
  const graphResponse = await api.get(`/api/scene-versions/${VERSION_ID}/graph`, { headers });
  assert(graphResponse.ok(), `cannot load ${VERSION_ID}: ${graphResponse.status()} ${await graphResponse.text()}`);
  let scene = (await graphResponse.json()).source_json;
  const actorId = scene.nodes.find((item) => ["robot", "human"].includes(item.node_type))?.id;
  assert(actorId, "v28 has no interactive actor");

  async function interact(targetId, hand = "right", input = "interact_primary", hit = {}) {
    const response = await api.post("/api/scene-simulation/interactions", {
      headers,
      data: { source_json: scene, actor_id: actorId, input, target_id: targetId, hand, hit },
    });
    assert(response.ok(), `interaction HTTP failure for ${targetId}: ${response.status()} ${await response.text()}`);
    const result = await response.json();
    assert(result.applied, `interaction rejected for ${targetId}: ${result.failures.join("; ")}`);
    scene = result.source_json;
    return result;
  }

  async function navigateTo(targetId) {
    const goal = roomFor(scene, targetId) || targetId;
    let current = roomFor(scene, actorId);
    if (current === goal) return;
    const neighbors = new Map();
    for (const item of scene.edges.filter((candidate) => candidate.relation === "connected")) {
      if (!neighbors.has(item.source_id)) neighbors.set(item.source_id, []);
      if (!neighbors.has(item.target_id)) neighbors.set(item.target_id, []);
      neighbors.get(item.source_id).push(item.target_id);
      neighbors.get(item.target_id).push(item.source_id);
    }
    const queue = [[current]];
    const visited = new Set([current]);
    let path = null;
    while (queue.length) {
      const candidate = queue.shift();
      if (candidate.at(-1) === goal) { path = candidate; break; }
      for (const next of neighbors.get(candidate.at(-1)) || []) {
        if (!visited.has(next)) { visited.add(next); queue.push([...candidate, next]); }
      }
    }
    assert(path, `no room path from ${current} to ${goal}`);
    for (const roomId of path.slice(1)) {
      const door = scene.nodes.find((item) => item.semantic_type === "door"
        && Array.isArray(item.connected_rooms)
        && item.connected_rooms.includes(current)
        && item.connected_rooms.includes(roomId));
      if (door && !door.states?.is_open) await interact(door.id);
      await interact(roomId, "right", "move");
      current = roomId;
    }
  }

  async function tick(steps = 1) {
    const response = await api.post("/api/scene-simulation/ticks", {
      headers,
      data: { source_json: scene, elapsed_steps: steps },
    });
    assert(response.ok(), `tick HTTP failure: ${response.status()} ${await response.text()}`);
    const result = await response.json();
    assert(result.applied, `tick rejected: ${result.failures?.join("; ") || "unknown failure"}`);
    scene = result.source_json;
    return result;
  }

  await navigateTo("light_bathroom");
  const lightOn = await interact("light_bathroom");
  assert.equal(node(scene, "light_bathroom").states.is_on, true);
  assert(lightOn.delta.state_changes.some((change) => change.node_id === "light_bathroom" && change.state === "is_on"));
  await interact("light_bathroom");
  assert.equal(node(scene, "light_bathroom").states.is_on, false);

  await interact("faucet_bathroom");
  assert.equal(node(scene, "faucet_bathroom").states.is_on, true);
  assert.equal(node(scene, "sink_bathroom").states.water_flowing, true);
  await tick();
  assert(node(scene, "sink_bathroom").states.water_level > 0);
  await interact("faucet_bathroom");
  assert.equal(node(scene, "sink_bathroom").states.water_flowing, false);

  await navigateTo("clothes_bedroom_1");
  if (!node(scene, "wardrobe_bedroom").states.is_open) await interact("wardrobe_bedroom");
  await interact("clothes_bedroom_1", "right");
  await interact("clothes_bedroom_2", "left");
  assert.equal(edge(scene, "clothes_bedroom_1").relation, "held_by");
  assert.equal(edge(scene, "clothes_bedroom_2").relation, "held_by_left");

  await navigateTo("washer_bathroom");
  await interact("washer_bathroom_door");
  await interact("washer_bathroom_slot_l1_c1", "right", "interact_primary", { volume_uv: [0.25, 0.5, 0.5] });
  await interact("washer_bathroom_slot_l1_c1", "left", "interact_primary", { volume_uv: [0.75, 0.5, 0.5] });
  assert.equal(edge(scene, "clothes_bedroom_1").source_id, "washer_bathroom_slot_l1_c1");
  assert.equal(edge(scene, "clothes_bedroom_2").source_id, "washer_bathroom_slot_l1_c1");
  await interact("washer_bathroom_door");
  await interact("washer_bathroom_button");
  assert.equal(node(scene, "washer_bathroom").states.is_running, true);
  const before = node(scene, "washer_bathroom").states.cycle_remaining;
  const progress = await tick();
  assert.equal(node(scene, "washer_bathroom").states.cycle_remaining, before - 1);
  assert(progress.delta.state_changes.some((change) => change.node_id === "washer_bathroom" && change.state === "cycle_remaining"));
  await interact("washer_bathroom_button");
  assert.equal(node(scene, "washer_bathroom").states.is_running, false);

  await navigateTo("shoe_rack_entrance");
  await interact("shoes_entrance_1", "right");
  await interact("shoe_rack_entrance", "right");
  assert.equal(edge(scene, "shoes_entrance_1").source_id, "shoe_rack_entrance");
  assert.equal(edge(scene, "shoes_entrance_1").relation, "on");
  await interact("shoes_entrance_1", "right");
  await interact("entrance", "right", "release");
  assert.equal(edge(scene, "shoes_entrance_1").source_id, "entrance");
  assert.notEqual(edge(scene, "shoes_entrance_1").relation, "held_by");

  await api.dispose();
  return { actorId, nodeCount: scene.nodes.length, edgeCount: scene.edges.length };
}

async function runBrowserSmoke() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto(WEB_URL, { waitUntil: "networkidle" });
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password").fill("admin123");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/scenes/);
  await page.goto(`${WEB_URL}/scenes/simple_home_1f/edit?version=${VERSION_ID}`, { waitUntil: "networkidle" });
  await page.getByRole("tab", { name: "3D" }).click();
  const version = page.getByLabel("Source snapshot");
  await version.waitFor();
  assert.equal(await version.inputValue(), VERSION_ID);
  const canvas = page.locator(".scene3d-stage canvas");
  await canvas.waitFor({ state: "visible" });
  const canvasInfo = await canvas.evaluate((element) => {
    const gl = element.getContext("webgl2") || element.getContext("webgl");
    return { width: element.width, height: element.height, hasWebGL: Boolean(gl), nonBlank: Boolean(gl && gl.getParameter(gl.VENDOR)) };
  });
  assert(canvasInfo.width > 300 && canvasInfo.height > 300, `invalid canvas dimensions: ${JSON.stringify(canvasInfo)}`);
  assert(canvasInfo.hasWebGL && canvasInfo.nonBlank, `3D canvas has no active WebGL renderer: ${JSON.stringify(canvasInfo)}`);
  await page.locator("button.scene3d-simulation-toggle").click();
  await page.locator(".scene3d-simulation-hint").waitFor({ state: "visible" });
  await page.screenshot({ path: "e2e/home-v28-3d.png", fullPage: true });
  await browser.close();
  return canvasInfo;
  await page.getByRole("button", { name: /开始仿真/ }).click();
  await page.getByText(/Q\/E 交互/).waitFor();
  assert.equal(errors.length, 0, `browser errors:\n${errors.join("\n")}`);
  const screenshot = await canvas.screenshot({ path: "e2e/home-v28-3d.png" });
  assert(screenshot.length > 10000, `3D canvas screenshot is unexpectedly small: ${screenshot.length}`);
  await browser.close();
  return canvasInfo;
}

(async () => {
  const api = await runApiContracts();
  const canvas = await runBrowserSmoke();
  console.log(JSON.stringify({ ok: true, version: VERSION_ID, api, canvas }, null, 2));
})().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
