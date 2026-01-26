// Configuration
    let KIT_BASE_PATH = "downloads/";
    let CURRENT_KIT_FOLDER = ""; // Set dynamically
    let KIT_PATH = ""; // Set dynamically

    // State
    let kitStructure = null; // Changed from metadata
    let kits = [];
    let currentPart = null;
    let currentItem = null;
    let currentColor = null;
    let currentColorIndex = 0;
    let characterLayers = {};
    let imgVers = Date.now();

    // Multi-region focus management
    let activeFocusArea = "colors"; // 'parts', 'items', 'colors'
    let canvasWidth = 1436;
    let canvasHeight = 1902;

    // Canvas
    const canvas = document.getElementById("character-canvas");
    const ctx = canvas.getContext("2d");

    // Load Kits list
    async function loadKitsList() {
      try {
        const response = await fetch("/api/get_kits_list", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        const result = await response.json();

        if (result.success) {
          kits = result.kits;

          if (kits.length > 0) {
            // Auto-select the first kit
            const firstKit = kits[0];
            CURRENT_KIT_FOLDER = firstKit.folder;
            KIT_PATH = `${KIT_BASE_PATH}${CURRENT_KIT_FOLDER}/`;

          }

          const selector = document.getElementById("kit-selector");
          selector.innerHTML = "";

          kits.forEach((kit) => {
            const option = document.createElement("option");
            option.value = kit.folder;
            option.textContent = kit.name;
            if (kit.folder === CURRENT_KIT_FOLDER) option.selected = true;
            selector.appendChild(option);
          });

          loadKitStructure();
        } else {
          console.error("Error loading kits list:", result.message);
        }
      } catch (error) {
        console.error("Error loading kits list:", error);
      }
    }

    // Switch Kit
    function switchKit(folderName) {
      if (!folderName) return;

      CURRENT_KIT_FOLDER = folderName;
      KIT_PATH = `${KIT_BASE_PATH}${CURRENT_KIT_FOLDER}/`;


      // Clear current kit structure to trigger fresh load
      kitStructure = null;

      // Reset character UI
      resetCharacter();

      // Reload kit structure for new kit
      loadKitStructure();
    }

    // Load kit structure from folder API
    async function loadKitStructure(preserveSelection = false) {
      try {
        const response = await fetch("/api/get_kit_structure", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kit: CURRENT_KIT_FOLDER }),
        });
        const result = await response.json();
        if (result.success) {
          kitStructure = result.parts;
          canvasWidth = result.canvas_width || 1436;
          canvasHeight = result.canvas_height || 1902;

          // Update main canvas aspect ratio (Base width 400px)
          const displayWidth = 400;
          const aspectRatio = canvasHeight / canvasWidth;
          canvas.width = displayWidth;
          canvas.height = displayWidth * aspectRatio;
          canvas.style.height = displayWidth * aspectRatio + "px";

          // Warning about duplicate X and gaps
          const warningBox = document.getElementById("structure-warnings");
          let warningHtml = "";

          if (result.duplicates && result.duplicates.length > 0) {
            warningHtml += `
                            <strong>⚠️ CẢNH BÁO TRÙNG THỨ TỰ (X):</strong><br>
                            Các folder sau đây đang dùng chung số X (sẽ bị lỗi hiển thị đè nhau):<br>
                            ${result.duplicates.join("<br>")}<br><br>
                        `;
          }

          if (result.missing_x && result.missing_x.length > 0) {
            warningHtml += `
                            <strong>⚠️ THIẾU CHỈ SỐ X (Thứ tự layer):</strong><br>
                            Thiếu các số X sau: ${result.missing_x.join(", ")}<br>
                            (Hãy kiểm tra lại việc đặt tên folder X-Y)<br><br>
                        `;
          }

          if (result.missing_y && result.missing_y.length > 0) {
            warningHtml += `
                            <strong>⚠️ THIẾU CHỈ SỐ Y (Vị trí menu):</strong><br>
                            Thiếu các số Y sau: ${result.missing_y.join(", ")}<br>
                            (Hãy kiểm tra lại việc đặt tên folder X-Y)
                        `;
          }

          if (warningHtml) {
            warningBox.style.display = "block";
            warningBox.innerHTML = warningHtml;
          } else {
            warningBox.style.display = "none";
            warningBox.innerHTML = "";
          }

          // Handle separated layers info
          const sepInfo = document.getElementById("separated-layers-info");
          const sepList = document.getElementById("separated-folders-list");
          if (result.has_separated_layers) {
            sepInfo.style.display = "block";
            sepList.textContent = result.separated_folders.join(", ");
          } else {
            sepInfo.style.display = "none";
          }

          imgVers = Date.now(); // Update version to bypass cache
          if (preserveSelection) {
            // If preserving selection, update the existing characterLayers with new metadata
            // This handles renaming (folderName updates) and sorting (sortOrder updates)
            Object.keys(characterLayers).forEach((idx) => {
              const partIndex = parseInt(idx);
              if (kitStructure[partIndex]) {
                const newPart = kitStructure[partIndex];
                const layer = characterLayers[partIndex];

                // Update folder name
                layer.folderName = newPart.folder;

                // Update sortOrder based on new X
                // sortOrder = X * 1000 + partIndex
                layer.sortOrder = newPart.x * 1000 + partIndex;
              } else {
                // Part might have been deleted?
                delete characterLayers[partIndex];
              }
            });
          }

          initializeApp(preserveSelection);
        } else {
          console.error("Error loading kit structure:", result.message);
        }
      } catch (error) {
        console.error("Error loading kit structure:", error);
      }
    }

    // Initialize app
    function initializeApp(preserveSelection = false) {
      if (!kitStructure || kitStructure.length === 0) {
        console.error("No kit structure loaded");
        return;
      }

      const savedPartIndex = currentPart ? currentPart.index : 0;
      const savedColorIdx = currentColorIndex;

      const navContainer = document.getElementById("nav-icons");
      const countLayer = document.getElementById("count-layer");
      navContainer.innerHTML = "";
      countLayer.innerHTML = "";

      kitStructure.forEach((part, index) => {
        const navIcon = document.createElement("div");
        navIcon.className = "nav-icon";
        navIcon.dataset.partIndex = index;
        navIcon.dataset.folderName = part.folder;
        if (part.is_separated) {
          navIcon.classList.add("separated");
          navIcon.title = "Bộ phận này có layer tách";
        }

        const img = document.createElement("img");
        img.src = `${KIT_PATH}${part.folder}/nav.png?v=${imgVers}`;
        img.alt = part.folder;
        img.onerror = () => (img.style.display = "none");

        const label = document.createElement("div");
        label.className = "label";
        label.textContent = part.folder;

        navIcon.appendChild(img);
        navIcon.appendChild(label);
        navIcon.onclick = () => selectPart(index, part);

        navContainer.appendChild(navIcon);
        countLayer.textContent = `(${kitStructure.length})`;

        // If not preserving or if we lost the selection, reset to default if needed
        if (!characterLayers[index] && part.items_count > 0) {
          const firstColor =
            part.colors.length > 0 ? part.colors[0] : "default";
          internalSelectItem(index, 1, part, firstColor, 0);
        }
      });

      // Re-render canvas but keep layers
      renderCharacter();

      // Reselect the part to refresh item grid
      const targetIdx = preserveSelection ? savedPartIndex : 0;
      if (kitStructure[targetIdx]) {
        selectPart(targetIdx, kitStructure[targetIdx]);
        // If we had a specific color, try to keep it
        if (
          preserveSelection &&
          kitStructure[targetIdx].colors.length > savedColorIdx
        ) {
          selectColor(
            kitStructure[targetIdx].colors[savedColorIdx],
            savedColorIdx,
          );
        }
      }
      updateFocusUI(); // Initial focus UI update
    }

    // Internal select item for auto-init
    async function internalSelectItem(
      partIndex,
      itemNumber,
      part,
      colorCode,
      colorIndex,
    ) {
      const sortOrder = part.x * 1000 + partIndex;

      characterLayers[partIndex] = {
        folderName: part.folder,
        color: colorCode,
        colorIndex: colorIndex,
        itemNumber: itemNumber,
        sortOrder: sortOrder,
      };
      renderCharacter();
    }

    // Select part
    function selectPart(index, part) {
      currentPart = { index, part };

      // Update active nav icon
      document.querySelectorAll(".nav-icon").forEach((icon) => {
        icon.classList.remove("active");
      });
      document
        .querySelector(`[data-part-index="${index}"]`)
        .classList.add("active");

      // Update part name
      // Update part name with Rename button
      const nameContainer = document.getElementById("current-part-name");

      nameContainer.innerHTML = `
                ${part.folder}
                <div class="btn-group" style="display:inline-flex; gap:5px; margin-left:8px;">
                     <button class="btn" style="padding:2px 6px; font-size:12px; background:#f1c40f;" onclick="renamePartFolder('${part.folder}')" title="Đổi tên thư mục này">✎</button>
                     <button class="btn" style="padding:2px 6px; font-size:12px; background:#3498db;" onclick="showFolderFiles()" title="Xem file trong folder">📂</button>
                </div>
            `;

      document.getElementById("delete-part-btn").style.display = "block";

      // Show merge button only for separated layers
      const mergeBtn = document.getElementById("merge-part-btn");
      if (part.is_separated) {
        mergeBtn.style.display = "block";
      } else {
        mergeBtn.style.display = "none";
      }

      // Show flatten button only if has color folders
      const flattenBtn = document.getElementById("flatten-colors-btn");
      if (part.has_colors) {
        flattenBtn.style.display = "block";
      } else {
        flattenBtn.style.display = "none";
      }

      // Don't auto-select item - respect current selection or None
      // If this part has a layer, it will be restored by loadItems
      currentItem = characterLayers[index]
        ? characterLayers[index].itemNumber
        : null;

      // Load items
      loadItems(part);

      // Load colors
      loadColors(part);
    }

    // Load items for current part
    async function loadItems(part) {
      const itemGrid = document.getElementById("item-grid");
      itemGrid.innerHTML =
        '<div class="loading"><div class="spinner"></div>Đang tải...</div>';

      itemGrid.innerHTML = "";

      // Add "None" option
      const noneDiv = document.createElement("div");
      noneDiv.className = "item-option item-none";
      if (characterLayers[currentPart.index] === undefined) {
        noneDiv.classList.add("active");
      }
      noneDiv.onclick = () => selectItem(-1);
      itemGrid.appendChild(noneDiv);

      // Generate items from 1 to items_count
      for (let itemNum = 1; itemNum <= part.items_count; itemNum++) {
        const itemDiv = document.createElement("div");
        itemDiv.className = "item-option";
        itemDiv.dataset.itemNumber = itemNum;

        if (
          characterLayers[currentPart.index] &&
          characterLayers[currentPart.index].itemNumber === itemNum
        ) {
          itemDiv.classList.add("active");
        }

        const img = document.createElement("img");
        const imagePath = `${KIT_PATH}${part.folder}/thumb_${itemNum}.png?v=${imgVers}`;
        img.src = imagePath;
        img.onerror = () => {
          console.log(`Thumbnail not found: ${imagePath}`);
          itemDiv.style.display = "none";
        };

        itemDiv.appendChild(img);

        // Add layer count badge if > 1
        if (part.item_layer_counts && part.item_layer_counts[itemNum]) {
          const layerCount = part.item_layer_counts[itemNum];
          if (layerCount > 1) {
            const badge = document.createElement("div");
            badge.className = "layer-count-badge";
            badge.textContent = layerCount;
            badge.title = `Click để xem ${layerCount} layers`;
            badge.style.cursor = "pointer";
            badge.onclick = (e) => showLayerDetails(part.folder, itemNum, e);
            itemDiv.appendChild(badge);
          }
        }

        itemDiv.onclick = () => selectItem(itemNum);

        itemGrid.appendChild(itemDiv);
      }
    }

    // Helper to extract hex color from folder name
    function getColorHex(colorFolderName) {
      if (colorFolderName === "default") return "CCCCCC";
      // Extract hex from folder name (e.g., "FF5733" or "FF5733_2")
      const match = colorFolderName.match(/^([0-9A-Fa-f]{6})/);
      return match ? match[1] : "CCCCCC";
    }

    // Load colors
    async function loadColors(part) {
      const colorGrid = document.getElementById("color-grid");
      const editFolderColor = document.getElementById("edit-folder-color");

      // Add Header with Rename Button
      // Doing this by modifying the container or pre-pending to grid?
      // The existing code has <div id="color-grid"></div> which only contains circles.
      // But there is a header "Chọn màu" somewhere.
      // Let's modify innerHTML completely or rely on existing header.
      // Looking at user code, there is no header inside loadColors. Header is external.
      // I will inject the button INTO the existing UI structure if possible, but I don't see the header in the snippet.
      // I'll append a control bar BEFORE the grid inside this function or check if I can target the container.
      // Actually, the "Chọn màu" header is static HTML probably.
      // Let's look at where the header is.

      colorGrid.innerHTML = "";
      editFolderColor.innerHTML = "";
      // Insert Rename Button at the start of the grid or separate row
      // User requested: "thêm 1 nút thay đổi tên folder màu cho tôi ở đây"
      const controlsDiv = document.createElement("div");
      controlsDiv.style.width = "100%";
      controlsDiv.style.marginBottom = "10px";
      controlsDiv.style.display = "flex";
      controlsDiv.style.justifyContent = "space-between";
      controlsDiv.style.alignItems = "center";

      const colorCount = part.colors.length > 0 ? part.colors.length : 1; // 1 if only default

      controlsDiv.innerHTML = `
                <span style="font-weight:bold;">Màu sắc (${colorCount})</span>
                <div style="display: flex; gap: 5px;">
                    <button id="rename-color-btn" onclick="renameCurrentColor()" style="display:none; padding: 5px 10px; font-size: 11px; cursor: pointer; background: #3498db; color: white; border: none; border-radius: 4px;">Đổi tên folder</button>
                    <button id="delete-colors-btn" onclick="confirmDeleteColors()" style="padding: 5px 10px; font-size: 11px; cursor: pointer; background: #e74c3c; color: white; border: none; border-radius: 4px;">Xóa màu đã chọn (F)</button>
                </div>
            `;
      editFolderColor.appendChild(controlsDiv);

      const colors = part.colors.length > 0 ? part.colors : ["default"];

      colors.forEach((colorFolder, index) => {
        const colorDiv = document.createElement("div");
        colorDiv.className = "color-option";
        colorDiv.dataset.colorIndex = index;
        colorDiv.dataset.colorFolder = colorFolder;

        const hexColor = getColorHex(colorFolder);
        colorDiv.style.background = `#${hexColor}`;
        colorDiv.title =
          colorFolder === "default" ? "Màu mặc định" : `#${hexColor}`;

        if (colorFolder === "default") {
          colorDiv.classList.add("default-color");
        }

        colorDiv.onclick = () => selectColor(colorFolder, index);

        if (colorFolder !== "default") {
          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.className = "color-checkbox";
          checkbox.name = "color-to-delete";
          checkbox.value = colorFolder;
          checkbox.onclick = (e) => e.stopPropagation();
          checkbox.title = "Chọn để xóa (D)";
          colorDiv.appendChild(checkbox);
        }

        colorGrid.appendChild(colorDiv);

      });

      // Show/Hide Delete Button
      document.getElementById("delete-colors-btn").style.display = (part.colors.length > 0) ? "block" : "none";

      // Select first color by default
      if (colors.length > 0) {
        selectColor(colors[0], 0);
      }

    }

    // Select item
    function selectItem(itemNumber) {
      currentItem = itemNumber;

      document.querySelectorAll(".item-option").forEach((item) => {
        item.classList.remove("active");
      });

      if (itemNumber === -1) {
        // "None" selected
        document.querySelector(".item-none")?.classList.add("active");
        delete characterLayers[currentPart.index];
        renderCharacter();
        return;
      }

      document
        .querySelector(`[data-item-number="${itemNumber}"]`)
        ?.classList.add("active");

      // Auto-select first color if not already selected
      if (!currentColor) {
        const firstColorOption = document.querySelector(".color-option");
        if (firstColorOption) {
          const firstColorFolder = firstColorOption.dataset.colorFolder;
          selectColor(firstColorFolder, 0);
        }
      } else {
        // Update with current color
        updateCharacter();
      }

      // Show layer details button if this item has multiple layers
      const layerDetailsBtn = document.getElementById("layer-details-btn");
      if (
        currentPart &&
        currentPart.part.item_layer_counts &&
        currentPart.part.item_layer_counts[itemNumber] > 1
      ) {
        layerDetailsBtn.style.display = "block";
      } else {
        layerDetailsBtn.style.display = "none";
      }
    }

    // Select color
    function selectColor(colorFolder, colorIndex) {
      currentColor = colorFolder;
      currentColorIndex = colorIndex !== undefined ? colorIndex : 0;

      document.querySelectorAll(".color-option").forEach((color) => {
        color.classList.remove("active");
      });

      const option = document.querySelector(
        `[data-color-folder="${colorFolder}"]`,
      );
      if (option) option.classList.add("active");

      // Handle Rename Button Visibility
      const renameBtn = document.getElementById("rename-color-btn");
      if (renameBtn) {
        if (colorFolder && colorFolder !== "default") {
          renameBtn.style.display = "block";
          renameBtn.title = `Đổi tên folder: ${colorFolder}`;
        } else {
          renameBtn.style.display = "none";
        }
      }

      updateCharacter();
    }

    // Rename Current Color Logic
    async function renameCurrentColor() {
      if (!currentPart || !currentColor || currentColor === "default") return;

      const newName = prompt(
        `Nhập tên mới cho folder màu "${currentColor}":`,
        currentColor,
      );
      if (!newName || newName === currentColor) return;

      // Basic validation
      // if (!/^[a-zA-Z0-9_-]+$/.test(newName)) // Loose validation

      try {
        const response = await fetch("/api/rename_color_folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kit: CURRENT_KIT_FOLDER,
            part_folder: currentPart.part.folder,
            old_color: currentColor,
            new_color: newName,
          }),
        });

        const result = await response.json();
        if (result.success) {
          // alert('Đổi tên thành công!');
          // We need to refresh the part structure to reflect the new folder name
          // Simplest way: Reload kit structure, find current part, re-render colors.
          // A optimization: Manually update local data.
          const index = currentPart.part.colors.indexOf(currentColor);
          if (index !== -1) {
            currentPart.part.colors[index] = newName;
          }

          // Also update characterLayers if using old color name
          if (
            characterLayers[currentPart.index] &&
            characterLayers[currentPart.index].color === currentColor
          ) {
            characterLayers[currentPart.index].color = newName;
          }

          // Re-load Colors UI
          loadColors(currentPart.part);
          // Select new color
          setTimeout(() => selectColor(newName, index), 50);

          // Re-render character to update image paths
          renderCharacter();
        } else {
          alert("Lỗi: " + result.message);
        }
      } catch (e) {
        alert("Lỗi server: " + e);
      }
    }

    async function confirmDeleteColors() {
      const checkboxes = document.querySelectorAll('.color-checkbox:checked');
      const colorsToDelete = Array.from(checkboxes).map(cb => cb.value);

      if (colorsToDelete.length === 0) {
        alert("Vui lòng tích chọn ít nhất một màu (ô vuông nhỏ trên vòng tròn màu) để xóa.");
        return;
      }

      if (!confirm(`Bạn có chắc chắn muốn xóa ${colorsToDelete.length} folder màu sắc đã chọn trực tiếp khỏi bộ phận này? Thao tác này không thể hoàn tác.`)) {
        return;
      }

      showLoading(true, "Đang xóa các folder màu sắc...");

      try {
        const response = await fetch("/api/delete_color_folders", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kit: CURRENT_KIT_FOLDER,
            part_folder: currentPart.part.folder,
            colors: colorsToDelete
          })
        });

        const result = await response.json();
        if (result.success) {
          // Update local data
          currentPart.part.colors = currentPart.part.colors.filter(c => !colorsToDelete.includes(c));

          // If current color was deleted, switch to default
          if (colorsToDelete.includes(currentColor)) {
            currentColor = "default";
            currentColorIndex = 0;
          }

          loadColors(currentPart.part);
          renderCharacter();
          // alert("Đã xóa màu thành công!");
        } else {
          alert("Lỗi: " + result.message);
        }
      } catch (e) {
        alert("Lỗi kết nối: " + e);
      } finally {
        hideLoading();
      }
    }




    // Update character
    async function updateCharacter() {
      if (!currentPart || currentItem === null || !currentColor) return;

      const part = currentPart.part;
      const sortOrder = part.x * 1000 + currentPart.index;

      characterLayers[currentPart.index] = {
        folderName: part.folder,
        color: currentColor,
        colorIndex: currentColorIndex,
        itemNumber: currentItem,
        sortOrder: sortOrder,
      };

      renderCharacter();
    }

    // Render character
    // Render character
    async function renderCharacter() {
      // Sort by sortOrder (X value determines layer order)
      const sortedLayers = Object.values(characterLayers).sort(
        (a, b) => a.sortOrder - b.sortOrder,
      );

      // Pre-load all images in parallel
      const loadPromises = sortedLayers.map(async (layer) => {
        const { folderName, color, itemNumber } = layer;
        let imagePath;
        if (color === "default" || !color) {
          imagePath = `${KIT_PATH}${folderName}/${itemNumber}.png?v=${imgVers}`;
        } else {
          imagePath = `${KIT_PATH}${folderName}/${color}/${itemNumber}.png?v=${imgVers}`;
        }

        try {
          const img = await loadImage(imagePath);
          return img;
        } catch (error) {
          console.error(`Failed to load: ${imagePath}`);
          return null;
        }
      });

      // Wait for all to load
      const images = await Promise.all(loadPromises);

      // Clear and draw all at once
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      images.forEach((img) => {
        if (img) {
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        }
      });
    }

    // Load image helper
    function loadImage(src) {
      return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = src;
      });
    }

    // Export character
    function exportCharacter() {
      const link = document.createElement("a");
      link.download = "my-character.png";
      link.href = canvas.toDataURL();
      link.click();
    }

    // Reset character
    function resetCharacter() {
      characterLayers = {};
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      currentPart = null;
      currentItem = null;
      currentColor = null;

      document
        .querySelectorAll(".nav-icon, .item-option, .color-option")
        .forEach((el) => {
          el.classList.remove("active");
        });

      document.getElementById("item-grid").innerHTML = "";
      document.getElementById("color-grid").innerHTML = "";
      document.getElementById("current-part-name").textContent =
        "Chọn một bộ phận";
    }

    // Randomize character
    async function randomizeCharacter() {
      if (!kitStructure || kitStructure.length === 0) return;

      // Randomize each part
      for (let partIndex = 0; partIndex < kitStructure.length; partIndex++) {
        const part = kitStructure[partIndex];
        if (part.items_count === 0) continue;

        // 85% chance to select an item, 15% chance to skip (None)
        if (Math.random() < 0.15) {
          delete characterLayers[partIndex];
          continue;
        }

        const itemNumber = Math.floor(Math.random() * part.items_count) + 1;
        const colors = part.colors.length > 0 ? part.colors : ["default"];
        const colorIdx = Math.floor(Math.random() * colors.length);
        const selectedColor = colors[colorIdx];

        const sortOrder = part.x * 1000 + partIndex;

        characterLayers[partIndex] = {
          folderName: part.folder,
          color: selectedColor,
          colorIndex: colorIdx,
          itemNumber: itemNumber,
          sortOrder: sortOrder,
        };
      }

      renderCharacter();

      // Refresh UI if a part is currently selected
      if (currentPart) {
        selectPart(currentPart.index, currentPart.part);
      }
    }

    // Reset all layers (select None for all parts)
    function resetAllLayers() {
      characterLayers = {};
      renderCharacter();

      // Update UI to show all parts as "None" selected
      document.querySelectorAll(".item-option").forEach((item) => {
        item.classList.remove("active");
      });
      document.querySelectorAll(".item-none").forEach((none) => {
        none.classList.add("active");
      });
    }

    async function downloadZip() {
      if (!CURRENT_KIT_FOLDER) {
        alert("Vui lòng chọn một bộ sưu tập trước!");
        return;
      }

      if (
        !confirm(
          `Bạn muốn tải xuống "Data ZIP" của "${CURRENT_KIT_FOLDER}"?\n\nLưu ý: Quá trình nén có thể mất vài chục giây tùy dung lượng.`
          ,
        )
      )
        return;

      try {
        // Find the button to show loading state
        const btn = document.querySelector('button[onclick="downloadZip()"]');
        const originalText = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang nén...';

        // We use window.location directly because fetch() will timeout on large/slow zip generation
        // The browser will handle the long-running download automatically.
        window.location.href = `/api/zip_kit?kit=${encodeURIComponent(CURRENT_KIT_FOLDER)}`;

        // We keep the button disabled for a bit to prevent multiple clicks
        setTimeout(() => {
          btn.disabled = false;
          btn.innerHTML = originalText;
        }, 10000);
      } catch (error) {
        alert("Lỗi khi bắt đầu tải xuống.");
        console.error(error);
      }
    }

    // Layer details modal functions
    async function showLayerDetails(folderName, itemNumber, event) {
      event.stopPropagation(); // Prevent item selection

      const modal = document.getElementById("layer-details-modal");
      const content = document.getElementById("layer-details-content");

      modal.style.display = "flex";
      content.innerHTML =
        '<div class="loading"><div class="spinner"></div>Đang tải...</div>';

      try {
        const response = await fetch("/api/get_item_layers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kit: CURRENT_KIT_FOLDER,
            folder: folderName,
            item_number: itemNumber,
          }),
        });

        const result = await response.json();

        if (result.success) {
          let html = `
                        <h3 style="margin-bottom: 15px;">Item #${itemNumber} - Tổng ${result.total_count} layer(s)</h3>
                        <div style="display: grid; gap: 15px;">
                    `;

          result.layers.forEach((layer, idx) => {
            const typeLabel =
              layer.type === "main" ? "🎨 Layer chính" : "✨ Layer phụ";
            const imgUrl = `https://img2.neka.cc/${layer.blob}`;

            html += `
                            <div style="border: 1px solid #ddd; border-radius: 8px; padding: 15px; background: #f9f9f9;">
                                <div style="display: flex; gap: 15px; align-items: start;">
                                    <img src="${imgUrl}" style="width: 100px; height: 100px; object-fit: contain; border: 1px solid #ccc; background: white; border-radius: 4px;">
                                    <div style="flex: 1;">
                                        <div style="font-weight: bold; margin-bottom: 8px;">${typeLabel} #${idx + 1}</div>
                                        <div style="font-size: 12px; color: #666; line-height: 1.6;">
                                            <div><strong>Blob ID:</strong> <code style="background: #e0e0e0; padding: 2px 4px; border-radius: 3px;">${layer.blob}</code></div>
                                            <div><strong>Vị trí:</strong> x=${layer.x}, y=${layer.y}</div>
                                            <div><strong>Kích thước:</strong> ${layer.w}×${layer.h}px</div>
                                            ${layer.layer_id ? `<div><strong>Toning ID:</strong> <code style="background: #e0e0e0; padding: 2px 4px; border-radius: 3px;">${layer.layer_id}</code></div>` : ""}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;
          });

          html += "</div>";
          content.innerHTML = html;
        } else {
          content.innerHTML = `<div style="color: red;">Lỗi: ${result.message}</div>`;
        }
      } catch (error) {
        content.innerHTML = `<div style="color: red;">Lỗi kết nối: ${error.message}</div>`;
      }
    }

    function closeLayerDetailsModal() {
      document.getElementById("layer-details-modal").style.display = "none";
    }

    function showCurrentItemLayers() {
      if (!currentPart || !currentItem || currentItem === -1) {
        alert("Vui lòng chọn một item trước!");
        return;
      }
      showLayerDetails(currentPart.part.folder, currentItem, {
        stopPropagation: () => { },
      });
    }

    // Show folder files debug modal
    async function showFolderFiles() {
      if (!currentPart) return;

      const modal = document.getElementById("file-debug-modal");
      const grid = document.getElementById("file-debug-grid");
      const subtitle = document.getElementById("file-debug-subtitle");

      modal.style.display = "flex";
      grid.innerHTML = "";
      subtitle.textContent = `Đang tải danh sách file cho part: ${currentPart.part.name} (${currentPart.part.folder})...`;

      try {
        // Determine color
        // Let's try to query the active color button in the UI
        const activeColorBtn = document.querySelector(".color-btn.active");
        let colorParam = activeColorBtn ? activeColorBtn.dataset.color : null;
        // Fix: Check if color param is actually valid (not undefined/null string due to dataset issue)
        // The dataset attribute is data-color-folder in loadColors function
        const activeColorOption = document.querySelector(
          ".color-option.active",
        );
        if (activeColorOption) {
          colorParam = activeColorOption.dataset.colorFolder;
        }

        const params = new URLSearchParams({
          kit: CURRENT_KIT_FOLDER,
          folder: currentPart.part.folder,
        });
        if (colorParam) params.append("color", colorParam);

        const response = await fetch(
          `/api/debug_folder_files?${params.toString()}`,
        );
        const result = await response.json();

        if (result.success) {
          subtitle.textContent = `Folder: ${currentPart.part.folder} ${colorParam ? "/ " + colorParam : ""} (Tổng: ${result.files.length} files)`;

          if (result.files.length === 0) {
            grid.innerHTML =
              '<p style="grid-column: 1/-1; text-align: center; color: #888;">Thư mục trống</p>';
            return;
          }

          // Group files by Item ID (e.g. "1") or "nav"
          const groups = {}; // { '1': { main: file, thumb: file }, 'nav': { main: file } }
          const others = [];

          result.files.forEach((file) => {
            // Check for Main Image: "1.png"
            if (file.name.match(/^\d+\.png$/)) {
              const id = file.name.split(".")[0];
              if (!groups[id]) groups[id] = {};
              groups[id].main = file;
            }
            // Check for Thumb Image: "thumb_1.png"
            else if (file.name.match(/^thumb_\d+\.png$/)) {
              const id = file.name.split(".")[0].replace("thumb_", "");
              if (!groups[id]) groups[id] = {};
              groups[id].thumb = file;
            }
            // Check for nav.png
            else if (file.name === "nav.png") {
              if (!groups["nav"]) groups["nav"] = {};
              groups["nav"].main = file;
            } else {
              others.push(file);
            }
          });

          // Clear grid but set up layout
          grid.style.display = "block";
          grid.innerHTML = `
                        <div style="display: flex; gap: 20px; align-items: flex-start;">
                            <div id="debug-main-list" style="flex: 10; display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 15px;"></div>
                            <div id="debug-sidebar" style="flex: 2; display: flex; flex-direction: column; gap: 15px; border-left: 1px solid #444; padding-left: 20px;"></div>
                        </div>
                    `;

          const mainList = document.getElementById("debug-main-list");
          const sidebar = document.getElementById("debug-sidebar");
          const timestamp = new Date().getTime();

          // Render Groups (Sorted by ID number)
          const sortedIds = Object.keys(groups).sort((a, b) => {
            if (a === "nav") return -1;
            if (b === "nav") return 1;
            return parseInt(a) - parseInt(b);
          });

          sortedIds.forEach((id) => {
            const group = groups[id];

            // Special handling for NAV -> Move to Sidebar
            // Special handling for NAV -> Move to Sidebar
            if (id === "nav") {
              const navContainer = document.createElement("div");
              navContainer.className = "file-debug-group";
              navContainer.style.cssText =
                "background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; display: flex; flex-direction: column; align-items: center; gap: 5px; width: 100%;";

              navContainer.innerHTML += `
                                <div style="display:flex; justify-content:space-between; width:100%; align-items:center; margin-bottom:5px;">
                                    <div style="font-weight:bold; color:#aaa;">NAV ICON</div>
                                    <button onclick="document.getElementById('nav-file-input').click()" style="padding:2px 8px; font-size:11px; cursor:pointer; background: #3498db; color:white; border:none; border-radius:3px;" title="Upload ảnh mới">⬆️ Upload</button>
                                </div>
                                <input type="file" id="nav-file-input" hidden accept="image/*" onchange="uploadNavFile(this)">
                             `;

              if (group.main) {
                navContainer.innerHTML += `
                                    <div class="file-debug-slot" title="${group.main.name}" style="position:relative; width:100%; display:flex; flex-direction:column; align-items:center;">
                                        <img src="${group.main.url}?v=${timestamp}" style="width: 100%; height: auto; object-fit: contain; background:rgba(255,255,255,0.1); border-radius:4px;">
                                        <div style="margin-top:5px;">${group.main.name}</div>
                                        <div style="margin-top:8px; display:flex; justify-content:center; width:100%;">
                                            <button onclick="deleteFile('${group.main.name}')" style="padding:4px 12px; background:#c0392b; color:white; border:none; border-radius:4px; cursor:pointer; font-size:12px;"> Xóa</button>
                                        </div>
                                    </div>
                                 `;
              } else {
                navContainer.innerHTML += `<div style="padding:20px; color:#666; text-align:center; border:1px dashed #444; width:100%; border-radius:4px;">Chưa có ảnh</div>`;
              }

              if (group.thumb) {
                navContainer.innerHTML += `
                                    <div style="color:#666; font-size:10px; margin-top:5px;">⬇️ Thumb</div>
                                    <div class="file-debug-slot" title="${group.thumb.name}">
                                        <img src="${group.thumb.url}?v=${timestamp}" style="width: 50px; height: 50px; object-fit: contain;">
                                    </div>
                                 `;
              }

              sidebar.appendChild(navContainer);
              return;
            }

            // REGULAR ITEMS -> Horizontal Layout (Row)
            const container = document.createElement("div");
            container.className = "file-debug-group";
            container.dataset.id = id; // Identify the group
            // Changed flex-direction to row for side-by-side
            container.style.cssText =
              "background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; display: flex; flex-direction: row; align-items: center; justify-content: space-around; gap: 10px;";

            // Main Slot
            if (group.main) {
              container.innerHTML += `
                                <div class="file-debug-slot main-slot" title="${group.main.name}" 
                                     draggable="true" ondragstart="handleDragStart(event, '${group.main ? group.main.name : ""}')"
                                     style="flex:1; display:flex; flex-direction:column; align-items:center; cursor:grab;">
                                    <img src="${group.main.url}?v=${timestamp}" style="width: 100%; height: 80px; object-fit: contain; pointer-events: none;">
                                    <span>${group.main.name}</span>
                                </div>
                             `;
            } else {
              container.innerHTML += `<div class="file-debug-slot main-slot" style="flex:1; opacity:0.5; text-align:center;">No Main</div>`;
            }

            // Arrow (Right)
            container.innerHTML += `<div style="color:#666; font-size:14px;">➡️</div>`;

            // Thumb Slot
            if (group.thumb) {
              const thumbId = `thumb-${id}`;
              const thumbName = group.thumb.name; // e.g., thumb_1.png

              // Draggable Thumb Container
              container.innerHTML += `
                                <div class="file-debug-slot thumb-slot" title="${thumbName}" 
                                     draggable="true" ondragstart="handleDragStart(event, '${group.main ? group.main.name : thumbName}')"
                                     style="flex:1; display:flex; flex-direction:column; align-items:center; position:relative;">
                                    <img src="${group.thumb.url}?v=${timestamp}" style="width: 100%; height: 80px; object-fit: contain;">
                                    <span>${thumbName}</span>
                                    
                                    <!-- Controls -->
                                    <div style="margin-top:5px; display:flex; gap:5px;">
                                        <button onclick="renameFile('${thumbName}')" title="Đổi tên" style="cursor:pointer; border:none; background:#f39c12; color:white; border-radius:3px; padding:2px 5px;">✏️</button>
                                        <button onclick="deleteFile('${thumbName}')" title="Xóa" style="cursor:pointer; border:none; background:#c0392b; color:white; border-radius:3px; padding:2px 5px;">🗑️</button>
                                    </div>
                                </div>
                             `;
            } else {
              // Missing Thumb -> Create Button AND Drop Zone
              const targetName = `thumb_${id}.png`;

              // Drop Zone Container
              container.innerHTML += `
                                <div class="file-debug-slot thumb-slot" style="flex:1; display:flex; flex-direction:column; justify-content:center; align-items:center; height:80px; border: 2px dashed #444;"
                                     ondragover="handleDragOver(event)" 
                                     ondrop="handleDrop(event, '${targetName}')">
                                     
                                    <button onclick="createThumbnail('${group.main ? group.main.name : ""}', '${targetName}')" 
                                            style="background: #27ae60; border: none; color: white; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 11px;">
                                        + Tạo Thumb
                                    </button>
                                    <span style="color:#e67e22; font-size:10px; margin-top:5px;">Kéo thả ảnh vào đây</span>
                                </div>
                            `;

              // Prevent click propagation for the button in the container
              // Wait, querySelector is safer after append
            }

            mainList.appendChild(container);

            // Re-bind click event for the Create Thumb button if it was added
            if (!group.thumb) {
              const lastDiv = container.querySelector(".thumb-slot");
              if (lastDiv) {
                lastDiv.addEventListener("click", (e) => {
                  if (e.target.tagName !== "BUTTON") return;
                });
              }
            }
          });

          // Render Others (Append to Main List, NOT grid)
          others.forEach((file) => {
            const itemDiv = document.createElement("div");
            itemDiv.className = "file-debug-item";
            itemDiv.style.cssText =
              "background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; display: flex; flex-direction: column; align-items: center;";
            itemDiv.innerHTML = `
                            <img src="${file.url}?v=${timestamp}" style="width: 100%; height: 100px; object-fit: contain;">
                            <span>${file.name}</span>
                        `;
            mainList.appendChild(itemDiv);
          });
        } else {
          subtitle.textContent = `Lỗi: ${result.message}`;
        }
      } catch (error) {
        console.error(error);
        subtitle.textContent = "Lỗi kết nối server";
      }
    }

    async function createThumbnail(sourceName, targetName) {
      // if(!confirm(`Tạo thumbnail ${targetName} từ ${sourceName}?`)) return;

      // showLoading('Đang tạo thumbnail...');
      // User removed showLoading, keeping commented out

      try {
        // Get params again
        const activeColorBtn = document.querySelector(".color-btn.active");
        let colorParam = activeColorBtn ? activeColorBtn.dataset.color : null;
        const activeColorOption = document.querySelector(
          ".color-option.active",
        );
        if (activeColorOption) {
          colorParam = activeColorOption.dataset.colorFolder;
        }

        // Derive ID from targetName (thumb_X.png)
        let id = targetName.replace("thumb_", "").replace(".png", "");

        const response = await fetch("/api/create_thumb", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kit: CURRENT_KIT_FOLDER,
            folder: currentPart.part.folder,
            source_file: sourceName,
            target_file: targetName,
            color: colorParam,
          }),
        });

        const result = await response.json();
        if (result.success) {
          // Update DOM directly instead of showFolderFiles()
          const container = document.querySelector(
            `.file-debug-group[data-id="${id}"]`,
          );
          if (container) {
            const thumbSlot = container.querySelector(".thumb-slot");
            if (thumbSlot) {
              const timestamp = new Date().getTime();
              // Construct image URL (Approximation, verified by network tab usually)
              // Thumbnails are always saved in the parent folder by app_server.py
              let url = `/downloads/${CURRENT_KIT_FOLDER}/${currentPart.part.folder}/${targetName}`;


              thumbSlot.className = "file-debug-slot thumb-slot";
              thumbSlot.style =
                "flex:1; display:flex; flex-direction:column; align-items:center; position:relative;";
              thumbSlot.title = targetName;
              thumbSlot.innerHTML = `
                                <img src="${url}?v=${timestamp}" style="width: 100%; height: 80px; object-fit: contain;">
                                <span>${targetName}</span>
                                
                                <div style="margin-top:5px; display:flex; gap:5px;">
                                    <button onclick="renameFile('${targetName}')" title="Đổi tên" style="cursor:pointer; border:none; background:#f39c12; color:white; border-radius:3px; padding:2px 5px;">✏️</button>
                                    <button onclick="deleteFile('${targetName}')" title="Xóa" style="cursor:pointer; border:none; background:#c0392b; color:white; border-radius:3px; padding:2px 5px;">🗑️</button>
                                </div>
                             `;
              // Remove ondrop/ondragover which were on the empty slot
              thumbSlot.removeAttribute("ondrop");
              thumbSlot.removeAttribute("ondragover");
            }
          } else {
            // Fallback if ID finding fails (shouldn't happen)
            showFolderFiles();
          }
        } else {
          alert("Lỗi: " + result.message);
        }
      } catch (e) {
        alert("Lỗi server: " + e);
      } finally {
        hideLoading();
      }
    }

    async function deleteFile(filename) {
      // if(!confirm(`Bạn chắc chắn muốn XÓA file ${filename}?`)) return;

      // showLoading('Đang xóa...');
      try {
        const activeColorBtn = document.querySelector(".color-btn.active");
        let colorParam = activeColorBtn ? activeColorBtn.dataset.color : null;
        const activeColorOption = document.querySelector(
          ".color-option.active",
        );
        if (activeColorOption)
          colorParam = activeColorOption.dataset.colorFolder;

        const response = await fetch("/api/delete_file", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kit: CURRENT_KIT_FOLDER,
            folder: currentPart.part.folder,
            filename: filename,
            color: colorParam,
          }),
        });
        const result = await response.json();
        if (result.success) {
          if (filename === "nav.png") {
            showFolderFiles();
            return;
          }

          if (filename.startsWith("thumb_")) {
            let id = filename.replace("thumb_", "").replace(".png", "");
            const container = document.querySelector(
              `.file-debug-group[data-id="${id}"]`,
            );
            if (container) {
              const thumbSlot = container.querySelector(".thumb-slot");
              if (thumbSlot) {
                const mainNameSpan =
                  container.querySelector(".main-slot span");
                const mainName = mainNameSpan ? mainNameSpan.textContent : "";
                const targetName = filename;

                thumbSlot.className = "file-debug-slot thumb-slot";
                thumbSlot.style =
                  "flex:1; display:flex; flex-direction:column; justify-content:center; align-items:center; height:80px; border: 2px dashed #444;";
                thumbSlot.title = "";
                thumbSlot.innerHTML = `
                                    <button onclick="createThumbnail('${mainName}', '${targetName}')" 
                                            style="background: #27ae60; border: none; color: white; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 11px;">
                                        + Tạo Thumb
                                    </button>
                                    <span style="color:#e67e22; font-size:10px; margin-top:5px;">Kéo thả ảnh vào đây</span>
                                  `;
                thumbSlot.setAttribute("ondragover", "handleDragOver(event)");
                thumbSlot.setAttribute(
                  "ondrop",
                  `handleDrop(event, '${targetName}')`,
                );

                thumbSlot.addEventListener("click", (e) => {
                  if (e.target.tagName !== "BUTTON") return;
                });
              }
            } else {
              showFolderFiles();
            }
          } else {
            // Main File
            let id = filename.replace(".png", "");
            const container = document.querySelector(
              `.file-debug-group[data-id="${id}"]`,
            );
            if (container) {
              const mainSlot = container.querySelector(".main-slot");
              if (mainSlot) {
                mainSlot.style = "flex:1; opacity:0.5; text-align:center;";
                mainSlot.innerHTML = "No Main";
                mainSlot.removeAttribute("draggable");
                mainSlot.removeAttribute("ondragstart");
              }
            } else {
              showFolderFiles();
            }
          }
        } else {
          alert("Lỗi: " + result.message);
        }
      } catch (e) {
        alert("Lỗi: " + e);
      } finally {
        hideLoading();
      }
    }

    async function renameFile(oldName) {
      const newName = prompt(`Đổi tên ${oldName} thành:`, oldName);
      if (!newName || newName === oldName) return;

      showLoading("Đang đổi tên...");
      try {
        const activeColorBtn = document.querySelector(".color-btn.active");
        let colorParam = activeColorBtn ? activeColorBtn.dataset.color : null;
        const activeColorOption = document.querySelector(
          ".color-option.active",
        );
        if (activeColorOption)
          colorParam = activeColorOption.dataset.colorFolder;

        const response = await fetch("/api/rename_file", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kit: CURRENT_KIT_FOLDER,
            folder: currentPart.part.folder,
            old_name: oldName,
            new_name: newName,
            color: colorParam,
          }),
        });
        const result = await response.json();
        if (result.success) {
          showFolderFiles();
        } else {
          alert("Lỗi: " + result.message);
        }
      } catch (e) {
        alert("Lỗi: " + e);
      } finally {
        hideLoading();
      }
    }

    async function uploadNavFile(input) {
      if (!input.files || !input.files[0]) return;
      const file = input.files[0];

      // Basic size/type check if needed
      if (file.size > 2 * 1024 * 1024) {
        alert("File quá lớn (max 2MB)");
        input.value = "";
        return;
      }

      const reader = new FileReader();
      reader.onload = async function (e) {
        const base64Content = e.target.result;

        showLoading("Đang upload...");
        try {
          const activeColorBtn = document.querySelector(".color-btn.active");
          let colorParam = activeColorBtn
            ? activeColorBtn.dataset.color
            : null;
          const activeColorOption = document.querySelector(
            ".color-option.active",
          );
          if (activeColorOption)
            colorParam = activeColorOption.dataset.colorFolder;

          const response = await fetch("/api/upload_file", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              kit: CURRENT_KIT_FOLDER,
              folder: currentPart.part.folder,
              filename: "nav.png",
              file_content: base64Content,
              color: colorParam,
            }),
          });
          const result = await response.json();
          if (result.success) {
            showFolderFiles();
          } else {
            alert("Lỗi: " + result.message);
          }
        } catch (err) {
          alert("Lỗi: " + err);
        } finally {
          hideLoading();
          input.value = "";
        }
      };
      reader.readAsDataURL(file);
    }

    // Drag & Drop Handlers
    function handleDragStart(e, filename) {
      e.dataTransfer.setData("source_file", filename);
      e.dataTransfer.effectAllowed = "copy";
    }

    function handleDragOver(e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      e.currentTarget.style.borderColor = "#27ae60";
      e.currentTarget.style.backgroundColor = "rgba(39, 174, 96, 0.1)";
    }

    async function handleDrop(e, targetName) {
      e.preventDefault();
      e.currentTarget.style.borderColor = "#444";
      e.currentTarget.style.backgroundColor = "transparent";

      const sourceName = e.dataTransfer.getData("source_file");
      if (!sourceName) return;

      // Call Create/Copy logic
      createThumbnail(sourceName, targetName);
    }

    // Global Loading Functions
    function showLoading(message = "Đang xử lý...") {
      document.getElementById("global-loading-message").textContent = message;
      document.getElementById("global-loading-overlay").style.display =
        "flex";
    }

    function hideLoading() {
      document.getElementById("global-loading-overlay").style.display =
        "none";
    }

    // Prompt delete part command
    async function promptDeletePart() {
      if (!currentPart) return;
      const yIndex = currentPart.part.y;
      const folderName = currentPart.part.folder;

      if (
        !confirm(
          `Bạn có muốn XÓA VĨNH VIỄN bộ phận "${folderName}"?\n\nLưu ý: Hành động này sẽ tự động đổi tên các folder phía sau để lấp khoảng trống.`,
        )
      )
        return;

      showLoading("Đang xóa bộ phận và cập nhật chỉ số folder...");

      try {
        const response = await fetch("/api/delete_part", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kit: CURRENT_KIT_FOLDER, y: yIndex }),
        });
        const result = await response.json();
        if (result.success) {
          alert("Đã xóa xong! Trang web sẽ tự động tải lại.");
          location.reload();
        } else {
          alert("Lỗi: " + result.message);
        }
      } catch (error) {
        alert(
          "Không thể kết nối đến Server. Bạn có đang chạy app_server.py không?",
        );
        console.error(error);
      } finally {
        hideLoading();
      }
    }

    // Initialize on load
    loadKitsList();

    // Merge Workspace State
    let mergeStack = [];
    let mergeFilesList = [];
    let mergeCanvas, mctx;

    async function renamePartFolder(oldName) {
      const newName = prompt(
        `Nhập tên mới cho thư mục "${oldName}":`,
        oldName,
      );
      if (!newName || newName === oldName) return;

      showLoading("Đang đổi tên thư mục...");

      try {
        const response = await fetch("/api/rename_folder", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kit: CURRENT_KIT_FOLDER,
            old_name: oldName,
            new_name: newName,
          }),
        });
        const result = await response.json();
        if (result.success) {
          //  alert('Đổi tên thành công!');
          loadKitStructure(true);
        } else {
          alert("Lỗi: " + result.message);
        }
      } catch (error) {
        console.error(error);
        alert("Lỗi kết nối server");
      } finally {
        hideLoading();
      }
    }

    async function flattenColors() {
      if (!currentPart) return;
      if (
        !confirm(
          `Bạn chắc chắn muốn GỘP TẤT CẢ layer từ các folder màu ra ngoài root của part ${currentPart.part.folder}?\nHành động này sẽ XÓA các folder màu sau khi gộp.`,
        )
      )
        return;

      // showLoading('Đang gộp màu...');
      try {
        const response = await fetch("/api/flatten_colors", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kit: CURRENT_KIT_FOLDER,
            folder: currentPart.part.folder,
          }),
        });
        const result = await response.json();
        if (result.success) {
          alert("Gộp màu thành công! Thư mục đã được làm phẳng.");
          document.getElementById("file-debug-modal").style.display = "none"; // Close modal if open
          loadKitStructure(true); // Refresh main UI
        } else {
          alert("Lỗi: " + result.message);
        }
      } catch (error) {
        console.error(error);
        alert("Lỗi kết nối server");
      } finally {
        hideLoading();
      }
    }

    async function mergeLayers() {
      if (!currentPart) return;
      const folderName = currentPart.part.folder;
      const color = currentColor || "default";

      document.getElementById("merge-folder-name").textContent =
        `${folderName} (${color})`;
      document.getElementById("merge-modal-overlay").style.display = "flex";

      // Initialize canvas if not yet done
      if (!mergeCanvas) {
        mergeCanvas = document.getElementById("merge-preview-canvas");
        mctx = mergeCanvas.getContext("2d");
      }
      mergeCanvas.width = canvasWidth;
      mergeCanvas.height = canvasHeight;

      // Clear previous state
      mergeStack = [];
      document.getElementById("merge-stack-list").innerHTML = "";
      document.getElementById("merge-dest-name").value = "1";
      mctx.clearRect(0, 0, mergeCanvas.width, mergeCanvas.height);

      try {
        const response = await fetch("/api/list_part_images", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kit: CURRENT_KIT_FOLDER,
            folder: folderName,
            color: color,
          }),
        });
        const result = await response.json();
        if (result.success) {
          mergeFilesList = result.files;
          renderMergeLibrary();
        } else {
          alert("Lỗi khi tải danh sách ảnh: " + result.message);
        }
      } catch (error) {
        console.error(error);
      }
    }

    function renderMergeLibrary() {
      const grid = document.getElementById("merge-library-grid");
      grid.innerHTML = "";
      const color = currentColor || "default";
      const folder = currentPart.part.folder;
      const baseUrl = `${KIT_PATH}${folder}/${color === "default" ? "" : color + "/"}`;

      mergeFilesList.forEach((file) => {
        // Robustness: Handle both string (old server) and object (new server)
        const filename = typeof file === "string" ? file : file.filename;

        const div = document.createElement("div");
        div.className = "item-option";
        div.innerHTML = `<img src="${baseUrl}${filename}?v=${imgVers}" title="${filename}">`;
        div.onclick = () => addToStack(file);
        grid.appendChild(div);
      });
    }

    function addToStack(file) {
      mergeStack.push(file);
      renderStack();
      redrawMergePreview();
    }

    function removeFromStack(index) {
      mergeStack.splice(index, 1);
      renderStack();
      redrawMergePreview();
    }

    // Track color adjustments for each layer
    let layerColorAdjustments = {}; // {filename: {hue_shift, saturation, brightness}}
    let selectedLayerIndex = null;

    function renderStack() {
      const list = document.getElementById("merge-stack-list");
      list.innerHTML = "";
      const color = currentColor || "default";
      const folder = currentPart.part.folder;
      const baseUrl = `${KIT_PATH}${folder}/${color === "default" ? "" : color + "/"}`;

      mergeStack.forEach((file, idx) => {
        const filename = typeof file === "string" ? file : file.filename;

        const item = document.createElement("div");
        item.className = "stack-item";
        if (selectedLayerIndex === idx) {
          item.style.background = "rgba(52, 152, 219, 0.3)";
          item.style.border = "2px solid #3498db";
        }
        item.style.cursor = "pointer";

        item.innerHTML = `
                    <span style="font-weight:bold; color:#666;">#${idx + 1}</span>
                    <img src="${baseUrl}${filename}?v=${imgVers}">
                    <span style="flex:1; font-size:12px;">${filename}</span>
                    <button class="btn" style="padding:2px 5px; background:#ff7675; color:white;" onclick="event.stopPropagation(); removeFromStack(${idx})">✖</button>
                `;

        // Click to select layer for color adjustment
        item.onclick = () => selectLayerForAdjustment(idx, filename);

        list.appendChild(item);
      });
    }

    function selectLayerForAdjustment(idx, filename) {
      selectedLayerIndex = idx;
      renderStack(); // Re-render to show selection

      // Show color adjustment panel
      const panel = document.getElementById("color-adjust-panel");
      panel.style.display = "block";
      document.getElementById("selected-layer-name").textContent = filename;

      // Load existing adjustments or defaults
      const adj = layerColorAdjustments[filename] || { target_color: null };

      if (adj.target_color) {
        document.getElementById("color-picker").value =
          "#" + adj.target_color;
        document.getElementById("color-value").textContent =
          "#" + adj.target_color.toUpperCase();
      } else {
        document.getElementById("color-picker").value = "#FFFFFF";
        document.getElementById("color-value").textContent = "Không đổi";
      }
    }

    function updateColorAdjustment() {
      if (selectedLayerIndex === null) return;

      const filename = mergeStack[selectedLayerIndex];
      const filenameStr =
        typeof filename === "string" ? filename : filename.filename;

      const colorHex = document
        .getElementById("color-picker")
        .value.replace("#", "");

      document.getElementById("color-value").textContent =
        "#" + colorHex.toUpperCase();

      layerColorAdjustments[filenameStr] = {
        target_color: colorHex.toUpperCase(),
        saturation: 1.0,
        brightness: 1.0,
      };

      // Redraw preview with new color
      redrawMergePreview();
    }

    function clearColorTint() {
      if (selectedLayerIndex === null) return;

      const filename = mergeStack[selectedLayerIndex];
      const filenameStr =
        typeof filename === "string" ? filename : filename.filename;

      document.getElementById("color-picker").value = "#FFFFFF";
      document.getElementById("color-value").textContent = "Không đổi";

      if (layerColorAdjustments[filenameStr]) {
        layerColorAdjustments[filenameStr].target_color = null;
      }

      redrawMergePreview();
    }

    function resetColorAdjustment() {
      if (selectedLayerIndex === null) return;

      const filename = mergeStack[selectedLayerIndex];
      const filenameStr =
        typeof filename === "string" ? filename : filename.filename;

      document.getElementById("color-picker").value = "#FFFFFF";
      document.getElementById("color-value").textContent = "Không đổi";

      delete layerColorAdjustments[filenameStr];

      redrawMergePreview();
    }

    async function redrawMergePreview() {
      mctx.clearRect(0, 0, mergeCanvas.width, mergeCanvas.height);
      const color = currentColor || "default";
      const folder = currentPart.part.folder;
      const baseUrl = `${KIT_PATH}${folder}/${color === "default" ? "" : color + "/"}`;

      for (const file of mergeStack) {
        const filename = typeof file === "string" ? file : file.filename;

        const img = new Image();
        img.crossOrigin = "anonymous"; // Enable CORS
        img.src = `${baseUrl}${filename}?v=${imgVers}`;
        await new Promise((resolve) => {
          img.onload = () => {
            // Check if this layer has color adjustments
            const adj = layerColorAdjustments[filename];

            if (adj && adj.target_color) {
              // Apply color tint using temporary canvas
              const tempCanvas = document.createElement("canvas");
              tempCanvas.width = img.naturalWidth;
              tempCanvas.height = img.naturalHeight;
              const tempCtx = tempCanvas.getContext("2d");

              // Draw original image
              tempCtx.drawImage(img, 0, 0);

              // Get image data
              const imageData = tempCtx.getImageData(
                0,
                0,
                tempCanvas.width,
                tempCanvas.height,
              );
              const data = imageData.data;

              // Parse target color
              const targetColor = adj.target_color;
              const r_target = parseInt(targetColor.substring(0, 2), 16);
              const g_target = parseInt(targetColor.substring(2, 4), 16);
              const b_target = parseInt(targetColor.substring(4, 6), 16);

              // Apply color tint
              for (let i = 0; i < data.length; i += 4) {
                const r = data[i];
                const g = data[i + 1];
                const b = data[i + 2];
                // const a = data[i + 3]; // Keep alpha unchanged

                // Convert to grayscale (luminosity)
                const gray = 0.299 * r + 0.587 * g + 0.114 * b;
                const intensity = gray / 255;

                // Apply target color scaled by intensity
                data[i] = r_target * intensity;
                data[i + 1] = g_target * intensity;
                data[i + 2] = b_target * intensity;
              }

              // Put modified image data back
              tempCtx.putImageData(imageData, 0, 0);

              // Use coordinate offsets if available
              let targetX =
                file.x !== undefined
                  ? file.x
                  : (mergeCanvas.width - tempCanvas.width) / 2;
              let targetY =
                file.y !== undefined
                  ? file.y
                  : (mergeCanvas.height - tempCanvas.height) / 2;

              // SPECIAL FIX: Nếu ảnh đã là Full Canvas, x/y nên là 0
              if (
                img.naturalWidth === canvasWidth &&
                img.naturalHeight === canvasHeight
              ) {
                targetX = 0;
                targetY = 0;
              }

              mctx.drawImage(tempCanvas, targetX, targetY);
            } else {
              // No color adjustment, draw normally
              let targetX =
                file.x !== undefined
                  ? file.x
                  : (mergeCanvas.width - img.naturalWidth) / 2;
              let targetY =
                file.y !== undefined
                  ? file.y
                  : (mergeCanvas.height - img.naturalHeight) / 2;

              // SPECIAL FIX: Nếu ảnh đã là Full Canvas, x/y nên là 0
              if (
                img.naturalWidth === canvasWidth &&
                img.naturalHeight === canvasHeight
              ) {
                targetX = 0;
                targetY = 0;
              }

              mctx.drawImage(img, targetX, targetY);
            }

            resolve();
          };
          img.onerror = resolve;
        });
      }
    }

    function shuffleStack() {
      for (let i = mergeStack.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [mergeStack[i], mergeStack[j]] = [mergeStack[j], mergeStack[i]];
      }
      renderStack();
      redrawMergePreview();
    }

    function clearStack() {
      mergeStack = [];
      renderStack();
      redrawMergePreview();
    }

    function closeMergeModal() {
      document.getElementById("merge-modal-overlay").style.display = "none";
    }

    async function confirmMerge() {
      if (mergeStack.length === 0) {
        alert("Vui lòng chọn ít nhất một ảnh để ghép!");
        return;
      }

      const destName =
        document.getElementById("merge-dest-name").value.trim() || "1";
      const bulkApply = document.getElementById("bulk-apply-check").checked;
      const btn = document.getElementById("confirm-merge-btn");

      btn.disabled = true;
      btn.textContent = "⏳ Đang lưu...";

      try {
        const response = await fetch("/api/merge_layers", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            kit: CURRENT_KIT_FOLDER,
            folder: currentPart.part.folder,
            color: currentColor || "default",
            selected_files: mergeStack.map((f) =>
              typeof f === "string" ? f : f.filename,
            ),
            offsets: mergeStack.reduce((acc, f) => {
              if (typeof f !== "string" && f.x !== undefined) {
                acc[f.filename] = { x: f.x, y: f.y };
              }
              return acc;
            }, {}),
            destination_name: destName,
            bulk_apply: bulkApply,
            layer_adjustments: layerColorAdjustments,
          }),
        });
        const result = await response.json();
        if (result.success) {
          alert(result.message);
          closeMergeModal();
          // Refresh the entire kit structure and selector
          loadKitStructure(true);
        } else {
          alert("Lỗi: " + result.message);
        }
      } catch (error) {
        console.error(error);
        alert("Lỗi server khi ghép layer.");
      } finally {
        btn.disabled = false;
        btn.textContent = "✅ Lưu";
      }
    }

    function setFocusArea(area) {
      activeFocusArea = area;
      updateFocusUI();
    }

    function updateFocusUI() {
      document.getElementById("part-navigation-area").classList.remove("active-focus");
      document.getElementById("item-selector-area").classList.remove("active-focus");
      document.getElementById("color-selector-area").classList.remove("active-focus");

      if (activeFocusArea === "parts") {
        document.getElementById("part-navigation-area").classList.add("active-focus");
      } else if (activeFocusArea === "items") {
        document.getElementById("item-selector-area").classList.add("active-focus");
      } else if (activeFocusArea === "colors") {
        document.getElementById("color-selector-area").classList.add("active-focus");
      }
    }

    // Keyboard navigation for colors
    window.addEventListener("keydown", (e) => {
      // Only ignore if user is typing in a text input or textarea
      if (e.target.tagName === "TEXTAREA" ||
        (e.target.tagName === "INPUT" && ["text", "number", "search"].includes(e.target.type))) {
        return;
      }

      // Also check if any modal is open
      const modals = ["merge-modal-overlay", "layer-details-modal", "file-debug-modal"];
      for (const id of modals) {
        const m = document.getElementById(id);
        if (m && m.style.display !== "none" && m.style.display !== "") return;
      }

      // 1, 2, 3 to switch focus regions
      if (e.key === "1") { setFocusArea("parts"); return; }
      if (e.key === "2") { setFocusArea("items"); return; }
      if (e.key === "3") { setFocusArea("colors"); return; }

      if (!currentPart) return;

      // Logic based on focused area
      if (activeFocusArea === "parts") {
        let newIdx = currentPart.index;
        if (e.key === "ArrowUp" || e.key === "ArrowLeft") newIdx--;
        else if (e.key === "ArrowDown" || e.key === "ArrowRight") newIdx++;
        else return;

        if (newIdx >= 0 && newIdx < kitStructure.length) {
          e.preventDefault();
          selectPart(newIdx, kitStructure[newIdx]);
          document.querySelector(".nav-icon.active")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
        return;
      }

      if (activeFocusArea === "items") {
        const grid = document.getElementById("item-grid");
        const items = grid.querySelectorAll(".item-option");
        if (!items.length) return;

        const gridStyle = window.getComputedStyle(grid);
        const columns = gridStyle.getPropertyValue("grid-template-columns").split(" ").length;

        // Find current active index
        let currentIndex = -1;
        items.forEach((item, idx) => { if (item.classList.contains("active")) currentIndex = idx; });

        let newIdx = currentIndex;
        switch (e.key) {
          case "ArrowLeft": newIdx--; break;
          case "ArrowRight": newIdx++; break;
          case "ArrowUp": newIdx -= columns; break;
          case "ArrowDown": newIdx += columns; break;
          default: return;
        }

        if (newIdx >= 0 && newIdx < items.length) {
          e.preventDefault();
          items[newIdx].click();
          items[newIdx].scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
        return;
      }

      if (activeFocusArea === "colors") {
        const colors = currentPart.part.colors.length > 0 ? currentPart.part.colors : ["default"];
        const grid = document.getElementById("color-grid");
        if (!grid || !grid.children.length) return;

        const gridStyle = window.getComputedStyle(grid);
        const columns = gridStyle.getPropertyValue("grid-template-columns").split(" ").length;

        let newIndex = currentColorIndex;
        switch (e.key) {
          case "ArrowLeft": newIndex = currentColorIndex - 1; break;
          case "ArrowRight": newIndex = currentColorIndex + 1; break;
          case "ArrowUp": newIndex = currentColorIndex - columns; break;
          case "ArrowDown": newIndex = currentColorIndex + columns; break;
          case "d":
          case "D":
            e.preventDefault();
            const activeOption = document.querySelector(".color-option.active");
            const checkbox = activeOption?.querySelector(".color-checkbox");
            if (checkbox) checkbox.click();
            return;
          case "f":
          case "F":
            confirmDeleteColors();
            e.preventDefault();
            return;
          default: return;
        }

        if (newIndex >= 0 && newIndex < colors.length) {
          e.preventDefault();
          selectColor(colors[newIndex], newIndex);
          const targetElement = grid.children[newIndex];
          if (targetElement) targetElement.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }
    });

// --- Merged Script ---

function toggleMergeBackground() {
      const canvas = document.getElementById("merge-preview-canvas");
      const currentBg = canvas.style.background;
      if (currentBg === "rgb(34, 34, 34)" || currentBg === "#222") {
        canvas.style.background = "";
      } else {
        canvas.style.background = "#222";
      }
    }

    function updateFocusUI() {
      document.querySelectorAll(".focus-region").forEach((reg) => {
        reg.classList.remove("active-focus");
      });
      const targetId = {
        parts: "nav-icons",
        items: "item-grid",
        colors: "color-grid",
      }[activeFocusArea];
      const el = document.getElementById(targetId);
      if (el) el.classList.add("active-focus");
    }

    function setFocusArea(area) {
      activeFocusArea = area;
      updateFocusUI();
    }

    // Auto Create Thumbs
    async function autoCreateThumbs() {
      if (!CURRENT_KIT_FOLDER) {
        alert("Vui lòng chọn kit trước!");
        return;
      }

      if (!confirm("Tạo thumbnail tự động cho tất cả folder X-Y trong data này?\n\nChỉ tạo thumb cho file chưa có.")) {
        return;
      }

      // Show loading
      showGlobalLoading("Đang quét và tạo thumbnail...");

      try {
        const response = await fetch("/api/auto_create_thumbs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kit: CURRENT_KIT_FOLDER })
        });

        const result = await response.json();
        hideGlobalLoading();

        if (result.success) {
          const stats = result.stats;
          let message = `✅ Hoàn tất!\n\n`;
          message += `📁 Đã quét: ${stats.total_folders} folder\n`;
          message += `🖼️ Tổng ảnh: ${stats.total_images}\n`;
          message += `✨ Đã tạo: ${stats.created_thumbs} thumb\n`;
          message += `⏭️ Bỏ qua: ${stats.skipped_thumbs} thumb (đã có)\n\n`;

          if (stats.details.length > 0) {
            message += `Chi tiết:\n`;
            stats.details.forEach(d => {
              message += `  ${d.folder}: +${d.created} thumb\n`;
            });
          }

          alert(message);

          // Reload kit structure để cập nhật UI
          loadKitStructure(true);
        } else {
          alert("❌ Lỗi: " + result.message);
        }
      } catch (error) {
        hideGlobalLoading();
        alert("❌ Lỗi kết nối: " + error.message);
      }
    }

    // Delete All Thumbs
    async function deleteAllThumbs() {
      if (!CURRENT_KIT_FOLDER) {
        alert("Vui lòng chọn kit trước!");
        return;
      }

      if (!confirm("⚠️ CẢNH BÁO: Bạn có chắc chắn muốn xóa TẤT CẢ thumbnail (thumb_*.png) trong data này không?")) {
        return;
      }

      if (!confirm("❗ Hành động này không thể hoàn tác. Bạn thực sự muốn xóa?")) {
        return;
      }

      showGlobalLoading("Đang xóa tất cả thumbnail...");

      try {
        const response = await fetch("/api/delete_all_thumbs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kit: CURRENT_KIT_FOLDER })
        });

        const result = await response.json();
        hideGlobalLoading();

        if (result.success) {
          alert(`✅ ${result.message}`);
          // Reload kit structure
          loadKitStructure(true);
        } else {
          alert("❌ Lỗi: " + result.message);
        }
      } catch (error) {
        hideGlobalLoading();
        alert("❌ Lỗi kết nối: " + error.message);
      }
    }

    // Helper for global loading
    function showGlobalLoading(msg) {
      let overlay = document.getElementById('global-loading-overlay');
      if (!overlay) {
        // Create if not exists
        overlay = document.createElement('div');
        overlay.id = 'global-loading-overlay';
        overlay.innerHTML = `<div class="spinner"></div><p id="global-loading-message"></p>`;
        document.body.appendChild(overlay);
      }
      const msgEl = document.getElementById('global-loading-message');
      if (msgEl) msgEl.textContent = msg || "Đang xử lý...";
      overlay.style.display = 'flex';
    }

    function hideGlobalLoading() {
      const overlay = document.getElementById('global-loading-overlay');
      if (overlay) overlay.style.display = 'none';
    }