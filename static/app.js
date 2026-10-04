const HEX_COLOR = /^#?[0-9a-f]{6}$/i;
const CROSSWORD_CELL_CHARACTERS = /[^A-ZΑ-ΡΣ-ΩΆΈΉΊΌΎΏΪΫ#]/gu;

function normalizeCrosswordCell(value) {
  return value.normalize("NFC").toUpperCase()
    .replace(/Ι\u0308\u0301/gu, "Ϊ")
    .replace(/Υ\u0308\u0301/gu, "Ϋ")
    .replace(CROSSWORD_CELL_CHARACTERS, "")
    .slice(-1);
}

function normalizedColor(value) {
  const color = value.trim();
  if (!HEX_COLOR.test(color)) return null;
  return (color.startsWith("#") ? color : `#${color}`).toUpperCase();
}

function updateColorPreview(form) {
  const preview = form.querySelector("[data-color-preview]");
  if (!preview) return;

  const styleMap = {
    background_color: "--preview-background",
    profile_bg: "--preview-background",
    text_color: "--preview-body",
    profile_text: "--preview-text",
    title_color: "--preview-title",
  };

  Object.entries(styleMap).forEach(([fieldName, property]) => {
    const input = form.elements.namedItem(fieldName);
    const color = input && normalizedColor(input.value);
    if (color) preview.style.setProperty(property, color);
  });

  const title = form.querySelector("[data-preview-title]");
  const titleInput = form.elements.namedItem("title");
  const usernameInput = form.elements.namedItem("username");
  if (title && titleInput) title.textContent = titleInput.value || "Your post title";
  if (title && usernameInput) title.textContent = usernameInput.value || "Your profile";

  const body = form.querySelector("[data-preview-body]");
  const bodyInput = form.elements.namedItem("body");
  const bioInput = form.elements.namedItem("bio");
  if (body && bodyInput) body.textContent = bodyInput.value || "Your post body will use the selected body color.";
  if (body && bioInput) body.textContent = bioInput.value || "Your profile bio will appear here.";
}

function initializeColorControls() {
  document.querySelectorAll("[data-color-hex]").forEach((hexInput) => {
    const control = hexInput.closest(".color-control");
    const picker = control && control.querySelector("[data-color-wheel]");
    const form = hexInput.form;
    if (!picker || !form) return;

    const syncFromHex = () => {
      const color = normalizedColor(hexInput.value);
      if (!color) {
        hexInput.setCustomValidity("Enter a six-digit hex color.");
        return;
      }
      hexInput.setCustomValidity("");
      picker.value = color;
      updateColorPreview(form);
    };

    hexInput.addEventListener("input", syncFromHex);
    hexInput.addEventListener("blur", () => {
      const color = normalizedColor(hexInput.value);
      if (color) hexInput.value = color;
    });
    picker.addEventListener("input", () => {
      hexInput.value = picker.value.toUpperCase();
      hexInput.setCustomValidity("");
      updateColorPreview(form);
    });
    syncFromHex();
  });

  document.querySelectorAll("[data-color-preview]").forEach((preview) => {
    const form = preview.closest("form");
    if (!form) return;
    form.addEventListener("input", () => updateColorPreview(form));
    updateColorPreview(form);
  });
}

function initializeAvatarCrop() {
  const form = document.querySelector(".avatar-framing")?.closest("form");
  if (!form) return;

  const imageInput = form.querySelector("#avatar");
  const preview = form.querySelector("#avatar-crop-image");
  const placeholder = form.querySelector("[data-avatar-crop-placeholder]");
  const horizontal = form.querySelector("[data-avatar-position-x]");
  const vertical = form.querySelector("[data-avatar-position-y]");
  if (!imageInput || !preview || !placeholder || !horizontal || !vertical) return;

  let previewUrl = null;
  const updatePosition = () => {
    preview.style.objectPosition = `${horizontal.value}% ${vertical.value}%`;
  };

  horizontal.addEventListener("input", updatePosition);
  vertical.addEventListener("input", updatePosition);
  imageInput.addEventListener("change", () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    const [file] = imageInput.files;
    if (!file) return;
    previewUrl = URL.createObjectURL(file);
    preview.src = previewUrl;
    preview.hidden = false;
    placeholder.hidden = true;
    updatePosition();
  });

  updatePosition();
}

function crosswordEntryList(grid) {
  const acrossEntries = [];
  const downEntries = [];
  for (let row = 0; row < 15; row += 1) {
    for (let col = 0; col < 15; col += 1) {
      const index = row * 15 + col;
      if (grid[index] === "#") continue;
      const acrossStart = col === 0 || grid[index - 1] === "#";
      if (acrossStart) {
        let acrossLength = 0;
        while (col + acrossLength < 15 && grid[index + acrossLength] !== "#") {
          acrossLength += 1;
        }
        if (acrossLength >= 2) {
          acrossEntries.push({
            key: `A-${row}-${col}`,
            number: acrossEntries.length + 1,
            direction: "across",
            row,
            col,
            length: acrossLength,
          });
        }
      }
    }
  }
  for (let col = 0; col < 15; col += 1) {
    for (let row = 0; row < 15; row += 1) {
      const index = row * 15 + col;
      if (grid[index] === "#" || (row > 0 && grid[index - 15] !== "#")) continue;
      let downLength = 0;
      while (row + downLength < 15 && grid[index + downLength * 15] !== "#") {
        downLength += 1;
      }
      if (downLength >= 2) {
        downEntries.push({
          key: `D-${row}-${col}`,
          number: downEntries.length + 1,
          direction: "down",
          row,
          col,
          length: downLength,
        });
      }
    }
  }
  return [...acrossEntries, ...downEntries];
}

function initializeAdminCrossword() {
  const form = document.querySelector("[data-admin-crossword-form]");
  if (!form) return;
  const cells = Array.from(form.querySelectorAll("[data-admin-crossword-cell]"));
  const gridInput = form.querySelector("[data-crossword-solution]");
  const cluesInput = form.querySelector("[data-crossword-clues]");
  const acrossContainer = form.querySelector("[data-admin-across-clues]");
  const downContainer = form.querySelector("[data-admin-down-clues]");
  if (cells.length !== 225 || !gridInput || !cluesInput || !acrossContainer || !downContainer) return;

  let clues = {};
  try {
    clues = JSON.parse(cluesInput.value || "{}");
  } catch {
    clues = {};
  }

  const currentGrid = () => cells
    .map((cell) => normalizeCrosswordCell(cell.value) || " ")
    .join("");
  const currentHints = () => {
    const existingHints = {};
    form.querySelectorAll("[data-crossword-clue]").forEach((input) => {
      existingHints[input.dataset.crosswordClue] = input.value;
    });
    return { ...clues, ...existingHints };
  };
  const updateGrid = () => {
    cells.forEach((cell) => {
      cell.value = normalizeCrosswordCell(cell.value);
      cell.classList.toggle("is-blocked", cell.value === "#");
    });
    const grid = currentGrid();
    const hints = currentHints();
    const entries = crosswordEntryList(grid);
    acrossContainer.replaceChildren();
    downContainer.replaceChildren();
    form.querySelectorAll("[data-admin-crossword-number]").forEach((number) => number.remove());
    const startNumbers = new Map();
    entries.forEach((entry) => {
      const label = document.createElement("label");
      label.className = "crossword-clue-field";
      label.htmlFor = `clue-${entry.key}`;
      label.textContent = `${entry.number}. (${entry.length}) `;
      const input = document.createElement("input");
      input.id = `clue-${entry.key}`;
      input.type = "text";
      input.maxLength = 200;
      input.required = true;
      input.placeholder = `Hint for ${entry.number}`;
      input.value = hints[entry.key] ?? "";
      input.dataset.crosswordClue = entry.key;
      label.append(input);
      (entry.direction === "across" ? acrossContainer : downContainer).append(label);

      const cellIndex = entry.row * 15 + entry.col;
      const numbers = startNumbers.get(cellIndex) ?? [];
      numbers.push(String(entry.number));
      startNumbers.set(cellIndex, numbers);
    });
    startNumbers.forEach((numbers, index) => {
      const square = form.querySelector(`[data-admin-crossword-square="${index}"]`);
      if (!square) return;
      const number = document.createElement("small");
      number.className = "admin-crossword-number";
      number.dataset.adminCrosswordNumber = "";
      number.textContent = numbers.join("/");
      square.append(number);
    });
    gridInput.value = Array.from({ length: 15 }, (_, row) =>
      grid.slice(row * 15, (row + 1) * 15),
    ).join("\n");
  };

  cells.forEach((cell) => {
    cell.addEventListener("focus", () => cell.select());
    cell.addEventListener("input", () => {
      cell.value = normalizeCrosswordCell(cell.value);
      updateGrid();
    });
  });
  form.addEventListener("submit", () => {
    const hints = Object.fromEntries(
      Array.from(form.querySelectorAll("[data-crossword-clue]"))
        .map((input) => [input.dataset.crosswordClue, input.value]),
    );
    cluesInput.value = JSON.stringify(hints);
    const grid = currentGrid();
    gridInput.value = Array.from({ length: 15 }, (_, row) =>
      grid.slice(row * 15, (row + 1) * 15),
    ).join("\n");
  });
  updateGrid();

  const resetForm = document.querySelector(".crossword-reset-form");
  resetForm?.addEventListener("submit", () => {
    cells.forEach((cell) => {
      cell.value = "#";
    });
    updateGrid();
  });
}

function initializeCrosswordSolver() {
  const clueEntries = Array.from(document.querySelectorAll("[data-crossword-entry]"));
  if (clueEntries.length) {
    const orderedEntries = {
      across: clueEntries.filter((entry) => entry.dataset.direction === "across")
        .sort((a, b) => Number(a.dataset.row) - Number(b.dataset.row)
          || Number(a.dataset.col) - Number(b.dataset.col)),
      down: clueEntries.filter((entry) => entry.dataset.direction === "down")
        .sort((a, b) => Number(a.dataset.col) - Number(b.dataset.col)
          || Number(a.dataset.row) - Number(b.dataset.row)),
    };
    const starts = new Map();
    Object.entries(orderedEntries).forEach(([direction, entries]) => {
      entries.forEach((entry, index) => {
        const number = index + 1;
        const numberElement = entry.querySelector(".crossword-clue-number");
        if (numberElement) numberElement.textContent = `${number}.`;
        const key = `${Number(entry.dataset.row) + 1},${Number(entry.dataset.col) + 1}`;
        starts.set(key, [...(starts.get(key) ?? []), `${direction} ${number}`]);
        const squareIndex = (Number(entry.dataset.row) - 1) * 15
          + Number(entry.dataset.col) - 1;
        const square = document.querySelector(`[data-crossword-square="${squareIndex}"]`);
        if (square) {
          const numberLabel = square.querySelector("[data-crossword-start-number]");
          if (numberLabel) {
            const cellNumbers = [...(numberLabel.dataset.numbers ?? "").split("/").filter(Boolean)];
            cellNumbers.push(String(number));
            numberLabel.dataset.numbers = cellNumbers.join("/");
            numberLabel.textContent = cellNumbers.join("/");
          }
        }
      });
      entries.forEach((entry) => entry.parentElement.append(entry));
    });
    document.querySelectorAll("[data-crossword-square]").forEach((square) => {
      const key = `${square.dataset.row},${square.dataset.col}`;
      const labels = starts.get(key) ?? [];
      square.setAttribute(
        "aria-label",
        `Row ${square.dataset.row}, column ${square.dataset.col}`
          + (labels.length ? `: ${labels.join(", ")}` : ""),
      );
    });
  }

  const cells = Array.from(document.querySelectorAll("[data-crossword-cell]"));
  const crosswordKey = "boki-crossword-answers";

  // Restore crossword answers from localStorage
  const savedAnswers = localStorage.getItem(crosswordKey);
  if (savedAnswers) {
    try {
      const answers = JSON.parse(savedAnswers);
      cells.forEach((cell) => {
        const index = Number(cell.dataset.crosswordCell);
        if (answers[index]) {
          cell.value = answers[index];
        }
      });
    } catch {
      // Ignore if localStorage data is corrupted
    }
  }

  cells.forEach((cell) => {
    cell.addEventListener("input", () => {
      cell.value = normalizeCrosswordCell(cell.value);
      // Save to localStorage on each input
      const answers = {};
      cells.forEach((c) => {
        const index = Number(c.dataset.crosswordCell);
        if (c.value) answers[index] = c.value;
      });
      localStorage.setItem(crosswordKey, JSON.stringify(answers));

      const index = Number(cell.dataset.crosswordCell);
      const next = cells.find((candidate) => Number(candidate.dataset.crosswordCell) > index);
      if (cell.value && next) next.focus();
    });
  });

  const form = document.querySelector("[data-crossword-solve-form]");
  if (!form) return;
  const guessInput = form.querySelector("[data-crossword-guess]");
  const status = form.querySelector("[data-crossword-status]");
  if (!guessInput || !status) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const guesses = Array(225).fill("#");
    cells.forEach((cell) => {
      guesses[Number(cell.dataset.crosswordCell)] = normalizeCrosswordCell(cell.value);
    });
    guessInput.value = guesses.join("");
    const button = form.querySelector("button[type='submit']");
    button.disabled = true;
    status.textContent = "Checking your answers…";
    try {
      const response = await fetch(form.action, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/x-www-form-urlencoded",
        },
        credentials: "same-origin",
        body: new URLSearchParams(new FormData(form)),
      });
      if (!response.ok) throw new Error(`Could not check the puzzle (${response.status}).`);
      const result = await response.json();
      if (result.solved) {
        status.textContent = "Puzzle solved! Your star is being added.";
        localStorage.removeItem(crosswordKey);
        window.location.reload();
        return;
      }
      status.textContent = "Not quite yet. Check your answers and try again.";
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
}

function initializeAdminSearch() {
  document.querySelectorAll("[data-admin-search-form]").forEach((form) => {
    const input = form.querySelector("[data-admin-search]");
    const selectedId = form.querySelector("[data-selected-id]");
    const results = form.querySelector("[data-search-results]");
    if (!input || !selectedId || !results) return;
    const help = document.getElementById(input.getAttribute("aria-describedby"));
    const clearButton = form.querySelector("[data-clear-selection]");
    if (!help || !clearButton) return;

    let timer = null;
    let requestSequence = 0;

    const clearResults = () => results.replaceChildren();
    input.addEventListener("input", () => {
      selectedId.value = "";
      help.textContent = "Choose a result, or leave the search empty to clear the selection.";
      clearResults();
      window.clearTimeout(timer);
      const sequence = ++requestSequence;
      const query = input.value.trim();
      if (query.length < 2) return;

      timer = window.setTimeout(async () => {
        try {
          const endpoint = new URL(input.dataset.searchUrl, window.location.origin);
          endpoint.searchParams.set("q", query);
          const response = await fetch(endpoint, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
          });
          if (!response.ok) throw new Error(`Search failed (${response.status}).`);
          const data = await response.json();
          if (sequence !== requestSequence || input.value.trim() !== query) return;

          data.results.forEach((result) => {
            const item = document.createElement("li");
            const option = document.createElement("button");
            option.type = "button";
            option.textContent = result.label;
            option.addEventListener("click", () => {
              selectedId.value = String(result.id);
              input.value = result.label;
              help.textContent = `Selected: ${result.label}`;
              clearResults();
            });
            item.append(option);
            results.append(item);
          });
          if (!data.results.length) help.textContent = "No matches found.";
        } catch (error) {
          if (sequence !== requestSequence) return;
          help.textContent = error.message;
        }
      }, 200);
    });

    form.addEventListener("submit", (event) => {
      if (input.value.trim() && !selectedId.value) {
        event.preventDefault();
        help.textContent = "Select a search result before saving, or clear the search to remove the current selection.";
        input.focus();
      }
    });

    clearButton.addEventListener("click", () => {
      selectedId.value = "";
      input.value = "";
      help.textContent = "No selection. Saving will clear this setting.";
      clearResults();
      input.focus();
    });
  });
}

function initializeAdminSearch() {
  document.querySelectorAll("[data-admin-search-form]").forEach((form) => {
    const input = form.querySelector("[data-admin-search]");
    const selectedId = form.querySelector("[data-selected-id]");
    const results = form.querySelector("[data-search-results]");
    if (!input || !selectedId || !results) return;
    const help = document.getElementById(input.getAttribute("aria-describedby"));
    const clearButton = form.querySelector("[data-clear-selection]");
    if (!help || !clearButton) return;

    let timer = null;
    let requestSequence = 0;

    const clearResults = () => results.replaceChildren();
    input.addEventListener("input", () => {
      selectedId.value = "";
      help.textContent = "Choose a result, or leave the search empty to clear the selection.";
      clearResults();
      window.clearTimeout(timer);
      const sequence = ++requestSequence;
      const query = input.value.trim();
      if (query.length < 2) return;

      timer = window.setTimeout(async () => {
        try {
          const endpoint = new URL(input.dataset.searchUrl, window.location.origin);
          endpoint.searchParams.set("q", query);
          const response = await fetch(endpoint, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
          });
          if (!response.ok) throw new Error(`Search failed (${response.status}).`);
          const data = await response.json();
          if (sequence !== requestSequence || input.value.trim() !== query) return;

          data.results.forEach((result) => {
            const item = document.createElement("li");
            const option = document.createElement("button");
            option.type = "button";
            option.textContent = result.label;
            option.addEventListener("click", () => {
              selectedId.value = String(result.id);
              input.value = result.label;
              help.textContent = `Selected: ${result.label}`;
              clearResults();
            });
            item.append(option);
            results.append(item);
          });
          if (!data.results.length) help.textContent = "No matches found.";
        } catch (error) {
          if (sequence !== requestSequence) return;
          help.textContent = error.message;
        }
      }, 200);
    });

    form.addEventListener("submit", (event) => {
      if (input.value.trim() && !selectedId.value) {
        event.preventDefault();
        help.textContent = "Select a search result before saving, or clear the search to remove the current selection.";
        input.focus();
      }
    });

    clearButton.addEventListener("click", () => {
      selectedId.value = "";
      input.value = "";
      help.textContent = "No selection. Saving will clear this setting.";
      clearResults();
      input.focus();
    });
  });
}

function initializeLikeButtons() {
  document.querySelectorAll("form[action*='/like']").forEach((form) => {
    const button = form.querySelector("button[type='submit'].like");
    if (!button) return;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      button.disabled = true;

      try {
        const response = await fetch(form.action, {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
          },
          credentials: "same-origin",
          body: new URLSearchParams(new FormData(form)),
        });

        if (!response.ok) throw new Error(`Could not update like (${response.status}).`);
        const data = await response.json();

        // Update button state
        button.classList.toggle("is-liked", data.liked);
        button.setAttribute("aria-pressed", data.liked ? "true" : "false");

        // Update the heart icon and count
        const heartSpan = button.querySelector("span[aria-hidden='true']");
        if (heartSpan) {
          heartSpan.textContent = data.liked ? "♥" : "♡";
        }

        // Update the count text
        const countText = button.textContent.match(/\d+/);
        if (countText) {
          button.innerHTML = `<span aria-hidden="true">${data.liked ? "♥" : "♡"}</span> ${data.like_count}`;
          const sr = document.createElement("span");
          sr.className = "sr";
          sr.textContent = `${data.like_count} ${data.like_count === 1 ? "like" : "likes"}, ${data.liked ? "unlike" : "like this post"}`;
          button.append(sr);
        }

        // Update aria-label if present
        if (button.getAttribute("aria-label")) {
          const title = button.getAttribute("aria-label").match(/(?:Like|Unlike) (.*)/)?.[1] || "";
          button.setAttribute("aria-label", `${data.liked ? "Unlike" : "Like"} ${title}`);
        }
      } catch (error) {
        console.error("Error updating like:", error);
        // Re-enable button on error
      } finally {
        button.disabled = false;
      }
    });
  });
}

initializeColorControls();
initializeAvatarCrop();
initializeAdminCrossword();
initializeCrosswordSolver();
initializeAdminSearch();
initializeLikeButtons();
