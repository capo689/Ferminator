const menuButton = document.querySelector(".menu-button");
const sidebar = document.querySelector(".sidebar");

if (menuButton && sidebar) {
  menuButton.addEventListener("click", () => {
    const open = sidebar.classList.toggle("open");
    menuButton.setAttribute("aria-expanded", String(open));
  });
}

const discoverForm = document.querySelector("[data-discover-form]");
if (discoverForm) {
  const mode = discoverForm.querySelector("[data-location-mode]");
  const nearControls = [...discoverForm.querySelectorAll("[data-near-control]")];
  let timer;

  const showNearControls = () => {
    const visible = ["near", "remote_or_near"].includes(mode.value);
    nearControls.forEach((control) => control.classList.toggle("is-dimmed", !visible));
  };
  const submit = () => {
    window.clearTimeout(timer);
    if (discoverForm.reportValidity()) discoverForm.requestSubmit();
  };

  discoverForm.querySelectorAll("select").forEach((control) => {
    control.addEventListener("change", () => {
      showNearControls();
      submit();
    });
  });
  discoverForm.querySelector('input[name="zip"]')?.addEventListener("input", (event) => {
    if (event.target.value.length === 5) {
      timer = window.setTimeout(submit, 350);
    }
  });
  showNearControls();
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

const wrongDialog = document.querySelector("[data-wrong-dialog]");
if (wrongDialog) {
  const form = wrongDialog.querySelector("[data-wrong-form]");
  const jobLabel = wrongDialog.querySelector("[data-wrong-job]");
  const reasonCode = form.querySelector('[name="wrong_reason_code"]');
  const reasonNote = form.querySelector('[name="reason"]');
  const close = () => wrongDialog.close();

  document.querySelectorAll("[data-wrong-feedback]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      form.action = "/discover";
      form.elements.job_id.value = button.dataset.jobId;
      jobLabel.textContent = button.dataset.jobLabel;
      reasonCode.value = button.dataset.reasonCode || "";
      reasonNote.value = button.dataset.reasonNote || "";
      // Open after the triggering click fully settles. This prevents the same
      // pointer action from reaching the modal's submit button in some browsers.
      window.setTimeout(() => {
        wrongDialog.showModal();
        reasonCode.focus();
      }, 0);
    });
  });
  wrongDialog.querySelector("[data-wrong-close]").addEventListener("click", close);
  wrongDialog.querySelector("[data-wrong-cancel]").addEventListener("click", close);
  wrongDialog.addEventListener("click", (event) => {
    if (event.target === wrongDialog) close();
  });
}

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

const pipelineBoard = document.querySelector("[data-pipeline-board]");
if (pipelineBoard) {
  const cards = [...pipelineBoard.querySelectorAll("[data-pipeline-card]")];
  const search = document.querySelector("[data-pipeline-search]");
  const filter = document.querySelector("[data-pipeline-filter]");
  const sort = document.querySelector("[data-pipeline-sort]");

  const moveJob = async (card, state) => {
    const current = card.closest("[data-pipeline-stage]")?.dataset.pipelineStage;
    if (
      state === "applied" &&
      current !== "applied" &&
      !window.confirm("Mark this job as applied? This creates permanent application history.")
    ) {
      const select = card.querySelector("[data-move-select]");
      if (select && current) select.value = current;
      return;
    }
    card.classList.add("is-moving");
    try {
      const response = await fetch("/pipeline", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          "X-Pipeline-Request": "true",
        },
        body: new URLSearchParams({
          operation: "stage",
          job_id: card.dataset.jobId,
          state,
        }),
      });
      if (!response.ok) throw new Error(`Move failed: ${response.status}`);
      window.location.assign(response.url);
    } catch (_error) {
      card.classList.remove("is-moving");
      const status = document.createElement("div");
      status.className = "pipeline-toast error";
      status.setAttribute("role", "alert");
      status.textContent = "That move did not save. The card is still in its previous stage.";
      document.body.appendChild(status);
      window.setTimeout(() => status.remove(), 4000);
    }
  };

  cards.forEach((card) => {
    card.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("text/plain", card.dataset.jobId);
      event.dataTransfer.effectAllowed = "move";
      card.classList.add("is-dragging");
    });
    card.addEventListener("dragend", () => card.classList.remove("is-dragging"));
    card.querySelector("[data-move-select]")?.addEventListener("change", (event) => {
      moveJob(card, event.target.value);
    });
  });

  pipelineBoard.querySelectorAll("[data-pipeline-stage]").forEach((column) => {
    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      column.classList.add("is-drop-target");
    });
    column.addEventListener("dragleave", () => column.classList.remove("is-drop-target"));
    column.addEventListener("drop", (event) => {
      event.preventDefault();
      column.classList.remove("is-drop-target");
      const jobId = event.dataTransfer.getData("text/plain");
      const card = cards.find((item) => item.dataset.jobId === jobId);
      if (card && card.closest("[data-pipeline-stage]") !== column) {
        moveJob(card, column.dataset.pipelineStage);
      }
    });
  });

  const refresh = () => {
    const needle = (search?.value || "").trim().toLowerCase();
    const mode = filter?.value || "all";
    cards.forEach((card) => {
      const matchesText = !needle || card.dataset.search.toLowerCase().includes(needle);
      const matchesMode =
        mode === "all" ||
        (mode === "attention" && card.classList.contains("is-overdue")) ||
        (mode === "priority" && Number(card.dataset.priority) > 0) ||
        (mode === "stale" && Number(card.dataset.days) >= 7);
      card.hidden = !(matchesText && matchesMode);
    });
    pipelineBoard.querySelectorAll("[data-pipeline-stage]").forEach((column) => {
      const visible = [...column.querySelectorAll("[data-pipeline-card]")]
        .filter((card) => !card.hidden).length;
      column.querySelector("[data-stage-count]").textContent = String(visible);
    });
  };

  const sortCards = () => {
    const mode = sort?.value || "priority";
    pipelineBoard.querySelectorAll("[data-pipeline-dropzone]").forEach((zone) => {
      const items = [...zone.querySelectorAll("[data-pipeline-card]")];
      items.sort((left, right) => {
        if (mode === "score") return Number(right.dataset.score) - Number(left.dataset.score);
        if (mode === "age") return Number(right.dataset.days) - Number(left.dataset.days);
        if (mode === "followup") {
          return (left.dataset.followup || "9999").localeCompare(
            right.dataset.followup || "9999"
          );
        }
        return Number(right.dataset.priority) - Number(left.dataset.priority);
      });
      items.forEach((item) => zone.appendChild(item));
    });
  };

  search?.addEventListener("input", refresh);
  filter?.addEventListener("change", refresh);
  sort?.addEventListener("change", sortCards);
  sortCards();
}

const historyToggle = document.querySelector("[data-history-toggle]");
const pipelineHistory = document.querySelector("[data-pipeline-history]");
if (historyToggle && pipelineHistory) {
  historyToggle.addEventListener("click", () => {
    pipelineHistory.hidden = !pipelineHistory.hidden;
    historyToggle.setAttribute("aria-expanded", String(!pipelineHistory.hidden));
    if (!pipelineHistory.hidden) pipelineHistory.scrollIntoView({ behavior: "smooth" });
  });
}
