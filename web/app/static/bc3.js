// T-0030: visual BC3 — menu do celular, PC numa tela só (páginas no lugar da rolagem), lista que abre no celular.
(function () {
  "use strict";
  var corpo = document.body;
  var PC = window.matchMedia("(min-width: 1000px) and (min-height: 600px)");
  var CEL = window.matchMedia("(max-width: 700px)");

  // menu lateral no celular
  var bt = document.querySelector(".bc3-menu"), lado = document.getElementById("bc3-lado");
  if (bt && lado) {
    bt.addEventListener("click", function () {
      var aberto = corpo.classList.toggle("bc3-menu-aberto");
      bt.setAttribute("aria-expanded", aberto ? "true" : "false");
    });
  }

  // paginação de uma tabela: mostra `n` linhas por vez e desenha ‹ 1 2 3 › em `nav`
  function paginar(tbody, n, nav, info, rotulo) {
    var rs = Array.prototype.slice.call(tbody.rows);
    if (!rs.length || rs.length === 1 && rs[0].cells.length === 1) return;
    var tot = Math.max(1, Math.ceil(rs.length / n)), p = 0;
    function bt(txt, k, cls, rot) {
      var a = document.createElement("button");
      a.type = "button"; a.textContent = txt; if (cls) a.className = cls;
      if (rot) a.setAttribute("aria-label", rot);
      a.addEventListener("click", function () { ir(k); });
      nav.appendChild(a);
    }
    function ir(k) {
      p = Math.max(0, Math.min(tot - 1, k));
      rs.forEach(function (r, i) { r.hidden = !(i >= p * n && i < (p + 1) * n); });
      nav.textContent = "";
      if (tot > 1) {
        bt("‹", p - 1, p === 0 ? "off" : "", "Página anterior");
        var reticencias = false;
        for (var i = 0; i < tot; i++) {
          if (tot > 7 && Math.abs(i - p) > 2 && i !== 0 && i !== tot - 1) {
            if (!reticencias) { var e = document.createElement("span"); e.textContent = "…"; nav.appendChild(e); reticencias = true; }
            continue;
          }
          reticencias = false;
          bt(String(i + 1), i, i === p ? "on" : "", "Página " + (i + 1));
        }
        bt("›", p + 1, p === tot - 1 ? "off" : "", "Próxima página");
      }
      if (info) info.textContent = (p * n + 1) + "–" + Math.min(rs.length, (p + 1) * n) + " de " + rs.length + (rotulo ? " " + rotulo : "");
    }
    ir(0);
  }

  // PC: Farol com as tabelas de baixo numa tela só
  var juntas = document.querySelector(".bc3-juntas");
  var cima = document.querySelector(".rolagem-dados.sem-rolagem");
  function umaTela() {
    if (!PC.matches || !juntas || !cima) return;
    document.querySelectorAll(".bc3-junta").forEach(function (d) { d.open = true; });
    corpo.classList.add("uma-tela");
    // os Filtros sobem para a barra das abas (não gastam uma linha da tela)
    var filt = document.querySelector(".bc3-corpo > .filtros-det"), acoes = document.querySelector(".bc3-acoes");
    if (filt && acoes) { filt.classList.add("bc3-filt"); acoes.insertBefore(filt, acoes.firstChild); }
    // as de baixo: 5 linhas por página
    juntas.querySelectorAll(".bc3-junta").forEach(function (d) {
      var tb = d.querySelector("tbody");
      if (!tb) return;
      var nav = document.createElement("nav"); nav.className = "bc3-pag";
      d.appendChild(nav);
      paginar(tb, window.innerHeight < 760 ? 3 : 5, nav);
    });
    // a de cima: quantas linhas cabem na altura que sobra
    var rod = document.createElement("div"); rod.className = "bc3-rod";
    rod.innerHTML = '<span></span><nav class="bc3-pag"></nav>';
    cima.appendChild(rod);
    var tb = cima.querySelector("tbody"), thead = cima.querySelector("thead");
    if (!tb || !tb.rows.length) return;
    var alt = tb.rows[0].getBoundingClientRect().height || 30;
    var livre = cima.clientHeight - (thead ? thead.getBoundingClientRect().height : 0) - rod.getBoundingClientRect().height - 4;
    paginar(tb, Math.max(4, Math.floor(livre / alt)), rod.querySelector("nav"), rod.querySelector("span"), "pedidos");
  }
  umaTela();

  // celular: lista que abre, de 10 em 10
  if (CEL.matches) {
    document.querySelectorAll(".bc3-lista").forEach(function (l) {
      var itens = l.querySelectorAll(".bc3-item"), lote = parseInt(l.getAttribute("data-lote"), 10) || 10, vis = lote;
      if (itens.length <= lote) return;
      var mais = document.createElement("button");
      mais.type = "button"; mais.className = "bc3-mais";
      function mostrar() {
        itens.forEach(function (it, i) { it.hidden = i >= vis; });
        var falta = itens.length - vis;
        mais.textContent = "Ver mais " + Math.min(lote, falta) + " de " + falta;
        mais.hidden = falta <= 0;
      }
      mais.addEventListener("click", function () { vis += lote; mostrar(); });
      l.after(mais);
      mostrar();
    });
  } else {
    document.querySelectorAll(".bc3-junta").forEach(function (d) { d.open = true; });
  }
})();
