const BID_ORDER = window.bridgeRules.CONTRACT_ORDER;
const SUITS = ["S", "H", "D", "C"];
const DISPLAY_SUITS = ["S", "H", "C", "D"];
const SUIT_ENTITIES = { S: "&spades;", H: "&hearts;", C: "&clubs;", D: "&diams;" };
const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];
const TABLE_SEATS = ["north", "east", "south", "west"];

const game = { hands: {}, humanSeat: "south", dealer: "north", auction: [], turn: "north", contract: null, playTurn: null, trick: [], tricksWon: { ns: 0, ew: 0 }, playHistory: [], declarer: null, dummy: null };
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
  for (let i = 0; i < 52; i++) hands[TABLE_SEATS[i % 4]].push(deck[i]);
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

// Determine the declarer from the completed auction (first player on declaring side to bid that strain)
function findDeclarer(auction, dealer) {
  let finalStrain = null;
  let finalBidSeat = null;
  for (let i = auction.length - 1; i >= 0; i--) {
    const call = window.bridgeRules.parseCall(auction[i].call);
    if (call && !["PASS", "X", "XX"].includes(call)) {
      finalStrain = call.slice(1); // "H", "NT", "S", etc.
      finalBidSeat = auction[i].seat;
      break;
    }
  }
  if (!finalStrain || !finalBidSeat) return dealer;
  const nsTeam = ["north", "south"];
  const declarerTeam = nsTeam.includes(finalBidSeat) ? nsTeam : ["east", "west"];
  for (const entry of auction) {
    const call = window.bridgeRules.parseCall(entry.call);
    if (call && call.slice(1) === finalStrain && declarerTeam.includes(entry.seat)) return entry.seat;
  }
  return finalBidSeat;
}

async function postJson(url, payload) {
  return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
}

async function llmCoachViaApi(payload) {
  let response = await postJson("/api/coach", payload);
  if (!response.ok && (response.status === 404 || response.status === 501)) {
    if (window.location.port !== "8000") response = await postJson("http://localhost:8000/api/coach", payload);
  }
  if (!response.ok) throw new Error(`Coach API failed: ${response.status}`);
  return response.json();
}

// Call GEKO bidding model via server API; returns { recommendedBid, top3 }
async function gekoAiBid(seat, hand, dealer, vulnerability, auction) {
  const response = await postJson("/api/bid", { seat, hand, dealer, vulnerability, auction });
  if (!response.ok) throw new Error(`Bid API ${response.status}`);
  return response.json();
}

// Call GEKO card-play model via server API; returns { recommendedCard }
async function gekoAiCard(seat, hand, trick, playHistory, auction, contract, declarer, dummy, vulnerability, dummyHand) {
  const response = await postJson("/api/card", { seat, hand, trick, playHistory, auction, contract, declarer, dummy, vulnerability, dummyHand });
  if (!response.ok) throw new Error(`Card API ${response.status}`);
  return response.json();
}

function auctionDone() { return window.bridgeRules.auctionDone(game.auction); }

function sortCardsForDisplay(cards) {
  return [...cards].sort((a, b) => {
    const suitDiff = DISPLAY_SUITS.indexOf(a[1]) - DISPLAY_SUITS.indexOf(b[1]);
    if (suitDiff) return suitDiff;
    const rankDiff = RANKS.indexOf(a[0]) - RANKS.indexOf(b[0]);
    return rankDiff || a.localeCompare(b);
  });
}

function renderHumanHand() {
  const displayCards = sortCardsForDisplay(game.hands[game.humanSeat] || []);
  document.getElementById("hand-view").innerHTML = displayCards.map((card) => `<button class="card ${/[HD]/.test(card[1]) ? "red" : "black"}" data-card="${card}">${card[0]}${SUIT_ENTITIES[card[1]] || card[1]}</button>`).join("");
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
      const auctionCalls = game.auction.map((a) => a.call);
      const vuln = document.getElementById("vuln").value;
      let call = null;

      // Try GEKO bidding model first
      try {
        const result = await gekoAiBid(seat, hand, game.dealer, vuln, auctionCalls);
        const recommended = result.recommendedBid;
        if (recommended) {
          const legality = window.bridgeRules.isLegalCall(game.auction, seat, recommended);
          if (legality.ok) call = legality.call;
        }
      } catch (_) { /* fallback below */ }

      // Heuristic fallback
      if (!call) {
        const prefs = predictiveTop3(hand, auctionCalls.join(" "));
        const choices = [...prefs, ...BID_ORDER, "Pass"];
        const chosen = choices.find((c) => window.bridgeRules.isLegalCall(game.auction, seat, c).ok) || "Pass";
        call = window.bridgeRules.isLegalCall(game.auction, seat, chosen).call || "PASS";
      }

      game.auction.push({ seat, call });
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
    const auctionHistory = game.auction.map((a) => ({ seat: a.seat, call: a.call }));
    const auctionCalls = game.auction.map((a) => a.call);
    const vuln = document.getElementById("vuln").value;

    // Compute all legally available calls for the current position
    const allCalls = [...BID_ORDER, "Pass", "X", "XX"];
    const legalBids = allCalls.filter((c) => window.bridgeRules.isLegalCall(game.auction, game.humanSeat, c).ok);

    // Get top3 from GEKO bidding model, filtered to legal calls; heuristic fallback
    let top3 = [];
    let gekoRecommendedBid = "";
    try {
      const result = await gekoAiBid(game.humanSeat, hand, game.dealer, vuln, auctionCalls);
      if (result.recommendedBid && legalBids.some((lb) => lb.toUpperCase() === result.recommendedBid.toUpperCase())) {
        gekoRecommendedBid = result.recommendedBid;
      }
      top3 = (result.top3 || []).filter((c) => legalBids.some((lb) => lb.toUpperCase() === c.toUpperCase()));
    } catch (_) { /* fallback below */ }
    if (!top3.length) {
      top3 = predictiveTop3(hand, auctionText).filter((c) => legalBids.some((lb) => lb.toUpperCase() === c.toUpperCase()));
    }
    if (!top3.length) top3 = legalBids.slice(0, 3);
    if (!gekoRecommendedBid) gekoRecommendedBid = top3[0] || "";

    const coached = await llmCoachViaApi({
      hand,
      userBid: bid,
      top3,
      recommendedBid: gekoRecommendedBid,
      seat: game.humanSeat,
      dealer: game.dealer,
      vulnerability: vuln,
      auction: auctionText,
      auctionHistory,
      legalBids,
    });

    document.getElementById("top3").textContent = top3.join(", ");
    document.getElementById("verdict").textContent = coached.verdict;
    document.getElementById("recommended").textContent = gekoRecommendedBid || coached.recommendedBid || "";
    const llmText = coached.reviewText || coached.explanation || "Not available";
    document.getElementById("llm-word-count").textContent = String(countWords(llmText));
    document.getElementById("llm-output-text").textContent = llmText;
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
  document.getElementById("contract-display").textContent = game.contract;
  document.getElementById("cardplay-panel").hidden = false;

  if (game.contract === "Pass") return; // passed-out auction: no card play

  game.declarer = findDeclarer(game.auction, game.dealer);
  game.dummy = nextSeat(nextSeat(game.declarer)); // partner of declarer
  game.playTurn = nextSeat(game.declarer);        // opening lead from left of declarer
  game.trick = [];
  game.playHistory = [];
  runCardplayLoop().catch((err) => {
    document.getElementById("trick-log").textContent = `Card play error: ${String(err)}`;
  });
}

function legalCards(seat) {
  return window.bridgeRules.legalCards(game.hands[seat], game.trick);
}

function winnerOfTrick() {
  return window.bridgeRules.winnerOfTrick(game.trick, game.contract);
}

async function runCardplayLoop() {
  while (game.playTurn !== game.humanSeat && game.hands[game.playTurn] && game.hands[game.playTurn].length) {
    const seat = game.playTurn;
    const legalCardsList = legalCards(seat);
    let aiCard = null;

    // Try GEKO card-play model
    if (game.declarer && game.contract && game.contract !== "Pass") {
      try {
        const dummyCards = game.hands[game.dummy] || [];
        const result = await gekoAiCard(
          seat,
          game.hands[seat],
          game.trick,
          game.playHistory,
          game.auction.map((a) => a.call),
          game.contract,
          game.declarer,
          game.dummy,
          document.getElementById("vuln").value,
          dummyCards,
        );
        const recommended = result.recommendedCard;
        if (recommended && game.hands[seat].includes(recommended) && legalCardsList.includes(recommended)) {
          aiCard = recommended;
        }
      } catch (_) { /* fallback below */ }
    }

    if (!aiCard) aiCard = legalCardsList[0];

    game.hands[seat] = game.hands[seat].filter((c) => c !== aiCard);
    game.trick.push({ seat, card: aiCard });
    game.playTurn = nextSeat(game.playTurn);
    if (game.trick.length === 4) completeTrick();
  }
  renderHumanHand();
  document.getElementById("trick-log").textContent = game.trick.map((p) => `${p.seat}:${p.card}`).join(" | ") || "(none)";
}

function completeTrick() {
  const winner = winnerOfTrick();
  game.tricksWon[teamForSeat(winner)] += 1;
  game.trick.forEach((p) => game.playHistory.push(p));
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
  game.playHistory = [];
  game.declarer = null;
  game.dummy = null;

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
  handView.addEventListener("click", async (event) => {
    const card = event.target.dataset.card; if (!card || game.playTurn !== game.humanSeat) return;
    if (!legalCards(game.humanSeat).includes(card)) return;
    game.hands[game.humanSeat] = game.hands[game.humanSeat].filter((c) => c !== card);
    game.trick.push({ seat: game.humanSeat, card });
    game.playTurn = nextSeat(game.humanSeat);
    if (game.trick.length === 4) completeTrick();
    await runCardplayLoop();
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initUi);
} else {
  initUi();
}
window.addEventListener("load", initUi);
