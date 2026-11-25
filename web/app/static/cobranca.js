// Fila "Cobrar no WhatsApp": link wa.me com o telefone e o texto da tela; registra ENVIADO/PULADO.
// Nenhuma regra aqui: o servidor confere perfil, cliente, valores e o clique repetido.
// Desfazer: o registro só é enviado depois de 10 s (ou ao sair da página); desfazer cancela e nada é gravado.
(function () {
  var secoes = document.querySelectorAll('.fila');
  if (!secoes.length) return;
  var ESPERA = 10000;
  var pendentes = [];
  function normaliza(v) { return (v || '').replace(/\D/g, ''); }
  function numero(card, link) {
    var d = normaliza(card.querySelector('.cob-tel').value);
    if (!d) return link.dataset.base;
    if (d.indexOf('55') === 0 && d.length >= 12) return d;
    d = d.replace(/^0+/, '');
    return d.length >= 10 ? '55' + d : '';
  }
  function atualizaLink(card) {
    var a = card.querySelector('.cob-link');
    var n = numero(card, a);
    if (!n) { a.hidden = true; card.querySelector('.cob-enviado').hidden = true; return; }
    a.hidden = false;
    a.href = 'https://wa.me/' + n + '?text=' + encodeURIComponent(card.querySelector('.cob-msg').value);
  }
  function botoes(card, desligado) {
    card.querySelectorAll('button[data-acao]').forEach(function (x) { x.disabled = desligado; });
  }
  function corpo(secao, card, acao) {
    return new URLSearchParams({
      csrf: secao.dataset.csrf, pacote_sha: secao.dataset.sha, cliente: card.dataset.cod, acao: acao,
      telefone: acao === 'ENVIADO' ? card.querySelector('.cob-tel').value : ''
    }).toString();
  }
  function envia(p, keepalive) {
    if (p.enviado) return;
    p.enviado = true;
    clearTimeout(p.timer);
    p.card.querySelector('.cob-desfaz').hidden = true;
    fetch(p.secao.dataset.url, {
      method: 'POST', credentials: 'same-origin', keepalive: !!keepalive,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: corpo(p.secao, p.card, p.acao)
    }).then(function (r) { return r.json().then(function (j) { return [r.ok, j]; }); })
      .then(function (res) {
        if (!res[0] || !res[1].ok) throw new Error(res[1].erro || 'Não foi possível registrar.');
        var t = p.card.querySelector('.cob-sit-txt');
        t.textContent = res[1].situacao + (res[1].repetido ? ' (já registrado)' : '');
        t.className = 'selo cob-sit-txt ' + (p.acao === 'ENVIADO' ? 'selo-ok' : 'selo-neutro');
        p.card.classList.add('feito');
      }).catch(function (e) {
        p.card.querySelector('.cob-erro').textContent = e.message;
        p.card.querySelector('.cob-sit-txt').textContent = 'ERRO AO REGISTRAR';
        botoes(p.card, false);
      });
  }
  secoes.forEach(function (secao) {
    secao.querySelectorAll('.cob').forEach(function (card) {
      var link = card.querySelector('.cob-link');
      var env = card.querySelector('.cob-enviado');
      card.querySelector('.cob-tel').addEventListener('input', function () { atualizaLink(card); });
      card.querySelector('.cob-msg').addEventListener('input', function () { atualizaLink(card); });
      link.addEventListener('click', function () { env.hidden = false; });      // ENVIADO só depois de abrir o WhatsApp
      card.querySelectorAll('button[data-acao]').forEach(function (b) {
        b.addEventListener('click', function () {
          card.querySelector('.cob-erro').textContent = '';
          botoes(card, true);
          var p = { secao: secao, card: card, acao: b.dataset.acao, enviado: false };
          var sit = card.querySelector('.cob-sit-txt');
          var antes = { txt: sit.textContent, cls: sit.className };
          sit.textContent = b.dataset.acao + ' HOJE';
          sit.className = 'selo cob-sit-txt ' + (b.dataset.acao === 'ENVIADO' ? 'selo-ok' : 'selo-neutro');
          var d = card.querySelector('.cob-desfaz');
          d.hidden = false;
          d.textContent = '';
          var bd = document.createElement('button');
          bd.type = 'button';
          bd.textContent = 'Desfazer';
          bd.addEventListener('click', function () {
            clearTimeout(p.timer);
            pendentes = pendentes.filter(function (x) { return x !== p; });
            p.enviado = true;
            sit.textContent = antes.txt;
            sit.className = antes.cls;
            d.hidden = true;
            botoes(card, false);
          });
          d.appendChild(bd);
          p.timer = setTimeout(function () { pendentes = pendentes.filter(function (x) { return x !== p; }); envia(p, false); }, ESPERA);
          pendentes.push(p);
        });
      });
    });
  });
  window.addEventListener('pagehide', function () {
    pendentes.slice().forEach(function (p) { envia(p, true); });
  });
})();
