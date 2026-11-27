// T-0050: "Novo usuário" refaz as duas partes do acesso (Do perfil / Liberar além do perfil) quando o perfil muda.
// Sem JavaScript, o <noscript> do formulário mostra só os faróis a liberar (o perfil entra sempre).
(function () {
  "use strict";
  var sel = document.getElementById("u-perfil"), lista = document.getElementById("u-lista");
  if (!sel) return;
  function aplicar() {
    var conj = document.querySelectorAll(".f-conj");
    for (var i = 0; i < conj.length; i++) {
      var ativo = conj[i].getAttribute("data-perfil") === sel.value;
      conj[i].hidden = !ativo;
      var caixas = conj[i].querySelectorAll("input");
      for (var k = 0; k < caixas.length; k++) caixas[k].disabled = !ativo;
    }
    if (lista) lista.disabled = false;     // com JS, a lista marcada é a lista toda (inclusive o que se tirou)
  }
  sel.addEventListener("change", aplicar);
  aplicar();
})();
