// Monthly payment calculator. Updates live as you type.

const $ = (id) => document.getElementById(id);

const money = (n) =>
  "$" + Math.round(n).toLocaleString("en-US");

function calculate() {
  const price = +$("price").value || 0;
  const downPct = +$("down").value || 0;
  const ratePct = +$("rate").value || 0;
  const years = +$("term").value || 30;
  const isFha = $("fha").checked;
  const taxRate = +$("taxrate").value || 0;
  const insuranceYr = +$("insurance").value || 0;
  const hoaMo = +$("hoa").value || 0;

  const downDollars = price * (downPct / 100);
  let loan = price - downDollars;

  // FHA: upfront MIP of 1.75% is usually financed into the loan.
  if (isFha) loan *= 1.0175;

  // Standard mortgage formula: M = L * r(1+r)^n / ((1+r)^n - 1)
  const r = ratePct / 100 / 12;          // monthly rate
  const n = years * 12;                  // number of payments
  let pi = 0;
  if (loan > 0) {
    pi = r > 0 ? (loan * r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1)
               : loan / n;
  }

  const taxMo = (price * (taxRate / 100)) / 12;
  const insMo = insuranceYr / 12;
  // FHA annual MIP is 0.55% of the loan for most 30-year loans (verify with lender).
  const mipMo = isFha ? (loan * 0.0055) / 12 : 0;

  const total = pi + taxMo + insMo + mipMo + hoaMo;

  $("down-dollars").textContent =
    downDollars > 0 ? "That's " + money(downDollars) + " in cash" : "";
  $("pi").textContent = money(pi);
  $("tax").textContent = money(taxMo);
  $("ins").textContent = money(insMo);
  $("mip").textContent = money(mipMo);
  $("hoa-out").textContent = money(hoaMo);
  $("total").textContent = money(total);

  $("mip-row").style.display = isFha ? "" : "none";
  $("hoa-row").style.display = hoaMo > 0 ? "" : "none";

  $("cash-down").textContent = money(downDollars);
  $("cash-closing").textContent =
    money(price * 0.02) + " – " + money(price * 0.05);
}

document.querySelectorAll("#calc-form input, #calc-form select")
  .forEach((el) => el.addEventListener("input", calculate));

calculate();
