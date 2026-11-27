// T-0030/T-0033: visual BC3 — menu do celular, PC numa tela só (rolagem por dentro da tabela), lista que abre no
// celular (M3) e "carregar mais" (500 em 500 linhas, ao rolar).
(function () {
  "use strict";
  var corpo = document.body;
  var PC = window.matchMedia("(min-width: 1000px) and (min-height: 600px)");
  var CEL = window.matchMedia("(max-width: 700px)");

  // menu lateral no celular: abre pelo ☰; fecha com um toque fora e com Esc
  var bt = document.querySelector(".bc3-menu"), lado = document.getElementById("bc3-lado");
  function menu(abrir) {
    corpo.classList.toggle("bc3-menu-aberto", abrir);
    if (bt) bt.setAttribute("aria-expanded", abrir ? "true" : "false");
  }
  if (bt && lado) {
    bt.addEventListener("click", function (e) { e.stopPropagation(); menu(!corpo.classList.contains("bc3-menu-aberto")); });
    document.addEventListener("click", function (e) {
      if (corpo.classList.contains("bc3-menu-aberto") && !lado.contains(e.target)) menu(false);
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") menu(false); });
  }

  // PC: a tabela de cima ocupa a altura que sobra e rola por dentro; as de baixo têm 5 linhas (3 em tela baixa)
  var juntas = document.querySelector(".bc3-juntas");
  var cima = document.querySelector(".rolagem-dados.sem-rolagem") ||
             document.querySelector(".bc3-corpo > .rolagem-dados");
  function umaTela() {
    if (!PC.matches) return;
    // Painel Executivo: a página não rola; o gráfico e as tabelas rolam por dentro (estilo.css, `.painel-corpo`)
    if (document.querySelector(".painel-corpo, .parcial-corpo")) { corpo.classList.add("uma-tela"); return; }
    if (!cima) return;
    cima.classList.add("bc3-cima");
    document.querySelectorAll(".bc3-junta").forEach(function (d) { d.open = true; });
    corpo.classList.add("uma-tela");
    // os Filtros sobem para a barra das abas (não gastam uma linha da tela)
    var filt = document.querySelector(".bc3-corpo > .filtros-det"), acoes = document.querySelector(".bc3-acoes");
    if (filt && acoes) { filt.classList.add("bc3-filt"); acoes.insertBefore(filt, acoes.firstChild); }
    if (juntas) juntas.querySelectorAll(".bc3-junta").forEach(function (d) {
      var box = d.querySelector(".rolagem-dados"), tb = d.querySelector("tbody"), th = d.querySelector("thead");
      if (!box || !tb || !tb.rows.length) return;
      var n = window.innerHeight < 760 ? 3 : 5;
      var alt = tb.rows[0].getBoundingClientRect().height || 22;
      box.style.maxHeight = Math.ceil((th ? th.getBoundingClientRect().height : 0) + n * alt + 2) + "px";
      box.classList.add("bc3-rola");
    });
    cima.classList.add("bc3-rola");
  }
  umaTela();

  // carregar mais: ao chegar perto do fim da rolagem da tabela, pede mais 500 linhas (a contagem da aba é a do servidor)
  var carregando = false;
  function maisLinhas(destino) {
    var url = destino.getAttribute("data-mais");
    if (!url || carregando) return Promise.resolve(false);
    carregando = true;
    return fetch(url, { credentials: "same-origin" }).then(function (r) { return r.ok ? r.text() : ""; }).then(function (txt) {
      carregando = false;
      if (!txt) return false;
      var doc = new DOMParser().parseFromString(txt, "text/html");
      var tbody = document.querySelector(".rolagem-dados[data-mais] tbody"), lista = document.querySelector(".bc3-lista");
      doc.querySelectorAll("tbody tr").forEach(function (tr) { if (tbody) tbody.appendChild(document.importNode(tr, true)); });
      doc.querySelectorAll(".m3 > details").forEach(function (d) { if (lista) lista.appendChild(document.importNode(d, true)); });
      var prox = doc.querySelector(".prox"), novo = prox ? prox.getAttribute("data-mais") : "";
      document.querySelectorAll("[data-mais]").forEach(function (e) {
        if (novo) e.setAttribute("data-mais", novo); else e.removeAttribute("data-mais");
      });
      return true;
    }).catch(function () { carregando = false; return false; });
  }
  var rolagem = document.querySelector(".rolagem-dados[data-mais]");
  if (rolagem) {
    rolagem.addEventListener("scroll", function () {
      if (rolagem.scrollTop + rolagem.clientHeight >= rolagem.scrollHeight - 200) maisLinhas(rolagem);
    }, { passive: true });
  }

  // celular: lista que abre, de 10 em 10 ("Ver mais 10 (faltam N)"); acabadas as já carregadas, pede mais 500 ao servidor
  if (CEL.matches) {
    document.querySelectorAll(".bc3-lista").forEach(function (l) {
      var lote = parseInt(l.getAttribute("data-lote"), 10) || 10, vis = lote;
      var mais = document.createElement("button");
      mais.type = "button"; mais.className = "bc3-mais";
      function mostrar() {
        var itens = l.querySelectorAll(".bc3-item:not(.bc3-total)");
        itens.forEach(function (it, i) { it.hidden = i >= vis; });
        var falta = itens.length - vis;
        mais.textContent = "Ver mais " + Math.min(lote, Math.max(falta, 0)) + " (faltam " + Math.max(falta, 0) + ")";
        mais.hidden = falta <= 0 && !l.getAttribute("data-mais");
        if (falta <= 0 && l.getAttribute("data-mais")) mais.textContent = "Ver mais";
      }
      mais.addEventListener("click", function () {
        var itens = l.querySelectorAll(".bc3-item:not(.bc3-total)");
        if (vis >= itens.length && l.getAttribute("data-mais")) { maisLinhas(l).then(function () { vis += lote; mostrar(); }); return; }
        vis += lote; mostrar();
      });
      l.after(mais);
      mostrar();
    });
  } else {
    document.querySelectorAll(".bc3-junta").forEach(function (d) { d.open = true; });
  }
})();
