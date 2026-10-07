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
    accent_color: "--preview-accent",
    surface_color: "--preview-surface",
    button_text_color: "--preview-button-text",
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

  // Typing direction: stays on "across" or "down" until the solver changes it
  // (click the active cell again, press Space, or click a clue).
  const cellByIndex = new Map(cells.map((cell) => [Number(cell.dataset.crosswordCell), cell]));
  const GRID_SIZE = 15;
  let direction = "across";

  // Neighbouring cell in a direction (step = 1 forward, -1 back); null at a
  // block or the grid edge, so typing never jumps out of the current word.
  const neighbour = (index, dir, step = 1) => {
    if (dir === "across") {
      const col = index % GRID_SIZE + step;
      if (col < 0 || col >= GRID_SIZE) return null;
      return cellByIndex.get(index + step) ?? null;
    }
    return cellByIndex.get(index + step * GRID_SIZE) ?? null;
  };
  const inWord = (index, dir) => Boolean(neighbour(index, dir, 1) || neighbour(index, dir, -1));
  const otherDirection = () => (direction === "across" ? "down" : "across");

  const wordIndexes = (index) => {
    let start = index;
    for (let prev = neighbour(start, direction, -1); prev;
      prev = neighbour(start, direction, -1)) {
      start = Number(prev.dataset.crosswordCell);
    }
    const indexes = [start];
    for (let next = neighbour(start, direction, 1); next;
      next = neighbour(indexes[indexes.length - 1], direction, 1)) {
      indexes.push(Number(next.dataset.crosswordCell));
    }
    return indexes;
  };
  const highlightWord = (index) => {
    document.querySelectorAll(".crossword-square.is-active-word")
      .forEach((square) => square.classList.remove("is-active-word"));
    if (index === null) return;
    wordIndexes(index).forEach((i) => {
      cellByIndex.get(i)?.closest(".crossword-square")?.classList.add("is-active-word");
    });
  };

  const setDirection = (dir, index) => {
    direction = dir;
    highlightWord(index ?? null);
  };

  cells.forEach((cell) => {
    const index = Number(cell.dataset.crosswordCell);
    let wasFocusedOnPress = false;

    cell.addEventListener("mousedown", () => {
      wasFocusedOnPress = document.activeElement === cell;
    });
    // Clicking the cell you are already on switches across <-> down.
    cell.addEventListener("click", () => {
      if (wasFocusedOnPress && inWord(index, otherDirection())) {
        setDirection(otherDirection(), index);
      }
      wasFocusedOnPress = false;
      // A click drops the caret, which would block typing over a filled square.
      // Only if focus is still here: typing may already have moved on.
      setTimeout(() => {
        if (document.activeElement === cell) cell.select();
      }, 0);
    });
    cell.addEventListener("focus", () => {
      // Keep the current direction unless this cell has no word that way.
      if (!inWord(index, direction) && inWord(index, otherDirection())) {
        direction = otherDirection();
      }
      highlightWord(index);
      cell.select();
    });
    cell.addEventListener("blur", () => highlightWord(null));

    cell.addEventListener("keydown", (event) => {
      if (event.key === " " && inWord(index, otherDirection())) {
        event.preventDefault();
        setDirection(otherDirection(), index);
      } else if (event.key === "Backspace" && !cell.value) {
        const previous = neighbour(index, direction, -1);
        if (previous) {
          event.preventDefault();
          previous.focus();
        }
      }
    });

    cell.addEventListener("input", () => {
      cell.value = normalizeCrosswordCell(cell.value);
      // Save to localStorage on each input
      const answers = {};
      cells.forEach((c) => {
        const i = Number(c.dataset.crosswordCell);
        if (c.value) answers[i] = c.value;
      });
      localStorage.setItem(crosswordKey, JSON.stringify(answers));

      if (!cell.value) return;
      const next = neighbour(index, direction, 1);
      if (next) next.focus();
    });
  });

  // Clicking a clue selects that word: right direction, first empty square.
  document.querySelectorAll("[data-crossword-entry]").forEach((entry) => {
    entry.addEventListener("click", () => {
      // data-row / data-col on clues are 0-based (unlike the squares' labels).
      const startIndex = Number(entry.dataset.row) * GRID_SIZE + Number(entry.dataset.col);
      const dir = entry.dataset.direction;
      direction = dir;
      const word = wordIndexes(startIndex).map((i) => cellByIndex.get(i));
      const target = word.find((c) => !c.value) ?? word[0];
      target?.focus();
      highlightWord(Number(target?.dataset.crosswordCell ?? startIndex));
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

function initializeBoknections() {
  const root = document.querySelector("[data-boknections]");
  if (!root) return;
  const status = root.querySelector("[data-bokn-status]");
  const savedMessage = sessionStorage.getItem("boknections-msg");
  sessionStorage.removeItem("boknections-msg");
  if (savedMessage && status) status.textContent = savedMessage;
  if (root.dataset.playable !== "true") return;

  const pool = root.querySelector("[data-bokn-pool]");
  const checkButton = root.querySelector("[data-bokn-check]");
  if (!pool || !checkButton || !status) return;
  const tiles = Array.from(root.querySelectorAll("[data-bokn-tile]"));
  const fields = Array.from(root.querySelectorAll("[data-bokn-field]"));
  const wildField = root.querySelector("[data-bokn-wild]");
  const slotsOf = (field) => Array.from(field.querySelectorAll("[data-bokn-slot]"));
  const tileIn = (container) => container.querySelector("[data-bokn-tile]");
  const storageKey = root.dataset.storageKey;
  let selected = null;
  let dragged = null;

  function arrangement() {
    return {
      groups: fields.map((field) => slotsOf(field).map((slot) => tileIn(slot)?.dataset.word)),
      wild: wildField ? tileIn(wildField)?.dataset.word ?? null : null,
    };
  }

  function checkable() {
    const current = arrangement();
    return { groups: current.groups.filter((group) => group.every(Boolean)), wild: current.wild };
  }

  function refresh() {
    const current = arrangement();
    checkButton.disabled = !current.groups.some((group) => group.every(Boolean)) && !current.wild;
    localStorage.setItem(storageKey, JSON.stringify({
      groups: current.groups.map((group) => group.filter(Boolean)),
      wild: current.wild,
    }));
  }

  function select(tile) {
    selected?.setAttribute("aria-pressed", "false");
    selected = tile;
    selected?.setAttribute("aria-pressed", "true");
  }

  function place(tile, target) {
    const origin = tile.parentElement;
    if (target === pool) {
      pool.append(tile);
    } else {
      const occupant = tileIn(target);
      if (occupant && occupant !== tile) origin.append(occupant);
      target.append(tile);
    }
    select(null);
    refresh();
  }

  tiles.forEach((tile) => {
    tile.setAttribute("aria-pressed", "false");
    tile.addEventListener("dragstart", (event) => {
      dragged = tile;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", tile.dataset.word);
    });
    tile.addEventListener("dragend", () => { dragged = null; });
    tile.addEventListener("click", (event) => {
      event.stopPropagation();
      if (!selected) select(tile);
      else if (selected === tile) select(null);
      else place(selected, tile.parentElement);
    });
  });

  const targets = [pool, ...fields.flatMap(slotsOf), ...(wildField ? slotsOf(wildField) : [])];
  targets.forEach((target) => {
    const isSlot = target !== pool;
    if (isSlot) {
      target.tabIndex = 0;
      target.setAttribute("role", "button");
      target.setAttribute("aria-label", "Empty box");
    }
    target.addEventListener("dragover", (event) => {
      event.preventDefault();
      target.classList.add("is-over");
    });
    target.addEventListener("dragleave", () => target.classList.remove("is-over"));
    target.addEventListener("drop", (event) => {
      event.preventDefault();
      target.classList.remove("is-over");
      if (dragged) place(dragged, target);
    });
    target.addEventListener("click", () => { if (selected) place(selected, target); });
    target.addEventListener("keydown", (event) => {
      if (event.target === target && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        if (selected) place(selected, target);
      }
    });
  });

  // Put words back where the player left them before the page reloaded.
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) ?? "null");
    if (saved) {
      const byWord = new Map(tiles.map((tile) => [tile.dataset.word, tile]));
      const take = (word, slot) => {
        const tile = byWord.get(word);
        if (!tile || !slot) return;
        byWord.delete(word);
        slot.append(tile);
      };
      const groups = (saved.groups ?? []).map((g) => g.filter((w) => byWord.has(w))).filter((g) => g.length);
      groups.slice(0, fields.length).forEach((group, index) => {
        group.forEach((word, position) => take(word, slotsOf(fields[index])[position]));
      });
      if (wildField && saved.wild) take(saved.wild, slotsOf(wildField)[0]);
    }
  } catch (error) {
    localStorage.removeItem(storageKey);
  }
  refresh();

  checkButton.addEventListener("click", async () => {
    checkButton.disabled = true;
    status.textContent = "Checking…";
    try {
      const response = await fetch(root.dataset.checkUrl, {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/x-www-form-urlencoded" },
        credentials: "same-origin",
        body: new URLSearchParams({
          csrf_token: root.dataset.csrf,
          placement: JSON.stringify(checkable()),
        }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error ?? `Could not check (${response.status}).`);
      if (result.solved || result.over) localStorage.removeItem(storageKey);
      sessionStorage.setItem("boknections-msg", result.correct
        ? `${result.correct} found! Attempts left: ${result.attempts_left}.`
        : `Nothing new this time. Attempts left: ${result.attempts_left}.`);
      window.location.reload();
    } catch (error) {
      status.textContent = error.message;
      refresh();
    }
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
initializeBoknections();
initializeAdminSearch();
initializeLikeButtons();