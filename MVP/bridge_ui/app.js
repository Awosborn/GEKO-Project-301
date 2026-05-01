const BID_ORDER = window.bridgeRules.CONTRACT_ORDER;
const SUITS = ["S", "H", "D", "C"];
const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
const SEATS = ["north", "east", "south", "west"];

const game = { hands: {}, humanSeat: "south", dealer: "north", auction: [], turn: "north", contract: null, playTurn: null, trick: [], tricksWon: { ns: 0, ew: 0 } };
let uiInitialized = false;

function countWords(text) { return text?.trim() ? text.trim().split(/\s+/).length : 0; }
function nextSeat(seat) { return window.bridgeRules.nextSeat(seat); }
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

async function postCoach(url, payload) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  return response;
}

async function llmCoachViaApi(payload) {
  let response = await postCoach("/api/coach", payload);

  if (!response.ok && (response.status === 404 || response.status === 501)) {
    const runningOnPort8000 = window.location.port === "8000";
    if (!runningOnPort8000) {
      response = await postCoach("http://localhost:8000/api/coach", payload);
    }
  }

  if (!response.ok) throw new Error(`Coach API failed: ${response.status}`);
  return response.json();
}

function auctionDone() { return window.bridgeRules.auctionDone(game.auction); }

function renderHumanHand() {
  const cards = game.hands[game.humanSeat];
  document.getElementById("hand-view").innerHTML = cards.map((card) => `<button class="card ${/[HD]/.test(card[1]) ? "red" : "black"}" data-card="${card}">${card[0]}${card[1] === "S" ? "♠" : card[1] === "H" ? "♥" : card[1] === "D" ? "♦" : "♣"}</button>`).join("");
}

function renderAuction() {
  document.getElementById("auction-log").textContent = game.auction.map((a) => `${a.seat}:${a.call}`).join(" | ") || "(empty)";
  document.getElementById("turn-display").textContent = auctionDone() ? "auction complete" : `${game.turn} to act`;
}

async function processAiBiddingUntilHuman() {
  try {
    while (!auctionDone() && game.turn !== game.humanSeat) {
      const seat = game.turn;
      const hand = handToText(game.hands[seat]);
      const prefs = predictiveTop3(hand, game.auction.map((a) => a.call).join(" "));
      const choices = [...prefs, ...BID_ORDER, "Pass"];
      const call = choices.find((c) => window.bridgeRules.isLegalCall(game.auction, seat, c).ok) || "Pass";
      game.auction.push({ seat, call: call.toUpperCase() });
      game.turn = nextSeat(game.turn);
    }
    renderAuction();
    document.getElementById("bid-controls").hidden = auctionDone();
    if (auctionDone()) startCardplay();
  } catch (error) {
    renderAuction();
    document.getElementById("results").hidden = false;
    document.getElementById("verdict").textContent = "bidding_error";
    document.getElementById("recommended").textContent = "";
    document.getElementById("llm-output-text").textContent = `Bidding loop failed: ${String(error)}`;
    document.getElementById("llm-word-count").textContent = String(countWords(String(error)));
  }
}

async function submitHumanBid() {
  try {
  const bid = document.getElementById("user-bid").value.trim(); if (!bid) return;
  const legality = window.bridgeRules.isLegalCall(game.auction, game.humanSeat, bid);
  if (!legality.ok) {
    document.getElementById("results").hidden = false;
    document.getElementById("verdict").textContent = "illegal_call";
    document.getElementById("recommended").textContent = "";
    document.getElementById("llm-output-text").textContent = legality.reason;
    document.getElementById("llm-word-count").textContent = String(countWords(legality.reason));
    return;
  }
  const hand = handToText(game.hands[game.humanSeat]);
  const auctionText = game.auction.map((a) => a.call).join(" ");
  const top3 = predictiveTop3(hand, auctionText);
  const coached = await llmCoachViaApi({ hand, userBid: bid, top3, seat: game.humanSeat, dealer: game.dealer, vulnerability: document.getElementById("vuln").value, auction: auctionText });

  document.getElementById("top3").textContent = top3.join(", "); document.getElementById("verdict").textContent = coached.verdict; document.getElementById("recommended").textContent = coached.recommendedBid || "";
  const llmText = coached.rawModelText || coached.explanation || "Not available";
  document.getElementById("llm-word-count").textContent = String(countWords(llmText)); document.getElementById("llm-output-text").textContent = llmText;
  document.getElementById("results").hidden = false;

  game.auction.push({ seat: game.humanSeat, call: legality.call });
  game.turn = nextSeat(game.humanSeat);
  document.getElementById("user-bid").value = "";
  await processAiBiddingUntilHuman();
  } catch (error) {
    document.getElementById("results").hidden = false;
    document.getElementById("verdict").textContent = "api_error";
    document.getElementById("recommended").textContent = "";
    document.getElementById("llm-output-text").textContent = String(error);
    document.getElementById("llm-word-count").textContent = String(countWords(String(error)));
  }
}

function startCardplay() {
  game.contract = window.bridgeRules.finalContract(game.auction) || "Pass";
  game.playTurn = nextSeat(game.dealer);
  game.trick = [];
  document.getElementById("contract-display").textContent = game.contract;
  document.getElementById("cardplay-panel").hidden = false;
  runCardplayLoop();
}

function legalCards(seat) {
  return window.bridgeRules.legalCards(game.hands[seat], game.trick);
}

function winnerOfTrick() {
  return window.bridgeRules.winnerOfTrick(game.trick, game.contract);
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

async function startNewDeal() {
  game.humanSeat = document.getElementById("seat").value;
  game.dealer = document.getElementById("dealer").value;
  game.hands = dealHands();
  game.auction = [];
  game.turn = game.dealer;
  game.tricksWon = { ns: 0, ew: 0 };
  game.trick = [];
  game.contract = null;
  game.playTurn = null;

  document.getElementById("seat-display").textContent = game.humanSeat;
  document.getElementById("play-panel").hidden = false;
  document.getElementById("results").hidden = true;
  document.getElementById("cardplay-panel").hidden = true;
  document.getElementById("score").textContent = "NS 0 - EW 0";
  document.getElementById("trick-log").textContent = "(none)";
  document.getElementById("contract-display").textContent = "(none)";

  renderHumanHand();
  renderAuction();
  await processAiBiddingUntilHuman();
}

function initUi() {
  if (uiInitialized) return;
  const dealButton = document.getElementById("deal-btn");
  const playButton = document.getElementById("play-btn");
  const handView = document.getElementById("hand-view");
  if (!dealButton || !playButton || !handView) return;
  uiInitialized = true;

  dealButton.addEventListener("click", async () => {
    try {
      await startNewDeal();
    } catch (error) {
      document.getElementById("results").hidden = false;
      document.getElementById("verdict").textContent = "deal_error";
      document.getElementById("recommended").textContent = "";
      document.getElementById("llm-output-text").textContent = String(error);
      document.getElementById("llm-word-count").textContent = String(countWords(String(error)));
    }
  });

  playButton.addEventListener("click", submitHumanBid);
  handView.addEventListener("click", (event) => {
    const card = event.target.dataset.card; if (!card || game.playTurn !== game.humanSeat) return;
    if (!legalCards(game.humanSeat).includes(card)) return;
    game.hands[game.humanSeat] = game.hands[game.humanSeat].filter((c) => c !== card);
    game.trick.push({ seat: game.humanSeat, card }); game.playTurn = nextSeat(game.humanSeat);
    if (game.trick.length === 4) completeTrick();
    runCardplayLoop();
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initUi);
} else {
  initUi();
}
window.addEventListener("load", initUi);
