const BID_ORDER = [
  "Pass", "1C", "1D", "1H", "1S", "1NT",
  "2C", "2D", "2H", "2S", "2NT",
  "3C", "3D", "3H", "3S", "3NT"
];

const SUITS = ["S", "H", "D", "C"];
const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"];

let currentHand = "";

function shuffledDeck() {
  const deck = [];
  for (const suit of SUITS) for (const rank of RANKS) deck.push(`${rank}${suit}`);
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }
  return deck;
}

function dealHand() {
  const cards = shuffledDeck().slice(0, 13);
  const bySuit = { S: [], H: [], D: [], C: [] };
  cards.forEach((card) => bySuit[card[1]].push(card[0]));
  return SUITS.map((s) => `${s} ${RANKS.filter((r) => bySuit[s].includes(r)).join("")}`).join(" ");
}

function cardsFromHandText(handText) {
  const match = handText.match(/S\s*([AKQJT98765432]*)\s*H\s*([AKQJT98765432]*)\s*D\s*([AKQJT98765432]*)\s*C\s*([AKQJT98765432]*)/i);
  if (!match) return [];
  return [
    ...match[1].split("").filter(Boolean).map((r) => `${r}♠`),
    ...match[2].split("").filter(Boolean).map((r) => `${r}♥`),
    ...match[3].split("").filter(Boolean).map((r) => `${r}♦`),
    ...match[4].split("").filter(Boolean).map((r) => `${r}♣`)
  ];
}

function calculateHcp(handText) {
  const cardPoints = { A: 4, K: 3, Q: 2, J: 1 };
  let total = 0;
  for (const ch of handText.toUpperCase()) if (cardPoints[ch]) total += cardPoints[ch];
  return total;
}

function predictiveTop3(hand, auction) {
  const hcp = calculateHcp(hand);
  const auctionHas1Nt = /\b1NT\b/i.test(auction);
  if (hcp >= 16) return ["1NT", "1S", "1H"];
  if (hcp >= 12) return ["1H", "1S", "1D"];
  if (hcp >= 8) return auctionHas1Nt ? ["2D", "2H", "Pass"] : ["1D", "Pass", "1C"];
  return ["Pass", "1C", "1D"];
}

function llmCoach({ hand, userBid, top3, seat, dealer, vulnerability, auction }) {
  const normalized = userBid.trim().toUpperCase();
  const userInTop3 = top3.map((b) => b.toUpperCase()).includes(normalized);
  const best = top3[0];
  const hcp = calculateHcp(hand);

  if (userInTop3) {
    return {
      verdict: "inside_top_3",
      recommendedBid: normalized,
      explanation: ""
    };
  }

  return {
    verdict: "outside_top_3",
    recommendedBid: best,
    explanation: `LLM review (StreamLine context): Bid ${normalized} is outside GEKO playable model top-3 (${top3.join(", ")}). Hand=${hand}; HCP=${hcp}; Seat=${seat}; Dealer=${dealer}; Vuln=${vulnerability}; Auction=${auction || "(empty)"}. Recommend ${best} because it aligns with model strength profile.`
  };
}

function renderHandCards(handText) {
  const handView = document.getElementById("hand-view");
  const cards = cardsFromHandText(handText);
  handView.innerHTML = cards.map((card) => `<span class="card ${/[♥♦]/.test(card) ? "red" : "black"}">${card}</span>`).join("");
}

document.getElementById("deal-btn").addEventListener("click", () => {
  currentHand = dealHand();
  const seat = document.getElementById("seat").value;
  document.getElementById("seat-display").textContent = seat;
  renderHandCards(currentHand);
  document.getElementById("play-panel").hidden = false;
  document.getElementById("results").hidden = true;
});

document.getElementById("play-btn").addEventListener("click", () => {
  if (!currentHand) return;
  const seat = document.getElementById("seat").value;
  const dealer = document.getElementById("dealer").value;
  const vulnerability = document.getElementById("vuln").value;
  const auction = document.getElementById("auction").value;
  const userBid = document.getElementById("user-bid").value;

  const top3 = predictiveTop3(currentHand, auction);
  const coached = llmCoach({ hand: currentHand, userBid, top3, seat, dealer, vulnerability, auction });

  document.getElementById("top3").textContent = top3.join(", ");
  document.getElementById("verdict").textContent = coached.verdict;
  document.getElementById("recommended").textContent = coached.recommendedBid;

  const explanationBox = document.getElementById("explanation");
  if (coached.verdict === "outside_top_3") {
    explanationBox.textContent = coached.explanation;
    explanationBox.hidden = false;
  } else {
    explanationBox.hidden = true;
    explanationBox.textContent = "";
  }

  document.getElementById("results").hidden = false;
});
