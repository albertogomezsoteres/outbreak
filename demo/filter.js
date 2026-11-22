// Browser port of the trained channel filter (TF-IDF word 1-2 grams + char_wb 3-5 grams, logistic
// regression, isotonic calibration). Mirrors scikit-learn exactly; tests/test_pipeline/test_demo.py
// checks the scores against Python on held-out texts.
(function (root) {
  "use strict";

  const WORD = /[\p{L}\p{N}_]{2,}/gu; // sklearn token_pattern (?u)\b\w\w+\b

  function counts(grams) {
    const c = new Map();
    for (const g of grams) c.set(g, (c.get(g) || 0) + 1);
    return c;
  }

  function wordGrams(text) {
    const toks = text.toLowerCase().match(WORD) || [];
    const grams = toks.slice();
    for (let i = 0; i + 1 < toks.length; i++) grams.push(toks[i] + " " + toks[i + 1]);
    return grams;
  }

  function charWbGrams(text) {
    const grams = [];
    const words = text.toLowerCase().replace(/\s\s+/g, " ").split(/\s+/).filter(Boolean);
    for (const raw of words) {
      const w = " " + raw + " ";
      const chars = Array.from(w); // code points, like Python str indexing
      for (let n = 3; n <= 5; n++) {
        let offset = 0;
        grams.push(chars.slice(offset, offset + n).join(""));
        while (offset + n < chars.length) {
          offset += 1;
          grams.push(chars.slice(offset, offset + n).join(""));
        }
        if (offset === 0) break;
      }
    }
    return grams;
  }

  // sublinear tf * idf, L2-normalised per block, dotted with the block's coefficients
  function blockScore(grams, table) {
    let norm = 0;
    let dot = 0;
    for (const [g, tf] of counts(grams)) {
      const entry = table[g];
      if (!entry) continue;
      const v = (1 + Math.log(tf)) * entry[0];
      norm += v * v;
      dot += v * entry[1];
    }
    return norm > 0 ? dot / Math.sqrt(norm) : 0;
  }

  function interp(x, xs, ys) {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[xs.length - 1]) return ys[ys.length - 1];
    let lo = 0, hi = xs.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (xs[mid] <= x) lo = mid; else hi = mid;
    }
    const t = xs[hi] === xs[lo] ? 0 : (x - xs[lo]) / (xs[hi] - xs[lo]);
    return ys[lo] + t * (ys[hi] - ys[lo]);
  }

  function score(model, text) {
    const z = model.intercept + blockScore(wordGrams(text), model.word) + blockScore(charWbGrams(text), model.char);
    const raw = 1 / (1 + Math.exp(-z));
    const p = model.calibration ? interp(raw, model.calibration.x, model.calibration.y) : raw;
    return { raw, p, flagged: p >= model.threshold };
  }

  const api = { score, wordGrams, charWbGrams };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.OutbreakFilter = api;
})(typeof window !== "undefined" ? window : globalThis);
