(function () {
  function recipiente(el) {
    return el.closest(".field, .campo") || el.parentElement;
  }

  function limparBox(box) {
    box.classList.remove("invalido");
    var m = box.querySelector(".msg-erro");
    if (m) m.remove();
  }

  function limpar(el) {
    limparBox(recipiente(el));
    el.removeAttribute("aria-invalid");
  }

  function erro(el) {
    if (el.required && el.value.trim() === "") return "Campo obrigatório";
    if (!el.checkValidity()) return "Informe um valor válido";
    return "";
  }

  function marcar(el, texto) {
    limpar(el);
    recipiente(el).classList.add("invalido");
    el.setAttribute("aria-invalid", "true");
    var p = document.createElement("p");
    p.className = "msg-erro";
    p.textContent = texto;
    (el.closest(".control") || el).insertAdjacentElement("afterend", p);
  }

  function campos(form) {
    return Array.prototype.filter.call(
      form.querySelectorAll("input, select, textarea"),
      function (el) { return el.type !== "hidden" && el.type !== "checkbox" && !el.disabled; }
    );
  }

  // Quando o usuário corrige o campo, o vermelho sai na hora
  function reavaliar(e) {
    var el = e.target;
    if (!el.closest) return;
    var box = recipiente(el);
    if (box.classList.contains("invalido") && !erro(el)) limpar(el);
  }

  document.querySelectorAll("form").forEach(function (form) {
    form.setAttribute("novalidate", ""); // desliga o balão padrão do navegador

    form.addEventListener("submit", function (e) {
      var primeiro = null;
      campos(form).forEach(function (el) {
        var msg = erro(el);
        if (msg) {
          marcar(el, msg);
          if (!primeiro) primeiro = el;
        } else {
          limpar(el);
        }
      });
      if (primeiro) {
        e.preventDefault();
        primeiro.focus();
        primeiro.scrollIntoView({ block: "center", behavior: "smooth" });
      }
    });

    form.addEventListener("input", reavaliar);
    form.addEventListener("change", reavaliar);
  });

  // Ao fechar uma janela (dialog), limpa os avisos de erro dela
  document.addEventListener("close", function (e) {
    if (e.target.tagName === "DIALOG") {
      e.target.querySelectorAll(".invalido").forEach(limparBox);
    }
  }, true);
})();