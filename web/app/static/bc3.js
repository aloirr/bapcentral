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

  // celular: a aba ativa fica à vista na faixa de abas (T-0024, parecer de UX)
  var ativa = document.querySelector(".bc3-abas a.on");
  if (ativa && ativa.scrollIntoView && CEL.matches) ativa.scrollIntoView({ inline: "center", block: "nearest" });

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
  // a tabela de cima: a que liga as de baixo (Pedidos) ou a tabela da aba (os outros faróis)
  // T-0031 (Alexandre, 26/11: "Todos os farois devem ser nesse formato do farol de pedido"): a tabela de cima é a
  // que liga as de baixo (Pedidos) ou a tabela da aba (os outros faróis)
  var cima = document.querySelector(".rolagem-dados.sem-rolagem") ||
             document.querySelector(".bc3-corpo > .rolagem-dados");
  function umaTela() {
    if (!PC.matches || !cima) return;
    cima.classList.add("bc3-cima");
    document.querySelectorAll(".bc3-junta").forEach(function (d) { d.open = true; });
    corpo.classList.add("uma-tela");
    // os Filtros sobem para a barra das abas (não gastam uma linha da tela)
    var filt = document.querySelector(".bc3-corpo > .filtros-det"), acoes = document.querySelector(".bc3-acoes");
    if (filt && acoes) { filt.classList.add("bc3-filt"); acoes.insertBefore(filt, acoes.firstChild); }
    // Alexandre, 26/11: rolagem dentro da tabela, sem aumentar a tabela (no lugar das páginas 1 2 3)
    // as de baixo: altura de 5 linhas (3 em tela baixa), rolagem por dentro
    if (juntas) juntas.querySelectorAll(".bc3-junta").forEach(function (d) {
      var box = d.querySelector(".rolagem-dados"), tb = d.querySelector("tbody"), th = d.querySelector("thead");
      if (!box || !tb || !tb.rows.length) return;
      var n = window.innerHeight < 760 ? 3 : 5;
      var alt = tb.rows[0].getBoundingClientRect().height || 22;
      box.style.maxHeight = Math.ceil((th ? th.getBoundingClientRect().height : 0) + n * alt + 2) + "px";
      box.classList.add("bc3-rola");
    });
    // a de cima: ocupa a altura que sobra e rola por dentro; o rodapé diz quantas linhas há
    var tb = cima.querySelector("tbody");
    if (tb && tb.rows.length && !(tb.rows.length === 1 && tb.rows[0].cells.length === 1)) {
      var rod = document.createElement("div"); rod.className = "bc3-rod";
      rod.textContent = tb.rows.length + (document.querySelector(".sem-rolagem:not(.grade-lote)") ? " pedidos" : " linhas");
      cima.after(rod);
    }
    cima.classList.add("bc3-rola");
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

// T-0036 (revisão de UX, R2 e R3): as abas ficam numa linha só; o que não cabe vai para "Mais ▾".
// PC: pela largura. Celular: Resumo, a aba ativa e mais uma (3 à vista).
(function () {
  "use strict";
  var nav = document.querySelector(".bc3-abas");
  if (!nav) return;
  var links = Array.prototype.slice.call(nav.querySelectorAll("a"));
  if (links.length < 3) return;
  var CEL = window.matchMedia("(max-width: 700px)");
  var wrap = document.createElement("div");
  wrap.className = "bc3-abas-wrap";
  nav.parentNode.insertBefore(wrap, nav);
  wrap.appendChild(nav);
  var mais = document.createElement("details");
  mais.className = "bc3-amais"; mais.hidden = true;
  mais.innerHTML = "<summary>Mais ▾</summary><div></div>";
  wrap.appendChild(mais);
  var lista = mais.querySelector("div");
  function ativo() { for (var i = 0; i < links.length; i++) if (links[i].classList.contains("on")) return i; return 0; }
  function montar() {
    links.forEach(function (l) { l.hidden = false; });
    lista.textContent = ""; mais.hidden = true; mais.open = false;
    var ia = ativo();
    if (CEL.matches) {
      var ficar = [0]; if (ia > 0) ficar.push(ia);
      var k = ia + 1;
      while (ficar.length < 3 && k < links.length) { if (ficar.indexOf(k) < 0) ficar.push(k); k++; }
      k = ia - 1;
      while (ficar.length < 3 && k > 0) { if (ficar.indexOf(k) < 0) ficar.push(k); k--; }
      if (links.length > 3) links.forEach(function (l, i) { if (ficar.indexOf(i) < 0) l.hidden = true; });
    } else if (nav.scrollWidth > nav.clientWidth + 1) {
      mais.hidden = false;
      for (var i = links.length - 1; i > 0 && nav.scrollWidth > nav.clientWidth + 1; i--) if (i !== ia) links[i].hidden = true;
    }
    links.forEach(function (l) {
      if (!l.hidden) return;
      var c = l.cloneNode(true); c.hidden = false; c.removeAttribute("aria-current"); lista.appendChild(c);
    });
    mais.hidden = !lista.children.length;
  }
  montar();
  var t; window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(montar, 150); });
})();
