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

document.querySelectorAll("[data-copy-target]").forEach((button) => {
  button.addEventListener("click", async () => {
    const target = document.getElementById(button.dataset.copyTarget);
    if (!target) return;
    const originalLabel = button.dataset.copyLabel || button.textContent;
    try {
      await navigator.clipboard.writeText(target.textContent.trim());
      button.textContent = "Copied complete JD";
    } catch (_error) {
      const range = document.createRange();
      range.selectNodeContents(target);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = "JD selected — copy now";
    }
    window.setTimeout(() => {
      button.textContent = originalLabel;
    }, 2600);
  });
});

const roleControl = document.querySelector("[data-role-control]");
if (roleControl) {
  const cards = [...roleControl.querySelectorAll("[data-role-family]")];
  const slider = roleControl.querySelector("[data-role-slider]");
  const output = roleControl.querySelector("[data-role-output]");
  const label = roleControl.querySelector("[data-role-label]");
  const description = roleControl.querySelector("[data-role-description]");
  const aliases = roleControl.querySelector("[data-role-aliases]");
  const count = roleControl.querySelector("[data-role-count]");
  const save = roleControl.querySelector("[data-role-save]");
  const reset = roleControl.querySelector("[data-role-reset]");
  let selected = cards[0];

  const renderCount = () => {
    const scores = selected.dataset.scores
      ? selected.dataset.scores.split(",").map(Number)
      : [];
    const visible = scores.filter((score) => score >= Number(slider.value)).length;
    output.value = slider.value;
    count.textContent = String(visible);
    selected.querySelector("b").textContent = `${slider.value}%`;
    selected.querySelector("small").textContent = `${visible} matches visible`;
    save.action = `/profile/role-threshold/${selected.dataset.id}/${slider.value}`;
  };

  const selectRole = (card) => {
    cards.forEach((item) => item.classList.toggle("selected", item === card));
    selected = card;
    label.textContent = card.dataset.label;
    description.textContent = card.dataset.description;
    aliases.textContent = card.dataset.aliases;
    slider.value = card.dataset.threshold;
    reset.action = `/profile/role-threshold-reset/${card.dataset.id}`;
    renderCount();
  };

  cards.forEach((card) => card.addEventListener("click", () => selectRole(card)));
  slider.addEventListener("input", renderCount);
  const requested = new URLSearchParams(window.location.search).get("family");
  selectRole(cards.find((card) => card.dataset.id === requested) || cards[0]);
}
