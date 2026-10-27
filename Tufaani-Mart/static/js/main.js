document.addEventListener("DOMContentLoaded",()=>{document.querySelectorAll(".alert").forEach(a=>setTimeout(()=>{try{bootstrap.Alert.getOrCreateInstance(a).close()}catch(e){}},5000));});


// Show / hide password fields
function togglePassword(inputId, button) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const icon = button.querySelector('i');
    const label = button.querySelector('span');
    if (input.type === 'password') {
        input.type = 'text';
        if (icon) icon.className = 'fa-regular fa-eye-slash';
        if (label) label.textContent = 'Hide';
        button.setAttribute('aria-label', 'Hide password');
    } else {
        input.type = 'password';
        if (icon) icon.className = 'fa-regular fa-eye';
        if (label) label.textContent = 'Show';
        button.setAttribute('aria-label', 'Show password');
    }
}
