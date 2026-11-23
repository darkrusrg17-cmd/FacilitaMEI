// Máscara de moeda (R$ 1.234,56) e cálculo automático da margem
const preco = document.getElementById("preco");
const custo = document.getElementById("custo");
const caixa = document.querySelector(".margin-box");
const margemValor = document.getElementById("margem-valor");
const margemPct = document.getElementById("margem-pct");

const toCents = (s) => parseInt(s.replace(/\D/g, "") || "0", 10);
const fmt = (n) => n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function mascaraMoeda(el) {
  const c = toCents(el.value);
  el.value = c ? "R$ " + fmt(c / 100) : "";
}

function atualizarMargem() {
  const p = toCents(preco.value) / 100;
  const c = toCents(custo.value) / 100;

  if (p === 0 && c === 0) {
    margemValor.textContent = "—";
    margemPct.textContent = "";
    caixa.classList.remove("neg");
    return;
  }

  const margem = p - c;
  const pct = p > 0 ? (margem / p) * 100 : 0;

  margemValor.textContent = (margem < 0 ? "− " : "") + "R$ " + fmt(Math.abs(margem)) + " por unidade";
  margemPct.textContent = pct.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
  caixa.classList.toggle("neg", margem < 0);
}