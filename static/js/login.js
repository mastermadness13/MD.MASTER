function togglePass() {
    var passwordInput = document.getElementById("password");
    var toggleLabel = document.getElementById("toggleLabel");
    var toggleButton = document.getElementById("togglePassword");

    if (passwordInput.type === "password") {
        passwordInput.type = "text";
        toggleLabel.textContent = "\u0625\u062e\u0641\u0627\u0621";
        toggleButton.setAttribute("aria-label", "\u0625\u062e\u0641\u0627\u0621 \u0643\u0644\u0645\u0629 \u0627\u0644\u0645\u0631\u0648\u0631");
    } else {
        passwordInput.type = "password";
        toggleLabel.textContent = "\u0625\u0638\u0647\u0627\u0631";
        toggleButton.setAttribute("aria-label", "\u0625\u0638\u0647\u0627\u0631 \u0643\u0644\u0645\u0629 \u0627\u0644\u0645\u0631\u0648\u0631");
    }
}

function showToast(message, type) {
    var toast = document.getElementById('toast');
    var toastMsg = document.getElementById('toastMsg');
    var toastIcon = document.getElementById('toastIcon');
    if (!toast || !toastMsg || !toastIcon) return alert(message);

    toastMsg.textContent = message;
    toastIcon.textContent = type === 'error' ? '\u2715' : '\u2713';
    toast.className = 'notification-toast show ' + (type || 'success');
    setTimeout(function() { toast.className = 'notification-toast'; }, 4000);
}

document.addEventListener("DOMContentLoaded", function() {
    var userForm = document.getElementById("loginForm");
    if (userForm) {
        userForm.addEventListener("keydown", function(e) {
            if (e.key === "Enter") {
                e.preventDefault();
                this.requestSubmit();
            }
        });

        userForm.addEventListener("submit", function(e) {
            var username = document.getElementById("username").value.trim();
            var password = document.getElementById("password").value.trim();

            if (!username) {
                e.preventDefault();
                showToast("\u064a\u0631\u062c\u0649 \u0625\u062f\u062e\u0627\u0644 \u0627\u0633\u0645 \u0627\u0644\u0645\u0633\u062a\u062e\u062f\u0645", "error");
                return;
            }

            if (!password) {
                e.preventDefault();
                showToast("\u064a\u0631\u062c\u0649 \u0625\u062f\u062e\u0627\u0644 \u0643\u0644\u0645\u0629 \u0627\u0644\u0645\u0631\u0648\u0631", "error");
                return;
            }
        });
    }
});
