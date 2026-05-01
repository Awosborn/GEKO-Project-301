const BID_ORDER = [
  "Pass", "1C", "1D", "1H", "1S", "1NT", "2C", "2D", "2H", "2S", "2NT", "3C", "3D", "3H", "3S", "3NT"
];
const SUITS = ["S", "H", "D", "C"];
const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
const SEATS = ["north", "east", "south", "west"];

const game = { hands: {}, humanSeat: "south", dealer: "north", auction: [], turn: "north", contract: null, playTurn: null, trick: [], tricksWon: { ns: 0, ew: 0 } };

function countWords(text) { return text?.trim() ? text.trim().split(/\s+/).length : 0; }
function nextSeat(seat) { return SEATS[(SEATS.indexOf(seat) + 1) % 4]; }
function teamForSeat(seat) { return (seat === "north" || seat === "south") ? "ns" : "ew"; }

function shuffledDeck() {
  const deck = [];
  for (const suit of SUITS) for (const rank of RANKS) deck.push(`${rank}${suit}`);
  for (let i = deck.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [deck[i], deck[j]] = [deck[j], deck[i]]; }
  return deck;
}

function dealHands() {
  const deck = shuffledDeck();
  const hands = { north: [], east: [], south: [], west: [] };
  for (let i = 0; i < 52; i++) hands[SEATS[i % 4]].push(deck[i]);
  return hands;
}

function handToText(cards) {
  const bySuit = { S: [], H: [], D: [], C: [] };
  cards.forEach((c) => bySuit[c[1]].push(c[0]));
  return SUITS.map((s) => `${s} ${RANKS.filter((r) => bySuit[s].includes(r)).join("")}`).join(" ");
}

function calculateHcp(handText) { const p = { A: 4, K: 3, Q: 2, J: 1 }; return [...handText.toUpperCase()].reduce((t, ch) => t + (p[ch] || 0), 0); }
function predictiveTop3(handText, auctionText) {
  const hcp = calculateHcp(handText); const hasNt = /\b1NT\b/i.test(auctionText);
  if (hcp >= 16) return ["1NT", "1S", "1H"]; if (hcp >= 12) return ["1H", "1S", "1D"]; if (hcp >= 8) return hasNt ? ["2D", "2H", "Pass"] : ["1D", "Pass", "1C"]; return ["Pass", "1C", "1D"];
}

function ruleBasedCoach({ hand, userBid, top3, seat, dealer, vulnerability, auction }) {
  const normalized = userBid.trim().toUpperCase(); const userInTop3 = top3.map((b) => b.toUpperCase()).includes(normalized); const best = top3[0]; const hcp = calculateHcp(hand);
  if (userInTop3) return { verdict: "inside_top_3", recommendedBid: normalized, explanation: "" };
  return { verdict: "outside_top_3", recommendedBid: best, explanation: `Rule-based review: Bid ${normalized} is outside top-3 (${top3.join(", ")}). Hand=${hand}; HCP=${hcp}; Seat=${seat}; Dealer=${dealer}; Vuln=${vulnerability}; Auction=${auction || "(empty)"}. Recommend ${best}.` };
}

async function llmCoachViaApi(payload) {
  const response = await fetch("/api/coach", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) throw new Error(`Coach API failed: ${response.status}`);
  return response.json();
}

function auctionDone() {
  if (game.auction.length < 4) return false;
  const last3 = game.auction.slice(-3).every((a) => a.call === "Pass");
  const anyBid = game.auction.some((a) => a.call !== "Pass");
  return last3 && anyBid;
}

function renderHumanHand() {
  const cards = game.hands[game.humanSeat];
  document.getElementById("hand-view").innerHTML = cards.map((card) => `<button class="card ${/[HD]/.test(card[1]) ? "red" : "black"}" data-card="${card}">${card[0]}${card[1] === "S" ? "♠" : card[1] === "H" ? "♥" : card[1] === "D" ? "♦" : "♣"}</button>`).join("");
}

function renderAuction() {
  document.getElementById("auction-log").textContent = game.auction.map((a) => `${a.seat}:${a.call}`).join(" | ") || "(empty)";
}

async function processAiBiddingUntilHuman() {
  while (!auctionDone() && game.turn !== game.humanSeat) {
    const seat = game.turn;
    const hand = handToText(game.hands[seat]);
    const call = predictiveTop3(hand, game.auction.map((a) => a.call).join(" "))[0];
    game.auction.push({ seat, call });
    game.turn = nextSeat(game.turn);
  }
  renderAuction();
  document.getElementById("bid-controls").hidden = auctionDone();
  if (auctionDone()) startCardplay();
}

async function submitHumanBid() {
  const bid = document.getElementById("user-bid").value.trim(); if (!bid) return;
  const hand = handToText(game.hands[game.humanSeat]);
  const auctionText = game.auction.map((a) => a.call).join(" ");
  const top3 = predictiveTop3(hand, auctionText);
  let coached;
  try { coached = await llmCoachViaApi({ hand, userBid: bid, top3, seat: game.humanSeat, dealer: game.dealer, vulnerability: document.getElementById("vuln").value, auction: auctionText }); }
  catch { coached = ruleBasedCoach({ hand, userBid: bid, top3, seat: game.humanSeat, dealer: game.dealer, vulnerability: document.getElementById("vuln").value, auction: auctionText }); }

  document.getElementById("top3").textContent = top3.join(", "); document.getElementById("verdict").textContent = coached.verdict; document.getElementById("recommended").textContent = coached.recommendedBid || "";
  document.getElementById("llm-word-count").textContent = String(countWords(coached.explanation || "")); document.getElementById("llm-output-text").textContent = coached.explanation || "Not available";
  document.getElementById("results").hidden = false;

  if (coached.verdict === "outside_top_3") return;

  game.auction.push({ seat: game.humanSeat, call: bid.toUpperCase() });
  game.turn = nextSeat(game.humanSeat);
  document.getElementById("user-bid").value = "";
  await processAiBiddingUntilHuman();
}

function startCardplay() {
  game.contract = game.auction.filter((a) => a.call !== "Pass").slice(-1)[0]?.call || "Pass";
  game.playTurn = nextSeat(game.dealer);
  game.trick = [];
  document.getElementById("cardplay-panel").hidden = false;
  runCardplayLoop();
}

function legalCards(seat) {
  const cards = game.hands[seat];
  if (!game.trick.length) return cards;
  const leadSuit = game.trick[0].card[1];
  const follow = cards.filter((c) => c[1] === leadSuit);
  return follow.length ? follow : cards;
}

function rankValue(r) { return RANKS.indexOf(r); }
function winnerOfTrick() {
  const lead = game.trick[0].card[1];
  const candidates = game.trick.filter((p) => p.card[1] === lead);
  candidates.sort((a, b) => rankValue(a.card[0]) - rankValue(b.card[0]));
  return candidates[0].seat;
}

function runCardplayLoop() {
  while (game.playTurn !== game.humanSeat && game.hands[game.playTurn].length) {
    const aiCard = legalCards(game.playTurn)[0];
    game.hands[game.playTurn] = game.hands[game.playTurn].filter((c) => c !== aiCard);
    game.trick.push({ seat: game.playTurn, card: aiCard });
    game.playTurn = nextSeat(game.playTurn);
    if (game.trick.length === 4) completeTrick();
  }
  renderHumanHand();
  document.getElementById("trick-log").textContent = game.trick.map((p) => `${p.seat}:${p.card}`).join(" | ") || "(none)";
}

function completeTrick() {
  const winner = winnerOfTrick();
  game.tricksWon[teamForSeat(winner)] += 1;
  game.playTurn = winner;
  game.trick = [];
  document.getElementById("score").textContent = `NS ${game.tricksWon.ns} - EW ${game.tricksWon.ew}`;
}

document.getElementById("deal-btn").addEventListener("click", async () => {
  game.humanSeat = document.getElementById("seat").value; game.dealer = document.getElementById("dealer").value;
  game.hands = dealHands(); game.auction = []; game.turn = game.dealer; game.tricksWon = { ns: 0, ew: 0 }; game.trick = [];
  document.getElementById("seat-display").textContent = game.humanSeat; document.getElementById("play-panel").hidden = false; document.getElementById("results").hidden = true; document.getElementById("cardplay-panel").hidden = true;
  renderHumanHand(); renderAuction(); await processAiBiddingUntilHuman();
});

document.getElementById("play-btn").addEventListener("click", submitHumanBid);
document.getElementById("hand-view").addEventListener("click", (event) => {
  const card = event.target.dataset.card; if (!card || game.playTurn !== game.humanSeat) return;
  if (!legalCards(game.humanSeat).includes(card)) return;
  game.hands[game.humanSeat] = game.hands[game.humanSeat].filter((c) => c !== card);
  game.trick.push({ seat: game.humanSeat, card }); game.playTurn = nextSeat(game.humanSeat);
  if (game.trick.length === 4) completeTrick();
  runCardplayLoop();
});
