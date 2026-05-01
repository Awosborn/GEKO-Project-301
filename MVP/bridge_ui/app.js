const BID_ORDER = [
  "Pass", "1C", "1D", "1H", "1S", "1NT",
  "2C", "2D", "2H", "2S", "2NT",
  "3C", "3D", "3H", "3S", "3NT"
];

function calculateHcp(handText) {
  const cardPoints = { A: 4, K: 3, Q: 2, J: 1 };
  let total = 0;
  for (const ch of handText.toUpperCase()) {
    if (cardPoints[ch]) total += cardPoints[ch];
  }
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

function llmCoach({ hand, userBid, top3, seat, dealer, vulnerability }) {
  const normalized = userBid.trim().toUpperCase();
  const userInTop3 = top3.map((b) => b.toUpperCase()).includes(normalized);
  const best = top3[0];
  const hcp = calculateHcp(hand);

  if (userInTop3) {
    return {
      verdict: "reasonable",
      recommendedBid: normalized,
      explanation: `Your bid ${normalized} is inside the model's top three choices. With ${hcp} HCP from ${seat} (dealer: ${dealer}, vulnerability: ${vulnerability}), this is a practical and acceptable action.`
    };
  }

  return {
    verdict: "improve",
    recommendedBid: best,
    explanation: `Your bid ${normalized} is outside the predictive model's top three (${top3.join(", ")}). The LLM coach would correct this to ${best} because it better matches the hand strength (${hcp} HCP), seat context (${seat}), and risk profile at ${vulnerability} vulnerability.`
  };
}

document.getElementById("coach-form").addEventListener("submit", (e) => {
  e.preventDefault();

  const seat = document.getElementById("seat").value;
  const dealer = document.getElementById("dealer").value;
  const vulnerability = document.getElementById("vuln").value;
  const hand = document.getElementById("hand").value;
  const auction = document.getElementById("auction").value;
  const userBid = document.getElementById("user-bid").value;

  const top3 = predictiveTop3(hand, auction);
  const coached = llmCoach({ hand, userBid, top3, seat, dealer, vulnerability });

  document.getElementById("top3").textContent = top3.join(", ");
  document.getElementById("verdict").textContent = coached.verdict;
  document.getElementById("recommended").textContent = coached.recommendedBid;
  document.getElementById("explanation").textContent = coached.explanation;
  document.getElementById("results").hidden = false;
});
