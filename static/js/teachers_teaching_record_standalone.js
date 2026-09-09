        (function () {
          var input = document.getElementById('period-search');
          if (!input) return;
          var none = document.getElementById('period-no-match');
          var cards = Array.prototype.slice.call(
            document.querySelectorAll('#periods-grid > a'));
          function norm(x) {
            return (x || '').toLowerCase()
              .replace(/[\u0623\u0625\u0622]/g, '\u0627')
              .replace(/\u0629/g, '\u0647');
          }
          input.addEventListener('input', function () {
            var q = norm(input.value.trim());
            var visible = 0;
            cards.forEach(function (card) {
              var hit = !q || norm(card.getAttribute('data-search')).indexOf(q) !== -1;
              card.classList.toggle('hidden', !hit);
              if (hit) visible++;
            });
            if (none) none.classList.toggle('hidden', visible > 0);
          });
        })();
      
