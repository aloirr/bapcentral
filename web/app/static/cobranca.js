// Fila "Cobrar no WhatsApp": monta o link wa.me com o telefone e o texto da tela e registra ENVIADO/PULADO.
// Nenhuma regra aqui: o servidor confere perfil, cliente, valores e o clique repetido.
(function () {
  var fila = document.querySelector('.fila');
  if (!fila) return;
  function normaliza(v) { return (v || '').replace(/\D/g, ''); }
  function numero(card, link) {
    var d = normaliza(card.querySelector('.cob-tel').value);
    if (!d) return link.dataset.base;
    if (d.indexOf('55') === 0 && d.length >= 12) return d;
    return '55' + d.replace(/^0+/, '');
  }
  function atualizaLink(card) {
    var a = card.querySelector('.cob-link');
    var n = numero(card, a);
    if (!n) { a.hidden = true; return; }
    a.hidden = false;
    a.href = 'https://wa.me/' + n + '?text=' + encodeURIComponent(card.querySelector('.cob-msg').value);
  }
  function botoes(card, desligado) {
    card.querySelectorAll('button').forEach(function (x) { x.disabled = desligado; });
  }
  fila.querySelectorAll('.cob').forEach(function (card) {
    card.querySelector('.cob-tel').addEventListener('input', function () { atualizaLink(card); });
    card.querySelector('.cob-msg').addEventListener('input', function () { atualizaLink(card); });
    card.querySelectorAll('button[data-acao]').forEach(function (b) {
      b.addEventListener('click', function () {
        var erro = card.querySelector('.cob-erro');
        erro.textContent = '';
        var corpo = new URLSearchParams({
          csrf: fila.dataset.csrf, pacote_sha: fila.dataset.sha, cliente: card.dataset.cod, acao: b.dataset.acao,
          telefone: b.dataset.acao === 'ENVIADO' ? card.querySelector('.cob-tel').value : ''
        });
        botoes(card, true);
        fetch(fila.dataset.url, {
          method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: corpo.toString()
        }).then(function (r) { return r.json().then(function (j) { return [r.ok, j]; }); })
          .then(function (res) {
            if (!res[0] || !res[1].ok) throw new Error(res[1].erro || 'Não foi possível registrar.');
            card.querySelector('.cob-sit-txt').textContent = res[1].situacao + (res[1].repetido ? ' (já registrado)' : '');
            card.classList.add('feito');
            setTimeout(function () { botoes(card, false); }, 60000);
          }).catch(function (e) {
            erro.textContent = e.message;
            botoes(card, false);
          });
      });
    });
  });
})();
