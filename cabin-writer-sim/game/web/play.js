"use strict";

const $ = (id) => document.getElementById(id);
const actionParameters = new WeakMap();
const heldDirections = new Map();
const movementQueue = [];
const directions = { w: [0, -1], arrowup: [0, -1], s: [0, 1], arrowdown: [0, 1],
  a: [-1, 0], arrowleft: [-1, 0], d: [1, 0], arrowright: [1, 0] };
const npcColors = { mira: "#dfbd78", nessa: "#85b7c1", rowan: "#8baa79",
  jun: "#dba8a0", ada: "#bca6ca", tomas: "#c99772" };
const organNotes = {
  brain: "Vital. Vulnerable to temperature extremes and blood loss.",
  heart: "Vital. Circulation suffers from bleeding, heat and dehydration.",
  lungs: "Vital. Damage increases the energy cost of exertion.",
  liver: "Damage makes illness more harmful.",
  kidneys: "Damage increases water loss; dehydration injures them.",
  stomach: "Damage reduces the nourishment absorbed from food.",
  skin: "Cold and infected wounds damage your protective barrier.",
  arms: "Damage reduces bow accuracy.",
  legs: "Damage slows walking and makes journeys take longer.",
};
let state = null;
let token = "";
let busy = false;
let wholeScene = false;
let lastStep = 0;
let lastMove = 0;
let view = { tile: 48, x: 0, y: 0 };

function node(tag, text = "", className = "") {
  const result = document.createElement(tag);
  result.textContent = text;
  if (className) result.className = className;
  return result;
}

function pretty(value) { return value.replaceAll("_", " "); }
function color(ratio) { return ratio > 0.65 ? "#93b387" : ratio > 0.3 ? "#d7ad67" : "#db8774"; }

function bar(value, maximum = 100, label = "") {
  const result = document.createElement("progress");
  result.max = maximum;
  result.value = value;
  result.classList.toggle("low", value / maximum < 0.25);
  result.setAttribute("aria-label", label);
  return result;
}

function actionButton(text, action, parameters = {}) {
  const result = node("button", text);
  result.type = "button";
  result.dataset.action = action;
  actionParameters.set(result, parameters);
  return result;
}

function parametersFor(button) {
  if (actionParameters.has(button)) return actionParameters.get(button);
  switch (button.dataset.action) {
    case "eat": return { item: $("food").value };
    case "cook": return { item: $("raw-food").value };
    case "drink": return { unsafe: button.dataset.unsafe === "true" };
    case "hunt": return $("hunt-target").value ? { target: Number($("hunt-target").value) } : {};
    case "wait": return { minutes: Number($("wait-minutes").value) };
    case "research": return { topic: $("topic").value };
    default: return {};
  }
}

function nearby(id) { return state.npcs.find((npc) => npc.id === id)?.nearby ?? false; }

function nearTree() {
  if (state.scene.indoors) return false;
  const { x, y } = state.player;
  for (let dy = -2; dy <= 2; dy++) {
    for (let dx = -2; dx <= 2; dx++) {
      if (state.scene.grid[y + dy]?.[x + dx] === "T") return true;
    }
  }
  return false;
}

function available(action, parameters = {}) {
  if (!state?.player.alive) return false;
  const p = state.player;
  switch (action) {
    case "fish": return state.at_water && p.inventory.bait > 0 && state.fish_stock > 0 && p.needs.energy >= 15;
    case "hunt": return p.inventory.arrows > 0 && p.needs.energy >= 25 && state.animals.some((animal) => animal.huntable);
    case "forage": case "gather_wood": return nearTree() && p.needs.energy >= 15;
    case "drink": return parameters.unsafe ? state.at_water : p.inventory.water > 0;
    case "refill": return ["cabin", "cafe"].includes(p.scene);
    case "eat": return parameters.item === "meal" ? p.meals > 0 : p.inventory[parameters.item] > 0;
    case "cook": return state.stations.stove && state.fire_minutes >= 30 && p.inventory[parameters.item] > 0;
    case "light_fire": return state.stations.stove && p.inventory.firewood > 0;
    case "sleep": return state.stations.bed;
    case "wash": return ["cabin", "cafe", "chapel"].includes(p.scene);
    case "read": return ["cabin", "cafe", "library", "lookout_cabin"].includes(p.scene);
    case "medicine": return p.inventory.medicine > 0 && p.conditions.some((value) => ["Food poisoning", "Wound infection"].includes(value));
    case "bandage": return p.inventory.bandage > 0 && (p.bleeding > 0 || p.organs.some((organ) => ["skin", "arms", "legs"].includes(organ.id) && organ.hp < organ.max));
    case "clinic": return nearby("jun") && p.money >= 25;
    case "write": return state.stations.desk && state.book !== null && p.needs.energy >= 30 && p.needs.satiety >= 15 && p.hp >= 300 && p.paper > 0;
    case "research": return p.scene === "library";
    case "talk": return nearby(parameters.npc);
    case "equip": return p.gear.includes(parameters.item) && p.clothing !== parameters.item;
    case "buy": {
      const item = state.catalogue.find((product) => product.id === parameters.item);
      return nearby("mira") && item && !item.owned && item.cost <= p.money;
    }
    case "sell": return nearby("mira") && p.inventory[parameters.item] >= parameters.amount;
    case "accept_quest": case "deliver_quest": {
      const quest = state.quests.find((value) => value.id === parameters.quest);
      return quest && nearby(quest.npc) && (action === "accept_quest" ? quest.status === "available" :
        quest.status === "active" && p.inventory[quest.item] >= quest.amount);
    }
    case "travel": return parameters.destination !== p.scene;
    default: return true;
  }
}

function updateButtons() {
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.disabled = busy || !available(button.dataset.action, parametersFor(button));
  });
  document.querySelectorAll("[data-direction]").forEach((button) => { button.disabled = !state?.player.alive; });
  $("begin-book").disabled = busy || !state?.player.alive || state.book !== null;
  $("new-life").disabled = busy || !state;
  $("restart").disabled = busy;
}

function announce(message, error = false) {
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
  $("notice").setAttribute("aria-live", error ? "assertive" : "polite");
}

function stopMovement() {
  heldDirections.clear();
  movementQueue.length = 0;
}

async function perform(action, parameters = {}, endpoint = "/api/action") {
  if (busy || !state) return;
  if (action !== "move") stopMovement();
  busy = true;
  updateButtons();
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Cabin-Token": token },
      body: JSON.stringify(action === null ? { confirm: true } : { action, ...parameters }),
    });
    const result = await response.json();
    if (result.state) render(result.state);
    if (!response.ok) throw new Error(result.error || `Game request failed (${response.status}).`);
    announce(result.message);
  } catch (error) {
    stopMovement();
    announce(error instanceof Error ? error.message : "The game could not receive your action.", true);
  } finally {
    busy = false;
    updateButtons();
  }
}

function selectOptions(id, options, empty) {
  const select = $(id);
  const previous = select.value;
  select.replaceChildren(...(options.length ? options : [["", empty]]).map(([value, label]) => {
    const option = node("option", label);
    option.value = value;
    return option;
  }));
  if (options.some(([value]) => String(value) === previous)) select.value = previous;
}

function selectTab(name) {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    const selected = button.dataset.tab === name;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    $(`panel-${button.dataset.tab}`).hidden = !selected;
  });
}

function renderVitals() {
  const p = state.player;
  $("total-hp").textContent = `${p.hp.toLocaleString("en-GB")} / 1,000 HP`;
  $("total-hp").style.color = color(p.hp / p.max_hp);
  $("hp-segments").replaceChildren(...p.organs.map((organ) => {
    const segment = node("div", "", "hp-segment");
    const ratio = organ.hp / organ.max;
    segment.style.flexGrow = organ.max;
    segment.style.background = `linear-gradient(to right, ${color(ratio)} ${ratio * 100}%, #26372c ${ratio * 100}%)`;
    segment.title = `${organ.name}: ${organ.hp}/${organ.max} HP${organ.vital ? " (vital)" : ""}`;
    return segment;
  }));
  $("hp-segments").setAttribute("aria-label", p.organs.map((organ) => `${organ.name} ${organ.hp} of ${organ.max} HP`).join(", "));
  $("needs").replaceChildren(...[
    ["Food", p.needs.satiety], ["Energy", p.needs.energy],
    ["Water", p.hydration], ["Hygiene", p.needs.hygiene],
  ].map(([label, value]) => {
    const container = node("div");
    const heading = node("div", "", "need-label");
    heading.append(node("span", label), node("span", `${Math.round(value)}%`));
    container.append(heading, bar(value, 100, label));
    return container;
  }));
  $("body-stats").replaceChildren(...[
    ["Core temperature", `${p.temperature.toFixed(2)} C`],
    ["Hydration", `${p.hydration.toFixed(0)}%`],
    ["Clothing wetness", `${p.wetness.toFixed(0)}%`],
    ["Blood volume", `${p.blood.toFixed(0)}%`],
  ].map(([label, value]) => {
    const stat = node("div", label, "body-stat");
    stat.append(node("strong", value));
    return stat;
  }));
  $("conditions").replaceChildren(...(p.conditions.length ? p.conditions.map((value) =>
    node("span", value, "condition")) : [node("span", "Stable", "condition healthy")]));
  $("organ-list").replaceChildren(...p.organs.map((organ) => {
    const row = node("div", "", "organ");
    row.append(node("strong", `${organ.name}${organ.vital ? " / vital" : ""}`),
      node("span", `${organ.hp.toFixed(1)} / ${organ.max} HP`, "muted"),
      bar(organ.hp, organ.max, `${organ.name} health`), node("small", organNotes[organ.id]));
    return row;
  }));
  $("body-diagram").querySelectorAll("[data-organ]").forEach((part) => {
    const organ = p.organs.find((value) => value.id === part.dataset.organ);
    part.style.fill = color(organ.hp / organ.max);
  });
  $("game-over").hidden = p.alive;
  $("death-reason").textContent = p.conditions.join(", ");
}

function questCard(quest) {
  const card = node("div", "", "quest-card");
  const person = state.npcs.find((npc) => npc.id === quest.npc);
  const count = Math.min(state.player.inventory[quest.item], quest.amount);
  card.append(node("strong", quest.name), node("p", `${person.name} / ${quest.reward} credits`),
    node("p", quest.status === "complete" ? "Completed. Thank you." :
      `${count}/${quest.amount} ${pretty(quest.item)} collected. ${quest.status === "available" ? "Speak to them to accept." : "Return to deliver."}`));
  if (quest.status !== "complete") {
    card.append(actionButton(quest.status === "available" ? "Accept quest" : "Deliver provisions",
      quest.status === "available" ? "accept_quest" : "deliver_quest", { quest: quest.id }));
  }
  return card;
}

function renderNPCs() {
  const people = state.npcs.filter((npc) => npc.scene === state.player.scene);
  $("npc-cards").replaceChildren(...people.map((npc) => {
    const card = node("div", "", "npc-card");
    card.append(node("h4", `${npc.name} / ${npc.role}`));
    card.append(node("p", npc.nearby ? npc.dialogue : npc.open ?
      "Walk within two tiles to talk." : `Away until ${npc.hours[0]}:00. Here until ${npc.hours[1]}:00.`));
    card.append(node("p", `Friendship ${npc.relationship}/100`), actionButton("Talk", "talk", { npc: npc.id }));
    if (npc.id === "jun") card.append(actionButton("Treatment / 25 cr", "clinic"));
    if (npc.id === "mira") {
      const trade = node("button", "Open market");
      trade.type = "button";
      trade.disabled = !npc.nearby;
      trade.addEventListener("click", () => { selectTab("inventory"); $("market").scrollIntoView({ block: "nearest" }); });
      card.append(trade);
    }
    for (const quest of state.quests.filter((value) => value.npc === npc.id)) card.append(questCard(quest));
    return card;
  }));
  if (!people.length) {
    $("npc-cards").append(node("p", state.stations.desk ? "Your desk is close. This is where your writing sessions happen." :
      state.stations.stove ? "The stove is close. Fuel it to cook and warm up." :
      state.stations.bed ? "Your bed is close. Sleep restores energy." :
      "The map shows every building, villager and animal.", "muted"));
  }
}

function renderInventory() {
  const p = state.player;
  $("clothing-list").replaceChildren(...Object.entries(state.clothing).map(([id, clothes]) => {
    const card = node("div", "", `clothing-card${p.clothing === id ? " selected" : ""}`);
    card.append(node("strong", clothes.name + (p.clothing === id ? " / wearing" : "")),
      node("p", clothes.description), node("p", `Insulation ${clothes.insulation} / rain protection ${Math.round(clothes.waterproof * 100)}%`),
      actionButton(p.gear.includes(id) ? "Wear" : "Buy from Mira / 45 cr", p.gear.includes(id) ? "equip" : "buy", { item: id }));
    return card;
  }));
  const supplies = [["Prepared meals", p.meals], ["Writing paper", p.paper],
    ...Object.entries(p.inventory).filter(([, count]) => count > 0).map(([id, count]) => [pretty(id), count])];
  $("inventory-list").replaceChildren(...supplies.map(([label, count]) => {
    const row = node("div", "", "supply-row");
    row.append(node("span", label), node("strong", String(count)));
    return row;
  }));
  $("equipment").textContent = `Equipment: ${p.gear.filter((id) => !Object.hasOwn(state.clothing, id)).map(pretty).join(", ")}.`;
  $("market-hint").textContent = nearby("mira") ? "Mira is here. All prices are in-game credits; no real money moves." :
    "Stand within two tiles of Mira at the General Store (08:00-20:00) to trade.";
  $("shop-list").replaceChildren(...(nearby("mira") ? state.catalogue.map((item) => {
    const row = node("div", "", "shop-row");
    const detail = node("div");
    detail.append(node("span", pretty(item.id)), node("small", item.description));
    row.append(detail, actionButton(item.owned ? "Owned" : `${item.cost} cr`, "buy", { item: item.id }));
    return row;
  }) : []));
  $("sell-list").replaceChildren(...(nearby("mira") ? Object.entries(state.sell_prices).filter(([id]) => p.inventory[id] > 0).map(([id, price]) => {
    const row = node("div", "", "sell-row");
    row.append(node("span", `${pretty(id)} / ${p.inventory[id]} in bag`), actionButton(`Sell one / ${price} cr`, "sell", { item: id, amount: 1 }));
    return row;
  }) : []));
}

function renderJournal() {
  $("quest-list").replaceChildren(...state.quests.map(questCard));
  $("skills").replaceChildren(...Object.entries(state.skills).map(([id, count]) => {
    const row = node("div", "", "supply-row");
    row.append(node("span", pretty(id)), node("strong", `${count} practice`));
    return row;
  }));
  $("skills").append(node("p", `Inspiration ${Math.round(state.player.needs.inspiration)} / social ${Math.round(state.player.needs.social)} / mood ${Math.round(state.player.needs.mood)}.`, "muted"));
  $("books").replaceChildren(...state.books.map((book) => {
    const link = node("a", `${book.title} / ${book.words} words / download EPUB + PDF`, "book-link");
    link.href = `/books/${encodeURIComponent(book.file)}`;
    link.setAttribute("download", "");
    return link;
  }));
  if (!state.books.length) $("books").append(node("p", "No finished books yet. Start a topic, then write at your cabin desk.", "muted"));
  $("event-log").replaceChildren(...state.log.slice().reverse().map((event) => {
    const entry = node("li");
    entry.append(node("small", `${event.t} / ${event.who}`), node("span", event.text));
    return entry;
  }));
}

function renderMapDetails() {
  $("destinations").replaceChildren(...state.world.locations.map((location) =>
    actionButton(location.id === "lakeshore" ? "Lake dock" : location.name.replace(/^the /, ""),
      "travel", { destination: location.id })));
  $("villagers").replaceChildren(...state.npcs.map((npc) => {
    const note = node("div", "", "villager-note");
    note.append(node("strong", `${npc.name} / ${npc.role}`),
      node("span", `${npc.hours[0]}:00-${npc.hours[1]}:00 / ${npc.open ? "here today" : "away"}`));
    return note;
  }));
}

function render(next) {
  if (state && (next.player.x !== state.player.x || next.player.y !== state.player.y || next.player.scene !== state.player.scene)) lastMove = performance.now();
  state = next;
  const p = state.player;
  $("clock").textContent = state.time;
  $("forecast").textContent = `${state.season} / ${state.weather}`;
  $("money").textContent = `${p.money.toFixed(2)} credits`;
  $("location").textContent = state.scene.name;
  $("climate").textContent = state.environment.climate;
  $("environment").textContent = `${state.environment.temperature.toFixed(1)} C air / ${state.environment.wind} km/h wind${state.environment.heated ? " / stove lit" : ""}`;
  $("position").textContent = `Position ${p.x}, ${p.y} / ${p.clothing.replaceAll("_", " ")}`;
  $("game-canvas").setAttribute("aria-label", `${state.scene.name}, position ${p.x}, ${p.y}. ${p.hp} of 1000 HP. WASD or arrows to move.`);
  $("drink-button").textContent = `Drink water / ${p.inventory.water}`;
  $("outdoor-hint").textContent = `Lake stock ${state.fish_stock} / bait ${p.inventory.bait} / arrows ${p.inventory.arrows}. Trees block hunting shots.`;
  $("stove-hint").textContent = state.stations.stove ? `Stove nearby / ${state.fire_minutes} minutes of fuel / ${p.inventory.firewood} wood.` : "Move within two tiles of a cabin or lookout stove.";
  $("book-progress").textContent = state.book ? `${state.book.title}: ${state.book.words}/${state.book.target} words. Paper ${p.paper}.` : "You choose every writing session. Finished books earn royalties.";
  const foods = p.meals > 0 ? [["meal", `Prepared meal / ${p.meals}`]] : [];
  for (const id of ["berries", "cooked_fish", "cooked_meat", "fish", "raw_meat"]) {
    if (p.inventory[id] > 0) foods.push([id, `${pretty(id)} / ${p.inventory[id]}${["fish", "raw_meat"].includes(id) ? " / UNSAFE RAW" : ""}`]);
  }
  selectOptions("food", foods, "No food left");
  selectOptions("raw-food", ["fish", "raw_meat"].filter((id) => p.inventory[id] > 0).map((id) => [id, `${pretty(id)} / ${p.inventory[id]}`]), "No raw food to cook");
  selectOptions("hunt-target", state.animals.filter((animal) => animal.huntable).map((animal) => [String(animal.id), `${animal.kind} / ${animal.x}, ${animal.y}`]), "No animal in clear range");
  renderVitals();
  renderNPCs();
  renderInventory();
  renderJournal();
  renderMapDetails();
  updateButtons();
}

function polygon(ctx, points, fill) {
  ctx.fillStyle = fill;
  ctx.beginPath();
  points.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
  ctx.closePath();
  ctx.fill();
}

function tile(ctx, glyph, x, y, size, time, interior = false) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(size / 16, size / 16);
  const grass = glyph === "G" ? "#3c513b" : "#485f42";
  ctx.fillStyle = ["~", "D"].includes(glyph) ? "#304d5a" : interior ? "#795b3f" : grass;
  ctx.fillRect(0, 0, 16, 16);
  if ("gGTfr".includes(glyph) && !interior) {
    ctx.fillStyle = "#60764b";
    ctx.fillRect((x / size * 7 + y / size * 3) % 13, 5, 1, 3);
    ctx.fillRect(11, 12, 2, 1);
  }
  if (glyph === ".") {
    ctx.fillStyle = "#907653"; ctx.fillRect(0, 0, 16, 16);
    ctx.fillStyle = "#776348"; ctx.fillRect(3, 5, 2, 1); ctx.fillRect(10, 12, 3, 1);
  } else if (glyph === "~" || glyph === "D") {
    ctx.fillStyle = "#426976";
    const ripple = Math.sin(time / 1800 + x) * 2;
    ctx.fillRect(2 + ripple, 5, 7, 1); ctx.fillRect(8 - ripple, 12, 5, 1);
    if (glyph === "D") {
      ctx.fillStyle = "#9a7c54"; ctx.fillRect(2, 0, 12, 16);
      ctx.fillStyle = "#574833";
      for (let line = 0; line < 16; line += 4) ctx.fillRect(2, line, 12, 1);
    }
  } else if (glyph === "T") {
    ctx.fillStyle = "#55412e"; ctx.fillRect(7, 10, 3, 6);
    polygon(ctx, [[1, 12], [8, 2], [15, 12]], "#263e32");
    polygon(ctx, [[2, 8], [8, 0], [14, 8]], "#34563c");
    polygon(ctx, [[5, 3], [8, 0], [11, 3]], "#53754c");
  } else if (glyph === "#") {
    ctx.fillStyle = "#534239"; ctx.fillRect(0, 0, 16, 16);
    ctx.fillStyle = "#796048";
    for (let line = 2; line < 16; line += 4) ctx.fillRect(0, line, 16, 1);
  } else if ("CSLHAK".includes(glyph)) {
    ctx.fillStyle = "#604733"; ctx.fillRect(0, 0, 16, 16);
    ctx.fillStyle = "#be9258"; ctx.fillRect(4, 2, 9, 14);
    ctx.fillStyle = "#392d24"; ctx.fillRect(5, 3, 7, 12);
    ctx.fillStyle = "#d9ba78"; ctx.fillRect(10, 9, 1, 1);
    ctx.fillStyle = "#d8c491"; ctx.font = "6px monospace"; ctx.fillText(glyph, 6, 8);
  } else if (glyph === "w" || glyph === "W") {
    ctx.fillStyle = "#664b33"; ctx.fillRect(0, 0, 16, 16);
    ctx.fillStyle = "#886344"; ctx.fillRect(0, 3, 16, 1); ctx.fillRect(0, 10, 16, 1);
    if (glyph === "W") {
      ctx.fillStyle = "#45616d"; ctx.fillRect(2, 2, 12, 11);
      ctx.fillStyle = "#a4a279"; ctx.fillRect(7, 2, 2, 11); ctx.fillRect(2, 7, 12, 1);
      ctx.fillStyle = "#758d94"; ctx.fillRect(3, 4, 1, 3);
    }
  } else if (glyph === "o" || glyph === "e") {
    ctx.fillStyle = "#ae9769"; ctx.fillRect(0, 0, 16, 16);
    ctx.fillStyle = "#d9c899"; ctx.fillRect(3, 11, 10, 2);
  } else if (interior) {
    ctx.fillStyle = "#906c48"; ctx.fillRect(0, 7, 16, 1); ctx.fillRect(4, 0, 1, 7);
    if (glyph === "b") {
      ctx.fillStyle = "#3b302b"; ctx.fillRect(2, 1, 12, 14);
      ctx.fillStyle = "#acb4a0"; ctx.fillRect(3, 2, 10, 4);
      ctx.fillStyle = "#697f70"; ctx.fillRect(3, 7, 10, 7);
    } else if ("dtua".includes(glyph)) {
      ctx.fillStyle = "#503926"; ctx.fillRect(1, 3, 14, 12);
      ctx.fillStyle = "#b18a55"; ctx.fillRect(0, 1, 16, 10);
      if (glyph === "d") { ctx.fillStyle = "#e6d6a5"; ctx.fillRect(6, 3, 7, 5); ctx.fillStyle = "#6d5d3a"; ctx.fillRect(8, 4, 4, 1); }
    } else if ("ks".includes(glyph)) {
      ctx.fillStyle = "#4d3a2b"; ctx.fillRect(1, 0, 14, 16);
      for (let shelf = 1; shelf < 16; shelf += 6) {
        ["#a59361", "#668176", "#ba865c", "#9d9c87"].forEach((fill, i) => {
          ctx.fillStyle = fill; ctx.fillRect(2 + i * 3, shelf, 2, 4);
        });
      }
    } else if (glyph === "v") {
      ctx.fillStyle = "#333b38"; ctx.fillRect(2, 2, 12, 13);
      ctx.fillStyle = state.fire_minutes > 0 ? "#e9a350" : "#1b2420"; ctx.fillRect(5, 6, 6, 5);
      ctx.fillStyle = "#333b38"; ctx.fillRect(9, 0, 3, 4);
    } else if ("ln".includes(glyph)) {
      ctx.fillStyle = "#e3ba70"; ctx.fillRect(6, 4, 4, 5);
      ctx.fillStyle = "#f4d79b"; ctx.fillRect(7, 3, 2, 3);
      ctx.fillStyle = "#4b3c2c"; ctx.fillRect(7, 9, 2, 5);
    } else if ("cp".includes(glyph)) {
      ctx.fillStyle = "#59412c"; ctx.fillRect(3, 4, 10, 10);
      ctx.fillStyle = "#a07b4d"; ctx.fillRect(3, 2, 10, 4); ctx.fillRect(3, 8, 10, 3);
    } else if (glyph === "r") {
      ctx.fillStyle = "#775444"; ctx.fillRect(0, 1, 16, 14);
      ctx.fillStyle = "#ad8a57"; ctx.fillRect(1, 2, 14, 1); ctx.fillRect(1, 13, 14, 1);
    }
  } else if (glyph === "r") {
    polygon(ctx, [[3, 12], [2, 7], [7, 4], [13, 7], [14, 12]], "#6b7972");
  } else if (glyph === "f") {
    ctx.fillStyle = "#cab58a"; ctx.fillRect(5, 5, 2, 2); ctx.fillRect(10, 10, 2, 2);
  }
  ctx.restore();
}

function person(ctx, x, y, size, coat, facing, walking) {
  ctx.save(); ctx.translate(x, y); ctx.scale(size / 16, size / 16);
  ctx.fillStyle = "#10211766"; ctx.fillRect(4, 14, 9, 2);
  ctx.fillStyle = "#bba077"; ctx.fillRect(6, 3, 5, 5);
  ctx.fillStyle = "#493a2b"; ctx.fillRect(5, 2, 7, 3);
  ctx.fillStyle = coat; ctx.fillRect(5, 8, 7, 5); ctx.fillRect(3, 8, 2, 4); ctx.fillRect(12, 8, 2, 4);
  ctx.fillStyle = "#342f29"; ctx.fillRect(5, 13, 3, walking ? 2 : 3); ctx.fillRect(9, walking ? 14 : 13, 3, 2);
  if (facing !== "up") { ctx.fillStyle = "#342c25"; ctx.fillRect(facing === "left" ? 6 : 10, 5, 1, 1); }
  ctx.restore();
}

function animalSprite(ctx, animal, x, y, size) {
  ctx.save(); ctx.translate(x, y); ctx.scale(size / 16, size / 16);
  const deer = animal.kind === "deer";
  ctx.fillStyle = deer ? "#ac9870" : "#c6c5ac";
  ctx.fillRect(3, 7, 9, 6); ctx.fillRect(10, deer ? 3 : 4, 4, 6);
  ctx.fillRect(4, 12, 2, 3); ctx.fillRect(10, 12, 2, 3);
  ctx.fillRect(10, 1, 1, deer ? 4 : 5); ctx.fillRect(13, 0, 1, deer ? 4 : 5);
  if (deer) { ctx.fillRect(8, 2, 3, 1); ctx.fillRect(13, 2, 3, 1); }
  ctx.fillStyle = "#273d31"; ctx.fillRect(12, 6, 1, 1);
  ctx.restore();
}

function label(ctx, text, x, y, fill = "#e7d4a1", font = 11) {
  ctx.font = `${font}px system-ui`;
  const width = ctx.measureText(text).width;
  ctx.fillStyle = "#17231ed9"; ctx.fillRect(x - width / 2 - 4, y - font, width + 8, font + 4);
  ctx.fillStyle = fill; ctx.fillText(text, x - width / 2, y);
}

function drawScene(now) {
  const canvas = $("game-canvas");
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = "#1c241e"; ctx.fillRect(0, 0, canvas.width, canvas.height);
  const grid = state.scene.grid;
  const p = state.player;
  let size = state.scene.indoors ? 48 : wholeScene ? 16 : 32;
  let ox = (canvas.width - grid[0].length * size) / 2;
  let oy = (canvas.height - grid.length * size) / 2;
  if (!state.scene.indoors && !wholeScene) {
    ox = -Math.max(0, Math.min(grid[0].length - canvas.width / size, Math.floor(p.x - canvas.width / size / 2))) * size;
    oy = -Math.max(0, Math.min(grid.length - canvas.height / size, Math.floor(p.y - canvas.height / size / 2))) * size;
  }
  view = { tile: size, x: ox, y: oy };
  grid.forEach((row, y) => Array.from(row).forEach((glyph, x) => {
    const px = ox + x * size, py = oy + y * size;
    if (px > -size && py > -size && px < canvas.width && py < canvas.height) tile(ctx, glyph, px, py, size, now, state.scene.indoors);
  }));
  if (!state.scene.indoors) {
    state.animals.forEach((animal) => {
      animalSprite(ctx, animal, ox + animal.x * size, oy + animal.y * size, size);
      if (animal.huntable && size > 16) label(ctx, animal.kind, ox + (animal.x + 0.5) * size, oy + animal.y * size - 2, "#d9d7b5", 10);
    });
  }
  state.npcs.filter((npc) => npc.scene === p.scene && npc.open).forEach((npc) => {
    person(ctx, ox + npc.x * size, oy + npc.y * size, size, npcColors[npc.id], "down", false);
    label(ctx, npc.name, ox + (npc.x + 0.5) * size, oy + npc.y * size - 3, npcColors[npc.id]);
  });
  const coat = { light_clothes: "#a6b19a", raincoat: "#d0a856", winter_coat: "#9b7761" }[p.clothing];
  person(ctx, ox + p.x * size, oy + p.y * size, size, coat, p.facing, now - lastMove < 200);
  label(ctx, "YOU", ox + (p.x + 0.5) * size, oy + p.y * size - 3, "#f3d99d", 10);
  if (state.scene.indoors) {
    const glow = ctx.createRadialGradient(canvas.width / 2, canvas.height / 2, 50, canvas.width / 2, canvas.height / 2, 410);
    glow.addColorStop(0, "#e6ae5420"); glow.addColorStop(1, "#0b151977");
    ctx.fillStyle = glow; ctx.fillRect(0, 0, canvas.width, canvas.height);
  } else {
    const night = state.hour < 6 || state.hour > 19 ? 0.53 : state.weather === "storm" ? 0.22 : 0.05;
    ctx.fillStyle = `rgba(12, 24, 30, ${night})`; ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (state.weather === "fog") { ctx.fillStyle = "#aab8ae35"; ctx.fillRect(0, 0, canvas.width, canvas.height); }
    if (["rain", "storm", "snow"].includes(state.weather)) {
      ctx.strokeStyle = "#c2d4dd60"; ctx.fillStyle = "#e3e8dd9c"; ctx.lineWidth = 1;
      for (let drop = 0; drop < 60; drop++) {
        const x = (drop * 137 + now * 0.05) % canvas.width;
        const y = (drop * 73 + now * (state.weather === "snow" ? 0.03 : 0.2)) % canvas.height;
        if (state.weather === "snow") ctx.fillRect(x, y, 2, 2);
        else { ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - 4, y + 12); ctx.stroke(); }
      }
    }
  }
}

function drawMap(now) {
  const canvas = $("map-canvas");
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  state.world.grid.forEach((row, y) => Array.from(row).forEach((glyph, x) => tile(ctx, glyph, x * 16, y * 16, 16, now)));
  state.world.locations.filter((location) => location.door).forEach((location) => {
    const [x, y] = location.door;
    label(ctx, location.name.replace(/^the /, ""), (x + 1) * 16, y * 16 - 6, "#e3c791", 10);
  });
  state.animals.forEach((animal) => { ctx.fillStyle = "#cbd2b4"; ctx.fillRect(animal.x * 16 + 6, animal.y * 16 + 6, 4, 4); });
  state.npcs.filter((npc) => npc.open).forEach((npc) => {
    const location = state.world.locations.find((value) => value.id === npc.scene);
    const [x, y] = location?.door ?? [npc.x, npc.y];
    ctx.fillStyle = npcColors[npc.id]; ctx.fillRect(x * 16 + 3, y * 16 + 3, 6, 6);
  });
  const location = state.world.locations.find((value) => value.id === state.player.scene);
  const [x, y] = location?.door ?? [state.player.x, state.player.y];
  ctx.strokeStyle = "#ffdea0"; ctx.lineWidth = 2; ctx.strokeRect(x * 16 + 1, y * 16 + 1, 14, 14);
  ctx.fillStyle = "#ffdea0"; ctx.fillRect(x * 16 + 5, y * 16 + 5, 6, 6);
  label(ctx, "Lake & dock", 170, 424, "#a8c3c9", 11);
}

function openMap() { stopMovement(); $("map-dialog").showModal(); }

async function newLife() {
  stopMovement();
  if (!window.confirm("Start a new life? This replaces your current player save. Download a backup first if you want to keep it. Published files are not deleted.")) return;
  await perform(null, {}, "/api/new");
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.action && !button.disabled) void perform(button.dataset.action, parametersFor(button));
  if (button.dataset.tab) selectTab(button.dataset.tab);
  if (button.dataset.close) $(button.dataset.close).close();
});
$("map-open").addEventListener("click", openMap);
$("help-open").addEventListener("click", () => { stopMovement(); $("help-dialog").showModal(); });
$("health-open").addEventListener("click", () => selectTab("body"));
$("new-life").addEventListener("click", () => { void newLife(); });
$("restart").addEventListener("click", () => { void newLife(); });
$("zoom").addEventListener("click", () => { wholeScene = !wholeScene; $("zoom").textContent = wholeScene ? "Follow player" : "Whole scene"; });
$("book-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const parameters = { topic: $("topic").value };
  if ($("book-title").value.trim()) parameters.title = $("book-title").value.trim();
  void perform("begin_book", parameters);
});
document.querySelectorAll("select").forEach((select) => select.addEventListener("change", updateButtons));
document.querySelectorAll("[data-direction]").forEach((button) => {
  const values = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
  button.addEventListener("pointerdown", (event) => {
    if (button.disabled) return;
    event.preventDefault();
    button.setPointerCapture(event.pointerId);
    heldDirections.set("pad", values[button.dataset.direction]);
    movementQueue.push(values[button.dataset.direction]);
  });
  button.addEventListener("pointerup", () => heldDirections.delete("pad"));
  button.addEventListener("pointercancel", () => heldDirections.delete("pad"));
  button.addEventListener("lostpointercapture", () => heldDirections.delete("pad"));
  button.addEventListener("click", (event) => {
    if (event.detail === 0 && !button.disabled) {
      movementQueue.push(values[button.dataset.direction]);
    }
  });
});
window.addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey ||
      event.target.closest("input, select, textarea") || $("help-dialog").open) return;
  const key = event.key.toLowerCase();
  if ($("map-dialog").open) {
    if (key === "m") { event.preventDefault(); $("map-dialog").close(); }
    return;
  }
  if (directions[key]) {
    event.preventDefault();
    if (!heldDirections.has(key)) movementQueue.push(directions[key]);
    heldDirections.set(key, directions[key]);
  }
  else if (!event.repeat && key === "e") { event.preventDefault(); void perform("interact"); }
  else if (!event.repeat && key === "m") { event.preventDefault(); openMap(); }
  else if (!event.repeat && ["b", "i", "j"].includes(key)) {
    event.preventDefault(); selectTab({ b: "body", i: "inventory", j: "journal" }[key]);
  }
});
window.addEventListener("keyup", (event) => heldDirections.delete(event.key.toLowerCase()));
window.addEventListener("blur", stopMovement);
document.addEventListener("visibilitychange", () => { if (document.hidden) stopMovement(); });
document.querySelector(".tabs").addEventListener("keydown", (event) => {
  if (event.ctrlKey || event.metaKey || event.altKey ||
      !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
  event.preventDefault(); event.stopPropagation();
  const tabs = Array.from(document.querySelectorAll("[data-tab]"));
  const current = tabs.indexOf(event.target);
  const next = tabs[(current + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
  selectTab(next.dataset.tab); next.focus();
});
$("game-canvas").addEventListener("click", (event) => {
  if (!state || busy) return;
  const rect = event.currentTarget.getBoundingClientRect();
  const x = Math.floor(((event.clientX - rect.left) * 736 / rect.width - view.x) / view.tile);
  const y = Math.floor(((event.clientY - rect.top) * 448 / rect.height - view.y) / view.tile);
  if (x < 0 || y < 0 || y >= state.scene.grid.length || x >= state.scene.grid[y].length) return;
  void perform("walk_to", { x, y });
});
$("map-canvas").addEventListener("click", (event) => {
  if (!state || busy) return;
  const rect = event.currentTarget.getBoundingClientRect();
  const x = Math.floor((event.clientX - rect.left) * 46 / rect.width);
  const y = Math.floor((event.clientY - rect.top) * 28 / rect.height);
  const location = state.world.locations.find((value) => value.door && y === value.door[1] && (x === value.door[0] || x === value.door[0] + 1));
  if (location) { $("map-dialog").close(); void perform("travel", { destination: location.id }); }
  else if (state.player.scene === "outside" && x >= 0 && x < 46 && y >= 0 && y < 28) {
    $("map-dialog").close(); void perform("walk_to", { x, y });
  } else {
    $("map-dialog").close(); announce("Choose a building, or leave your current building before choosing outdoor ground.", true);
  }
});
$("destinations").addEventListener("click", (event) => {
  if (event.target.closest("button") && !event.target.closest("button").disabled) $("map-dialog").close();
});

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
function animate(now) {
  if (state) {
    drawScene(reducedMotion.matches ? 0 : now);
    if ($("map-dialog").open) drawMap(reducedMotion.matches ? 0 : now);
    if (!busy && state.player.alive && !$("map-dialog").open && !$("help-dialog").open &&
        (movementQueue.length || (heldDirections.size && now - lastStep >= 140))) {
      lastStep = now;
      const [dx, dy] = movementQueue.length ? movementQueue.shift() : heldDirections.values().next().value;
      void perform("move", { dx, dy });
    }
  }
  window.requestAnimationFrame(animate);
}
updateButtons();
window.requestAnimationFrame(animate);
fetch("/api/state").then(async (response) => {
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Could not open your saved life.");
  token = result.token;
  render(result.state);
}).catch((error) => announce(`Could not connect to the game: ${error.message}. Keep the Python server running and reload this page.`, true));
