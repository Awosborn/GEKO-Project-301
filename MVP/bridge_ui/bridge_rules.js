const SEATS = ["north", "east", "south", "west"];
const CONTRACT_ORDER = [
  "1C", "1D", "1H", "1S", "1NT",
  "2C", "2D", "2H", "2S", "2NT",
  "3C", "3D", "3H", "3S", "3NT",
  "4C", "4D", "4H", "4S", "4NT",
  "5C", "5D", "5H", "5S", "5NT",
  "6C", "6D", "6H", "6S", "6NT",
  "7C", "7D", "7H", "7S", "7NT"
];
const SUIT_RANK = { C: 0, D: 1, H: 2, S: 3, NT: 4 };
const RANK_ORDER = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"];

function nextSeat(seat) { return SEATS[(SEATS.indexOf(seat) + 1) % 4]; }

function parseCall(rawCall) {
  const call = String(rawCall || "").trim().toUpperCase();
  if (call === "PASS" || call === "X" || call === "XX") return call;
  const m = call.match(/^([1-7])(C|D|H|S|NT)$/);
  if (!m) return null;
  return `${m[1]}${m[2]}`;
}

function contractRank(contract) {
  const m = String(contract).match(/^([1-7])(C|D|H|S|NT)$/);
  if (!m) return -1;
  return (Number(m[1]) - 1) * 5 + SUIT_RANK[m[2]];
}

function finalContract(auction) {
  for (let i = auction.length - 1; i >= 0; i--) {
    const call = parseCall(auction[i].call);
    if (call && !["PASS", "X", "XX"].includes(call)) return call;
  }
  return null;
}

function auctionState(auction) {
  let contract = null;
  let doubled = false;
  let redoubled = false;
  let passedOut = false;

  for (const entry of auction) {
    const c = parseCall(entry.call);
    if (!c) continue;
    if (c === "PASS") continue;
    if (c === "X") {
      doubled = true; redoubled = false;
    } else if (c === "XX") {
      redoubled = true;
    } else {
      contract = c;
      doubled = false;
      redoubled = false;
    }
  }

  if (auction.length >= 4) {
    const first4Pass = auction.slice(0, 4).every((a) => parseCall(a.call) === "PASS");
    passedOut = first4Pass;
  }

  return { contract, doubled, redoubled, passedOut };
}

function isLegalCall(auction, seat, rawCall) {
  const call = parseCall(rawCall);
  if (!call) return { ok: false, reason: "Unknown bid/call format." };
  if (auctionDone(auction)) return { ok: false, reason: "Auction is already complete." };

  const state = auctionState(auction);
  const lastContract = state.contract;

  if (call === "PASS") return { ok: true, call };

  if (call === "X") {
    if (!lastContract) return { ok: false, reason: "Double requires an opposing contract." };
    if (state.doubled || state.redoubled) return { ok: false, reason: "Contract is already doubled/redoubled." };
    const declarerTeam = teamForSeat(lastBidSeat(auction));
    if (teamForSeat(seat) === declarerTeam) return { ok: false, reason: "You can only double opponents." };
    return { ok: true, call };
  }

  if (call === "XX") {
    if (!state.doubled || state.redoubled) return { ok: false, reason: "Redouble requires a live double." };
    const doublerTeam = teamForSeat(lastCallSeat(auction, "X"));
    if (teamForSeat(seat) === doublerTeam) return { ok: false, reason: "You can only redouble opponents' double." };
    return { ok: true, call };
  }

  if (!lastContract) return { ok: true, call };
  if (contractRank(call) <= contractRank(lastContract)) return { ok: false, reason: `Bid must outrank ${lastContract}.` };
  return { ok: true, call };
}

function lastCallSeat(auction, target) {
  for (let i = auction.length - 1; i >= 0; i--) {
    if (parseCall(auction[i].call) === target) return auction[i].seat;
  }
  return null;
}

function lastBidSeat(auction) {
  for (let i = auction.length - 1; i >= 0; i--) {
    const c = parseCall(auction[i].call);
    if (c && !["PASS", "X", "XX"].includes(c)) return auction[i].seat;
  }
  return null;
}

function teamForSeat(seat) { return (seat === "north" || seat === "south") ? "ns" : "ew"; }

function auctionDone(auction) {
  if (auction.length < 4) return false;
  if (auction.slice(0, 4).every((a) => parseCall(a.call) === "PASS")) return true;
  const last3Passes = auction.slice(-3).every((a) => parseCall(a.call) === "PASS");
  const hasContract = auction.some((a) => {
    const c = parseCall(a.call);
    return c && !["PASS", "X", "XX"].includes(c);
  });
  return hasContract && last3Passes;
}

function legalCards(hand, trick) {
  if (!trick.length) return [...hand];
  const leadSuit = trick[0].card[1];
  const follow = hand.filter((c) => c[1] === leadSuit);
  return follow.length ? follow : [...hand];
}

function winnerOfTrick(trick, contract) {
  const trump = /NT$/.test(contract || "") ? null : (contract || "").slice(-1);
  let winning = trick[0];
  for (const play of trick.slice(1)) {
    if (beats(play.card, winning.card, trick[0].card[1], trump)) winning = play;
  }
  return winning.seat;
}

function beats(cardA, cardB, leadSuit, trumpSuit) {
  const suitA = cardA[1], suitB = cardB[1];
  const trumpA = trumpSuit && suitA === trumpSuit;
  const trumpB = trumpSuit && suitB === trumpSuit;
  if (trumpA && !trumpB) return true;
  if (!trumpA && trumpB) return false;
  if (suitA !== suitB) return suitA === leadSuit;
  return RANK_ORDER.indexOf(cardA[0]) > RANK_ORDER.indexOf(cardB[0]);
}

window.bridgeRules = { parseCall, isLegalCall, auctionDone, legalCards, winnerOfTrick, nextSeat, finalContract, CONTRACT_ORDER };
