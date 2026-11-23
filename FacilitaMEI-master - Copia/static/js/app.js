// Máscaras simples para os campos brasileiros
const onlyDigits = (v) => v.replace(/\D/g, "");

const masks = {
  documento(v) {
    v = onlyDigits(v).slice(0, 14);
    if (v.length <= 11) {
      return v.replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d)/, "$1.$2").replace(/(\d{3})(\d{1,2})$/, "$1-$2");
    }
    return v.replace(/^(\d{2})(\d)/, "$1.$2").replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
            .replace(/\.(\d{3})(\d)/, ".$1/$2").replace(/(\d{4})(\d)/, "$1-$2");
  },
  telefone(v) {
    v = onlyDigits(v).slice(0, 11);
    return v.length > 10
      ? v.replace(/(\d{2})(\d{5})(\d{0,4})/, "($1) $2-$3")
      : v.replace(/(\d{2})(\d{4})(\d{0,4})/, "($1) $2-$3");
  },
  cep(v) {
    return onlyDigits(v).slice(0, 8).replace(/(\d{5})(\d)/, "$1-$2");
  },
};

Object.entries(masks).forEach(([id, fn]) => {
  const el = document.getElementById(id);
  if (el) el.addEventListener("input", () => (el.value = fn(el.value)));
});