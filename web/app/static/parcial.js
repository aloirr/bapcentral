/* T-0026: copiar a imagem da parcial para colar no WhatsApp (sem o clipboard do navegador, só baixa) */
(function () {
  var bt = document.getElementById('copiar'), msg = document.getElementById('msg-copia');
  if (!bt) return;
  bt.addEventListener('click', function () {
    msg.textContent = '';
    if (!(navigator.clipboard && window.ClipboardItem)) {
      msg.textContent = 'Este navegador não copia imagem: use Baixar imagem.';
      return;
    }
    fetch(bt.dataset.url, { credentials: 'same-origin' }).then(function (r) { return r.blob(); })
      .then(function (b) { return navigator.clipboard.write([new ClipboardItem({ 'image/png': b })]); })
      .then(function () { msg.textContent = 'Imagem copiada: abra o WhatsApp e cole.'; })
      .catch(function () { msg.textContent = 'Não consegui copiar: use Baixar imagem.'; });
  });
})();
