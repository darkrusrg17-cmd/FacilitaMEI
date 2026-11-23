const dlg = document.getElementById("dlg-lancamento");
const valor = document.getElementById("valor");

// Abrir e fechar a janela
document.getElementById("abrir-lancamento").addEventListener("click", () => dlg.showModal());
dlg.querySelectorAll("[data-fechar]").forEach((b) => b.addEventListener("click", () => dlg.close()));
dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); }); // clique fora fecha

// Máscara de moeda: R$ 1.234,56
const cents = (s) => parseInt(s.replace(/\D/g, "") || "0", 10);
valor.addEventListener("input", () => {
  const c = cents(valor.value);
  valor.value = c ? "R$ " + (c / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "";
  valor.setCustomValidity(c ? "" : "Informe um valor maior que zero.");
});