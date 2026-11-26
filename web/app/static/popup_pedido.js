// T-0028: popup com os dados do pedido ao passar o mouse (ou focar) no número do pedido.
// Lê os dados da própria linha (data-pop) e os itens do pedido na tabela "Analítico por pedido" da página.
(function () {
  "use strict";
  var pop = document.getElementById("pop-pedido");
  if (!pop) return;

  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined) e.textContent = txt;
    return e;
  }

  function itensDoPedido(ped) {
    // a junta cujo 1º cabeçalho é PEDIDO (o Analítico): as linhas desse pedido
    var out = null;
    document.querySelectorAll(".juntas .junta table").forEach(function (t) {
      var ths = t.querySelectorAll("thead tr:last-child th");
      if (!ths.length || ths[0].textContent.trim().toUpperCase() !== "PEDIDO") return;
      var nomes = Array.prototype.map.call(ths, function (h) { return h.textContent.trim(); });
      var quer = ["CÓD. PROD.", "DESCRIÇÃO", "QTD", "ATENDIDO", "FALTA"].filter(function (q) { return nomes.indexOf(q) >= 0; });
      var idx = quer.map(function (q) { return nomes.indexOf(q); });
      var linhas = [];
      t.querySelectorAll("tbody tr").forEach(function (tr) {
        var tds = tr.querySelectorAll("td");
        if (tds.length && tds[0].textContent.trim() === ped) {
          linhas.push(idx.map(function (i) { return i >= 0 && tds[i] ? tds[i].textContent.trim() : ""; }));
        }
      });
      out = { cab: quer, linhas: linhas };
    });
    return out;
  }

  function montar(a) {
    var pares;
    try { pares = JSON.parse(a.getAttribute("data-pop") || "[]"); } catch (e) { pares = []; }
    pop.textContent = "";
    var ped = a.textContent.trim();
    pop.appendChild(el("h3", "", "Pedido " + ped));
    var dl = el("dl", "pop-dados");
    pares.forEach(function (p) {
      if (p[0].toUpperCase() === "PEDIDO") return;
      dl.appendChild(el("dt", "", p[0]));
      dl.appendChild(el("dd", "", p[1]));
    });
    pop.appendChild(dl);
    var it = itensDoPedido(ped);
    if (it && it.linhas.length) {
      var t = el("table", "pop-itens"), tr = el("tr");
      it.cab.forEach(function (c, i) { tr.appendChild(el("th", i > 1 ? "num" : "", c)); });
      var th = el("thead"); th.appendChild(tr); t.appendChild(th);
      var tb = el("tbody");
      it.linhas.forEach(function (l) {
        var r = el("tr");
        l.forEach(function (v, i) { r.appendChild(el("td", i > 1 ? "num" : "", v)); });
        tb.appendChild(r);
      });
      t.appendChild(tb);
      pop.appendChild(el("h4", "", "Itens (" + it.linhas.length + ")"));
      pop.appendChild(t);
    }
  }

  function posicionar(a) {
    var r = a.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
    var x = Math.min(window.innerWidth - w - 8, Math.max(8, r.left));
    var y = r.bottom + 6;
    if (y + h > window.innerHeight - 8) y = Math.max(8, r.top - h - 6);
    pop.style.left = x + "px";
    pop.style.top = y + "px";
  }

  var atual = null;
  function mostrar(a) {
    atual = a;
    montar(a);
    pop.hidden = false;
    posicionar(a);
  }
  function esconder() { atual = null; pop.hidden = true; }

  document.querySelectorAll("a.sel-link[data-pop]").forEach(function (a) {
    a.addEventListener("mouseenter", function () { mostrar(a); });
    a.addEventListener("focus", function () { mostrar(a); });
    a.addEventListener("mouseleave", esconder);
    a.addEventListener("blur", esconder);
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") esconder(); });
  window.addEventListener("scroll", function () { if (atual) posicionar(atual); }, { passive: true });
})();
