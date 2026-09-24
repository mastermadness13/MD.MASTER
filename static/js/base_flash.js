
            (function () {
              var BOOT = window.BASE_FLASH_BOOT || {};
              var messages = BOOT.messages || [];
              function fire() {
                messages.forEach(function (m) {
                  if (window.showNotification) {
                    var type = m[0] === 'recovery_code' ? 'recovery_code'
                      : m[0] === 'error' ? 'error'
                      : (m[0] === 'success' ? 'success'
                      : (m[0] === 'warning' ? 'warning' : 'info'));
                    window.showNotification(
                      String(m[1]), type, type === 'recovery_code' ? 0 : 4500
                    );
                  }
                });
              }
              if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', fire);
              } else {
                setTimeout(fire, 250);
              }
            })();
          