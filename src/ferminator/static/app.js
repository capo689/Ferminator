const menuButton = document.querySelector(".menu-button");
const sidebar = document.querySelector(".sidebar");

if (menuButton && sidebar) {
  menuButton.addEventListener("click", () => {
    const open = sidebar.classList.toggle("open");
    menuButton.setAttribute("aria-expanded", String(open));
  });
}

document.querySelectorAll("[data-toast]").forEach((button) => {
  button.addEventListener("click", () => {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.setAttribute("role", "status");
    toast.textContent = button.dataset.toast;
    document.body.appendChild(toast);
    window.setTimeout(() => toast.classList.add("visible"), 10);
    window.setTimeout(() => toast.remove(), 2600);
  });
});

document.querySelectorAll(".company-logo[data-initial] img").forEach((image) => {
  image.addEventListener("error", () => {
    const parent = image.parentElement;
    image.remove();
    parent.textContent = parent.dataset.initial;
  });
});
