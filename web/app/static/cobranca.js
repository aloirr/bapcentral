// Fila "Cobrar no WhatsApp": link wa.me com o telefone e o texto da tela; registra ENVIADO/PULADO.
// Nenhuma regra aqui: o servidor confere perfil, cliente, valores e o clique repetido.
// Desfazer: o registro só vai ao servidor depois de 10 s, ao abrir o WhatsApp de outro cartão ou ao sair
// da página; desfazer cancela e nada é gravado. O pendente fica no sessionStorage até o servidor dar ok
// e é reenviado quando a página volta (o servidor ignora o mesmo clique em menos de 60 s).
// "ENVIADO HOJE" só aparece depois do ok do servidor; erro = selo vermelho e o botão volta à vista.
(function () {
  var secoes = document.querySelectorAll('.fila');
  var CHAVE = 'bap_cobranca_pendentes';
  var ESPERA = 10000;
  var vivos = {};                                  // id -> {p, timer}

  function ler() {
    try { return JSON.parse(sessionStorage.getItem(CHAVE) || '[]'); } catch (e) { return []; }
  }
  function gravar(lista) {
    try { sessionStorage.setItem(CHAVE, JSON.stringify(lista)); } catch (e) { /* sem storage: segue só em memória */ }
  }
  function guarda(p) { var l = ler().filter(function (x) { return x.id !== p.id; }); l.push(p); gravar(l); }
  function tira(p) { gravar(ler().filter(function (x) { return x.id !== p.id; })); }
  function cartao(cod) {
    var r = null;
    document.querySelectorAll('.cob').forEach(function (c) { if (c.dataset.cod === cod) r = c; });
    return r;
  }
  function botoes(card, desligado) {
    card.querySelectorAll('button[data-acao]').forEach(function (x) { x.disabled = desligado; });
  }
  function selo(card, txt, cls) {
    var t = card.querySelector('.cob-sit-txt');
    t.textContent = txt;
    t.className = 'selo cob-sit-txt ' + cls;
  }
  function erro(p, msg) {
    var card = cartao(p.cliente);
    if (!card) return;
    selo(card, 'ERRO AO REGISTRAR', 'selo-erro');
    card.querySelector('.cob-desfaz').hidden = true;
    card.querySelector('.cob-erro').textContent = msg;
    card.querySelector('.cob-enviado').hidden = false;           // à vista: não reenvie a mensagem ao cliente
    botoes(card, false);
  }

  function envia(p, keepalive) {
    if (p.enviando) return;
    p.enviando = true;
    var v = vivos[p.id];
    if (v) { clearTimeout(v.timer); v.timer = null; }
    var card = cartao(p.cliente);
    if (card) {
      card.querySelector('.cob-desfaz').hidden = true;
      selo(card, p.acao === 'ENVIADO' ? 'REGISTRANDO ENVIADO…' : 'REGISTRANDO PULADO…', 'selo-neutro');
    }
    var corpo = new URLSearchParams({
      csrf: p.csrf, pacote_sha: p.sha, cliente: p.cliente, acao: p.acao, telefone: p.telefone
    }).toString();
    fetch(p.url, {
      method: 'POST', credentials: 'same-origin', keepalive: !!keepalive,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: corpo
    }).then(function (r) {
      return r.json().then(function (j) { return [r.ok, j]; }, function () { return [false, {}]; });
    }).then(function (res) {
      p.enviando = false;
      if (!res[0] || !res[1].ok) { var e = new Error(res[1].erro || 'Não foi possível registrar.'); e.servidor = true; throw e; }
      tira(p);
      delete vivos[p.id];
      var c = cartao(p.cliente);
      if (c) {
        selo(c, res[1].situacao + (res[1].repetido ? ' (já registrado)' : ''),
             p.acao === 'ENVIADO' ? 'selo-ok' : 'selo-neutro');
        c.classList.add('feito');
        c.querySelector('.cob-erro').textContent = '';
      }
    }).catch(function (e) {
      p.enviando = false;                                          // fica no storage: tenta de novo ao voltar
      erro(p, (e && e.servidor ? e.message : 'Sem conexão com o servidor.') + ' Toque em "Marquei como enviado" de novo; não reenvie a mensagem.');
    });
  }

  function enviaTodos(keepalive, menos) {
    Object.keys(vivos).forEach(function (id) {
      if (vivos[id].p.cliente !== menos) envia(vivos[id].p, keepalive);
    });
  }

  // reenvia o que ficou pendente de uma visita anterior (trocou para o WhatsApp, fechou, caiu a rede)
  function retoma() {
    Object.keys(vivos).forEach(function (id) {                     // pedido que o navegador suspendeu sem resposta
      if (vivos[id].p.enviando && !vivos[id].timer) { vivos[id].p.enviando = false; envia(vivos[id].p, false); }
    });
    ler().forEach(function (p) {
      if (vivos[p.id]) return;
      vivos[p.id] = { p: p, timer: null };
      envia(p, false);
    });
  }

  if (location.hash === '#tratados') {
    var det = document.querySelector('details.tratados');
    if (det) det.open = true;
  }
  if (!secoes.length) return;

  // espelho do `celular()` do PC (mesma regra do servidor): '55' + DDD + 8 ou 9 dígitos, ou '' se inválido
  function celular(v) {
    var partes = (v || '').split(/[\/;,|]| e /);
    for (var i = 0; i < partes.length; i++) {
      var d = partes[i].replace(/\D/g, '');
      if (d.indexOf('55') === 0 && d.length >= 12) d = d.slice(2);
      d = d.replace(/^0+/, '');
      if (d.length < 10) continue;
      var ddd = d.slice(0, 2), num = d.slice(2);
      if (num.length === 8 && '6789'.indexOf(num[0]) >= 0) num = '9' + num;
      var resto = num.slice(1);
      if (resto.split('').every(function (c) { return c === resto[0]; })) return '';
      if (num.length === 8 || num.length === 9) return '55' + ddd + num;
    }
    return '';
  }
  function numero(card, link) {
    var digitado = card.querySelector('.cob-tel').value || '';
    return digitado.replace(/\D/g, '') ? celular(digitado) : link.dataset.base;
  }
  function atualizaLink(card) {
    var a = card.querySelector('.cob-link');
    var n = numero(card, a);
    if (!n) { a.hidden = true; card.querySelector('.cob-enviado').hidden = true; return; }
    a.hidden = false;
    a.href = 'https://wa.me/' + n + '?text=' + encodeURIComponent(card.querySelector('.cob-msg').value);
  }

  secoes.forEach(function (secao) {
    secao.querySelectorAll('.cob').forEach(function (card) {
      var link = card.querySelector('.cob-link');
      var env = card.querySelector('.cob-enviado');
      card.querySelector('.cob-tel').addEventListener('input', function () { atualizaLink(card); });
      card.querySelector('.cob-msg').addEventListener('input', function () { atualizaLink(card); });
      link.addEventListener('click', function () {
        env.hidden = false;                                        // ENVIADO só depois de abrir o WhatsApp
        enviaTodos(true, card.dataset.cod);                        // abriu o de outro cartão: fecha os pendentes
      });
      card.querySelectorAll('button[data-acao]').forEach(function (b) {
        b.addEventListener('click', function () {
          card.querySelector('.cob-erro').textContent = '';
          botoes(card, true);
          var p = { id: card.dataset.cod + '|' + b.dataset.acao + '|' + Date.now(), cliente: card.dataset.cod,
                    acao: b.dataset.acao, csrf: secao.dataset.csrf, sha: secao.dataset.sha, url: secao.dataset.url,
                    telefone: b.dataset.acao === 'ENVIADO' ? card.querySelector('.cob-tel').value : '' };
          var sit = card.querySelector('.cob-sit-txt');
          var antes = { txt: sit.textContent, cls: sit.className };
          selo(card, b.dataset.acao === 'ENVIADO' ? 'MARCANDO ENVIADO…' : 'MARCANDO PULADO…', 'selo-neutro');
          var d = card.querySelector('.cob-desfaz');
          d.hidden = false;
          d.textContent = '';
          var bd = document.createElement('button');
          bd.type = 'button';
          bd.textContent = 'Desfazer';
          bd.addEventListener('click', function () {
            clearTimeout(vivos[p.id].timer);
            delete vivos[p.id];
            tira(p);
            sit.textContent = antes.txt;
            sit.className = antes.cls;
            d.hidden = true;
            botoes(card, false);
          });
          d.appendChild(bd);
          ler().forEach(function (o) {                             // novo toque no mesmo cliente e ação: vale só ele
            if (o.cliente === p.cliente && o.acao === p.acao) { tira(o); delete vivos[o.id]; }
          });
          guarda(p);                                               // sobrevive à troca para o WhatsApp
          vivos[p.id] = { p: p, timer: setTimeout(function () { envia(p, false); }, ESPERA) };
        });
      });
    });
  });

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') enviaTodos(true);   // foi para o WhatsApp
    else retoma();                                                 // voltou: reenvia o que não deu ok
  });
  window.addEventListener('pagehide', function () { enviaTodos(true); });
  window.addEventListener('pageshow', retoma);
  retoma();
})();
