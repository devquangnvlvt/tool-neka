// Configuration
let KIT_BASE_PATH = "downloads/";
let CURRENT_KIT_FOLDER = ""; // Set dynamically
let KIT_PATH = ""; // Set dynamically

// State
let kitStructure = null; // Changed from metadata
let globallySelectedColors = new Set(); // Chứa các mã màu đã chọn để đồng bộ giữa các bộ phận
let kits = [];
let currentPart = null;
let currentItem = null;
let currentColor = null;
let currentColorIndex = 0;
let lastColorIndex = null; // Mốc chọn màu gần nhất (chuột trái)
let characterLayers = {};
let imgVers = Date.now();
let showColorThumb = false; // Toggle: hiển thị thumb theo màu
let partSortType = "y"; // 'x' or 'y'
let currentZFilter = "all"; // 'all', '1', '2'
let debugSelectedIds = new Set();
let currentDebugColor = null;
let selectMergeMode = false;
let selectedMergeFolders = [];
let lastCheckedIndex = null;

let restoredActivePartFolder = null;
let allKits = [];
let currentParentFilter = "all";

// ---- LocalStorage Persistence ----
function saveSelectionState() {
  if (!CURRENT_KIT_FOLDER) return;
  // Serialize only what we need: per-folder item + color and active part
  const snapshot = {
    _meta: {
      activePartFolder: currentPart ? currentPart.part.folder : null,
    },
  };
  Object.entries(characterLayers).forEach(([idx, layer]) => {
    if (layer && layer.folderName) {
      snapshot[layer.folderName] = {
        itemNumber: layer.itemNumber,
        color: layer.color,
        colorIndex: layer.colorIndex || 0,
      };
    }
  });
  localStorage.setItem(
    `selection_${CURRENT_KIT_FOLDER}`,
    JSON.stringify(snapshot),
  );
}

function restoreSelectionState() {
  if (!CURRENT_KIT_FOLDER || !kitStructure) return;
  try {
    const raw = localStorage.getItem(`selection_${CURRENT_KIT_FOLDER}`);
    if (!raw) return;
    const snapshot = JSON.parse(raw);

    if (snapshot._meta && snapshot._meta.activePartFolder) {
      restoredActivePartFolder = snapshot._meta.activePartFolder;
    }

    kitStructure.forEach((part, idx) => {
      const saved = snapshot[part.folder];
      if (saved) {
        characterLayers[idx] = {
          folderName: part.folder,
          itemNumber: saved.itemNumber,
          color: saved.color,
          colorIndex: saved.colorIndex || 0,
          sortOrder: part.x * 1000 + idx,
        };
      }
    });
  } catch (e) {
    console.warn("Could not restore selection state:", e);
  }
}

// Toggle color thumb mode
function toggleColorThumb(checked) {
  showColorThumb = checked;
  if (currentPart) {
    loadItems(currentPart.part);
  }
}

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
      allKits = result.kits;
      kits = allKits;

      if (result.parents) {
        renderParentSelector(result.parents);
      }

      // Restore parent filter if saved
      const savedParent = localStorage.getItem("selectedParent") || "all";
      const parentSelector = document.getElementById("parent-selector");
      if (parentSelector) parentSelector.value = savedParent;
      currentParentFilter = savedParent;

      if (savedParent !== "all") {
        kits = allKits.filter((k) => k.parent === savedParent);
      } else {
        kits = allKits.filter((k) => k.parent === "Mặc định (Ngoài)");
      }

      if (kits.length > 0) {
        // Check localStorage for saved kit
        let savedKit = localStorage.getItem("selectedKit");
        // Ensure saved kit actually exists within the currently filtered parent
        let kitToSelect =
          savedKit && kits.find((k) => k.folder === savedKit)
            ? kits.find((k) => k.folder === savedKit)
            : kits[0];

        CURRENT_KIT_FOLDER = kitToSelect.folder;
        KIT_PATH = `${KIT_BASE_PATH}${CURRENT_KIT_FOLDER}/`;

        renderKitsSelector(kits);
      }

      loadKitStructure();
      // Check all missing thumbnails after kit structure is loaded
      setTimeout(checkAllMissingThumbnails, 1500);
    } else {
      console.error("Error loading kits list:", result.message);
    }
  } catch (error) {
    console.error("Error loading kits list:", error);
  }
}

// Render Parent/Category Selector
function renderParentSelector(parents) {
  const selector = document.getElementById("parent-selector");
  if (!selector) return;

  selector.innerHTML =
    '<option value="all">-- Mặc định (Thư mục ngoài) --</option>';
  parents.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    selector.appendChild(opt);
  });
}

// Filter Kits by Category
function filterByCategory(parentName) {
  currentParentFilter = parentName;
  localStorage.setItem("selectedParent", parentName);
  const searchTerm = document
    .getElementById("kit-search")
    .value.toLowerCase()
    .trim();

  let filtered = allKits;
  if (parentName !== "all") {
    filtered = allKits.filter((k) => k.parent === parentName);
  } else {
    // When "all" is selected, only show loose folders that are directly in DATA_DIR
    filtered = allKits.filter((k) => k.parent === "Mặc định (Ngoài)");
  }

  if (searchTerm) {
    filtered = filtered.filter(
      (kit) =>
        kit.name.toLowerCase().includes(searchTerm) ||
        kit.folder.toLowerCase().includes(searchTerm),
    );
  }

  kits = filtered;
  renderKitsSelector(filtered);

  // Auto-select the first kit when a category is chosen
  if (filtered.length > 0) {
    const kitSelector = document.getElementById("kit-selector");
    if (kitSelector) {
      kitSelector.value = filtered[0].folder;
      switchKit(filtered[0].folder);
    }
  } else {
    // Clear current UI if no kits are found in this category
    const navContainer = document.getElementById("nav-icons");
    const countLayer = document.getElementById("count-layer");
    const warningBox = document.getElementById("warning-box");

    if (navContainer) navContainer.innerHTML = "";
    if (countLayer) countLayer.innerHTML = "";
    if (warningBox) {
      warningBox.style.display = "block";
      warningBox.innerHTML =
        '<div style="color: #ff9800; padding: 10px; border: 1px solid #ff9800; border-radius: 4px; background: rgba(255, 152, 0, 0.1);">' +
        "<strong>⚠️ Thông báo:</strong> Không có bộ sưu tập nào trong thư mục này.</div>";
    }
    kitStructure = [];
    renderCharacter(); // Clear canvas
  }
}

// Fetch Server IP
async function fetchServerIP() {
  try {
    const response = await fetch("/api/get_ip");
    const result = await response.json();
    if (result.success && result.ip) {
      const display = document.getElementById("server-ip-display");
      if (display) {
        display.textContent = `Server IP: ${result.ip}:${window.location.port || "8000"}`;
      }

      // Replace hardcoded IPs in the header links
      const linkPicrew = document.getElementById("link-picrew");
      const linkNeka = document.getElementById("link-neka");

      if (linkPicrew) {
        linkPicrew.href = `http://${result.ip}:3000/`;
      }
      if (linkNeka) {
        linkNeka.href = `http://${result.ip}:8000/`; // Keeping it 8000 as per user request snippet
      }
    }
  } catch (error) {
    console.error("Error fetching server IP:", error);
  }
}

// Check for missing thumbnails from ALL kits in all parent folders
async function checkAllMissingThumbnails() {
  try {
    const response = await fetch("/api/check_missing_thumbnails", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}), // No specific kit - check all
    });
    const result = await response.json();

    console.log("checkAllMissingThumbnails - API result:", result);
    console.log("Missing items:", result.missing_thumbnails);

    if (result.success && result.total_missing > 0) {
      // Group by parent folder for display
      const groupedByParent = {};
      result.missing_thumbnails.forEach(item => {
        const parentKey = item.parent || 'downloads';
        if (!groupedByParent[parentKey]) {
          groupedByParent[parentKey] = {};
        }
        if (!groupedByParent[parentKey][item.kit]) {
          groupedByParent[parentKey][item.kit] = [];
        }
        groupedByParent[parentKey][item.kit].push(item.folder);
      });

      console.log("Grouped by parent:", groupedByParent);

      // Create notification HTML with details grouped by parent folder
      let detailsHTML = '';
      Object.entries(groupedByParent).forEach(([parent, kits]) => {
        console.log(`Adding parent: ${parent}`, kits);
        detailsHTML += `<div style="margin: 8px 0; padding: 8px; background: rgba(255,255,255,0.3); border-radius: 4px;">
          <strong style="color: #ff6f00;">📁 ${parent}</strong><br>`;

        Object.entries(kits).forEach(([kit, folders]) => {
          detailsHTML += `<div style="margin-left: 10px; font-size: 11px;">
            <strong>${kit}:</strong> ${folders.slice(0, 3).join(", ")}${folders.length > 3 ? ` ... +${folders.length - 3}` : ''}
          </div>`;
        });

        detailsHTML += `</div>`;
      });

      const notificationHTML = `
        <div id="thumbnail-warning-box" style="
          background: linear-gradient(135deg, #fff3cd 0%, #ffe69c 100%);
          border-left: 5px solid #ff9800;
          border-radius: 8px;
          padding: 15px;
          margin-bottom: 15px;
          box-shadow: 0 2px 8px rgba(255, 152, 0, 0.3);
          font-family: Arial, sans-serif;
        ">
          <div style="font-weight: bold; color: #e65100; font-size: 14px; margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 18px;">⚠️</span>
            Phát hiện ${result.total_missing} BỘ PHẬN THIẾU THUMBNAIL (${result.percentage_missing}%)
          </div>
          <div style="font-size: 12px; color: #d84315; max-height: 150px; overflow-y: auto; background: rgba(255,255,255,0.5); padding: 10px; border-radius: 4px;">
            ${detailsHTML}
          </div>
        </div>
      `;

      // Display in thumbnail-warnings
      const warningsDiv = document.getElementById("thumbnail-warnings");
      if (warningsDiv) {
        warningsDiv.innerHTML = notificationHTML;
        warningsDiv.style.display = 'block';
      }

      console.warn(`✋ Missing thumbnails detected: ${result.total_missing} folders (${result.percentage_missing}%)`);
    }
  } catch (error) {
    console.error("Error checking missing thumbnails:", error);
  }
}

// Check for missing thumbnails and display notification
async function checkMissingThumbnails() {
  try {
    const response = await fetch("/api/check_missing_thumbnails", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const result = await response.json();

    if (result.success && result.total_missing > 0) {
      // Group by kit for display
      const groupedByKit = {};
      result.missing_thumbnails.forEach(item => {
        if (!groupedByKit[item.kit]) {
          groupedByKit[item.kit] = [];
        }
        groupedByKit[item.kit].push(item.folder);
      });

      // Create notification HTML with details
      let detailsHTML = '';
      Object.entries(groupedByKit).forEach(([kit, folders]) => {
        detailsHTML += `<div style="margin: 8px 0;"><strong>${kit}:</strong> ${folders.slice(0, 5).join(", ")}${folders.length > 5 ? ` ... +${folders.length - 5} cái khác` : ''}</div>`;
      });

      const notificationHTML = `
        <div id="thumbnail-warning-box" style="
          background: linear-gradient(135deg, #fff3cd 0%, #ffe69c 100%);
          border-left: 5px solid #ff9800;
          border-radius: 8px;
          padding: 15px;
          margin-bottom: 15px;
          box-shadow: 0 2px 8px rgba(255, 152, 0, 0.3);
          font-family: Arial, sans-serif;
        ">
          <div style="font-weight: bold; color: #e65100; font-size: 14px; margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 18px;">⚠️</span>
            Phát hiện ${result.total_missing} BỘ PHẬN THIẾU THUMBNAIL (${result.percentage_missing}%)
          </div>
          <div style="font-size: 12px; color: #d84315; max-height: 150px; overflow-y: auto; background: rgba(255,255,255,0.5); padding: 10px; border-radius: 4px;">
            ${detailsHTML}
            <div style="margin-top: 8px; font-size: 11px; font-style: italic; color: #666;">→ Kiểm tra file: <code>downloads/missing_thumbnails_report.json</code></div>
          </div>
        </div>
      `;

      // Try to display in thumbnail-warnings first
      const warningsDiv = document.getElementById("thumbnail-warnings");
      if (warningsDiv) {
        warningsDiv.innerHTML = notificationHTML;
        warningsDiv.style.display = 'block';
      } else {
        // Fallback: create new notification div at top
        const container = document.querySelector('.container-full');
        if (container) {
          const notifDiv = document.createElement('div');
          notifDiv.innerHTML = notificationHTML;
          container.insertBefore(notifDiv.firstElementChild, container.firstChild);
        }
      }

      console.warn(`✋ Missing thumbnails detected: ${result.total_missing} folders (${result.percentage_missing}%)`);
    }
  } catch (error) {
    console.error("Error checking missing thumbnails:", error);
  }
}

// Check for missing thumbnails of a specific kit
async function checkMissingThumbnailsForKit(kitFolder) {
  try {
    const response = await fetch("/api/check_missing_thumbnails", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kit: kitFolder }),
    });
    const result = await response.json();

    if (result.success && result.total_missing > 0) {
      // Display warning for this kit
      const folders = result.missing_thumbnails.map(item => item.folder);
      const isSingle = result.total_missing === 1;

      const notificationHTML = `
        <div id="thumbnail-warning-box-kit" style="
          background: linear-gradient(135deg, ${isSingle ? '#fff3cd' : '#fff3cd'} 0%, ${isSingle ? '#ffe69c' : '#ffe69c'} 100%);
          border-left: 5px solid #ff9800;
          border-radius: 8px;
          padding: 12px;
          margin-bottom: 10px;
          box-shadow: 0 2px 8px rgba(255, 152, 0, 0.3);
          font-family: Arial, sans-serif;
          font-size: 12px;
        ">
          <div style="font-weight: bold; color: #e65100; margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 16px;">⚠️</span>
            <strong>${kitFolder}</strong> - Thiếu ${result.total_missing} bộ phận (${result.percentage_missing}%)
          </div>
          <div style="color: #d84315; max-height: 100px; overflow-y: auto; background: rgba(255,255,255,0.5); padding: 8px; border-radius: 4px;">
            <strong>Bộ phận thiếu:</strong> ${folders.slice(0, 10).join(", ")}${folders.length > 10 ? ` ... +${folders.length - 10} cái khác` : ''}
          </div>
        </div>
      `;

      // Display in thumbnail-warnings
      const warningsDiv = document.getElementById("thumbnail-warnings");
      if (warningsDiv) {
        warningsDiv.innerHTML = notificationHTML;
        warningsDiv.style.display = 'block';
      }

      const itemText = isSingle ? 'bộ phận' : 'bộ phận';
      console.warn(`⚠️ Kit "${kitFolder}" - Thiếu ${result.total_missing} ${itemText} thumbnail (${result.percentage_missing}%)`);
    } else {
      // Clear warning if no missing thumbnails
      const warningsDiv = document.getElementById("thumbnail-warnings");
      if (warningsDiv) {
        warningsDiv.innerHTML = '';
        warningsDiv.style.display = 'none';
      }
    }
  } catch (error) {
    console.error("Error checking missing thumbnails for kit:", error);
  }
}

// Check for corrupted images of a specific kit
async function checkCorruptedImagesForKit(kitFolder) {
  try {
    const response = await fetch("/api/check_corrupted_images", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kit: kitFolder }),
    });
    const result = await response.json();

    if (result.success && result.corrupted_files.length > 0) {
      const files = result.corrupted_files;

      const notificationHTML = `
        <div id="corrupted-warning-box-kit" style="
          background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
          border-left: 5px solid #dc3545;
          border-radius: 8px;
          padding: 12px;
          margin-bottom: 10px;
          box-shadow: 0 2px 8px rgba(220, 53, 69, 0.3);
          font-family: Arial, sans-serif;
          font-size: 12px;
        ">
          <div style="font-weight: bold; color: #721c24; margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 16px;">🚨</span>
            <strong>${kitFolder}</strong> - Phát hiện ${files.length} ảnh bị lỗi cấu trúc
          </div>
          <div style="color: #721c24; max-height: 100px; overflow-y: auto; background: rgba(255,255,255,0.5); padding: 8px; border-radius: 4px;">
            <strong>Ảnh bị lỗi:</strong><br> ${files.slice(0, 10).join("<br>")}${files.length > 10 ? `<br>... +${files.length - 10} file khác` : ''}
          </div>
        </div>
      `;

      let warningsDiv = document.getElementById("corrupted-warnings");
      if (!warningsDiv) {
        warningsDiv = document.createElement("div");
        warningsDiv.id = "corrupted-warnings";
        const partThumbWarnings = document.getElementById("part-thumbnail-warning");
        if (partThumbWarnings) {
          partThumbWarnings.parentNode.insertBefore(warningsDiv, partThumbWarnings.nextSibling);
        } else {
          const container = document.querySelector('.container-full');
          if (container) {
            container.insertBefore(warningsDiv, container.firstChild);
          }
        }
      }
      warningsDiv.innerHTML = notificationHTML;
      warningsDiv.style.display = 'block';

      console.warn(`🚨 Kit "${kitFolder}" - Phát hiện ${files.length} ảnh bị lỗi cấu trúc`);
    } else {
      const warningsDiv = document.getElementById("corrupted-warnings");
      if (warningsDiv) {
        warningsDiv.innerHTML = '';
        warningsDiv.style.display = 'none';
      }
    }
  } catch (error) {
    console.error("Error checking corrupted images for kit:", error);
  }
}

// Check for invalid image filenames (not matching n.png / thumb_n.png) in a kit
async function checkInvalidFilenamesForKit(kitFolder) {
  try {
    const response = await fetch("/api/check_invalid_filenames", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kit: kitFolder }),
    });
    const result = await response.json();

    let warningsDiv = document.getElementById("invalid-filename-warnings");

    if (result.success && result.total_invalid > 0) {
      const files = result.invalid_files;

      // Group by part folder for display
      const groupedByPart = {};
      files.forEach(item => {
        if (!groupedByPart[item.part]) groupedByPart[item.part] = [];
        groupedByPart[item.part].push(item);
      });

      let detailsHTML = '';
      Object.entries(groupedByPart).forEach(([part, items]) => {
        detailsHTML += `<div style="margin: 6px 0;">
          <strong style="color:#7b1fa2;">📁 ${part}</strong><br>`;
        items.slice(0, 8).forEach(item => {
          const location = item.color
            ? `<span style="color:#555;">mã màu <code>${item.color}</code> → </span>`
            : '';
          detailsHTML += `<div style="margin-left:12px;font-size:11px;">
            ${location}<code style="background:#f3e5f5;padding:1px 4px;border-radius:3px;color:#6a1b9a;">${item.file}</code>
          </div>`;
        });
        if (items.length > 8) {
          detailsHTML += `<div style="margin-left:12px;font-size:11px;color:#888;">... +${items.length - 8} file khác</div>`;
        }
        detailsHTML += `</div>`;
      });

      const notificationHTML = `
        <div id="invalid-filename-warning-box" style="
          background: linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%);
          border-left: 5px solid #9c27b0;
          border-radius: 8px;
          padding: 12px;
          margin-bottom: 10px;
          box-shadow: 0 2px 8px rgba(156, 39, 176, 0.3);
          font-family: Arial, sans-serif;
          font-size: 12px;
        ">
          <div style="font-weight: bold; color: #4a148c; margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 16px;">🚫</span>
            <strong>${kitFolder}</strong> – ${result.total_invalid} file có <u>tên ảnh sai định dạng</u>
          </div>
          <div style="font-size: 11px; color: #5e35b1; margin-bottom: 6px;">
            Định dạng đúng: <code>n.png</code> / <code>thumb_n.png</code> (n là số). File sai:
          </div>
          <div style="color: #4a148c; max-height: 130px; overflow-y: auto; background: rgba(255,255,255,0.55); padding: 8px; border-radius: 4px;">
            ${detailsHTML}
          </div>
        </div>
      `;

      if (!warningsDiv) {
        warningsDiv = document.createElement("div");
        warningsDiv.id = "invalid-filename-warnings";
        // Ưu tiên chèn ngay bên dưới khung cảnh báo structure-warnings (chứa Lỗi Nhảy Cóc Ảnh)
        const structWarnings = document.getElementById("structure-warnings");
        const thumbWarnings = document.getElementById("thumbnail-warnings");
        const targetRef = structWarnings || thumbWarnings;
        
        if (targetRef && targetRef.parentNode) {
          targetRef.parentNode.insertBefore(warningsDiv, targetRef.nextSibling);
        } else {
          const container = document.querySelector('.container-full');
          if (container) container.appendChild(warningsDiv);
        }
      }
      warningsDiv.innerHTML = notificationHTML;
      warningsDiv.style.display = 'block';

      console.warn(`🚫 Kit "${kitFolder}" – ${result.total_invalid} file tên sai định dạng`);
    } else {
      // Clear nếu không có lỗi
      if (warningsDiv) {
        warningsDiv.innerHTML = '';
        warningsDiv.style.display = 'none';
      }
    }
  } catch (error) {
    console.error("Error checking invalid filenames for kit:", error);
  }
}

// Global initialization
document.addEventListener("DOMContentLoaded", () => {
  fetchServerIP();
  loadKitsList();
});

// Render Kits Selector
function renderKitsSelector(kitsToRender) {
  const selector = document.getElementById("kit-selector");
  const currentValue = selector.value || CURRENT_KIT_FOLDER;

  selector.innerHTML = "";

  if (kitsToRender.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Không tìm thấy kết quả";
    selector.appendChild(opt);
    return;
  }

  // Add search placeholder only if search is active
  const searchInput = document.getElementById("kit-search");
  if (searchInput && searchInput.value.trim() !== "") {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "-- Chọn kết quả bên dưới --";
    selector.appendChild(placeholder);
  }

  kitsToRender.forEach((kit) => {
    const option = document.createElement("option");
    option.value = kit.folder;
    option.textContent = kit.name;
    // Highlight if search is empty OR it matches current kit
    if (!searchInput || searchInput.value.trim() === "") {
      if (kit.folder === currentValue) option.selected = true;
    }
    selector.appendChild(option);
  });
}

// Filter Kits
function filterKits(query) {
  const searchTerm = query.toLowerCase().trim();

  let filtered = allKits;
  if (currentParentFilter !== "all") {
    filtered = allKits.filter((k) => k.parent === currentParentFilter);
  } else {
    filtered = allKits.filter((k) => k.parent === "Mặc định (Ngoài)");
  }

  if (searchTerm) {
    filtered = filtered.filter(
      (kit) =>
        kit.name.toLowerCase().includes(searchTerm) ||
        kit.folder.toLowerCase().includes(searchTerm),
    );
  }

  kits = filtered;
  renderKitsSelector(filtered);
}

let isLoadingKit = false;

// Switch Kit
function switchKit(folderName) {
  if (!folderName || isLoadingKit) return;
  isLoadingKit = true;

  CURRENT_KIT_FOLDER = folderName;
  KIT_PATH = `${KIT_BASE_PATH}${CURRENT_KIT_FOLDER}/`;

  // Save to localStorage
  localStorage.setItem("selectedKit", folderName);

  // Clear search if any
  const searchInput = document.getElementById("kit-search");
  if (searchInput) {
    searchInput.value = "";
    renderKitsSelector(kits); // Restore full list
  }

  // Clear current kit structure to trigger fresh load
  kitStructure = null;

  // Reset character UI
  resetCharacter();

  // Check for missing thumbnails in this kit
  checkMissingThumbnailsForKit(folderName);

  // Reload kit structure for new kit
  loadKitStructure().finally(() => {
    isLoadingKit = false;
  });
}

// Load kit structure from folder API
async function loadKitStructure(preserveSelection = false) {
  try {
    showGlobalLoading("Đang tải bộ sưu tập...");
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

      const displayWidth = 600;
      const aspectRatio = canvasHeight / canvasWidth;
      canvas.width = displayWidth;
      // canvas.height = displayWidth * aspectRatio;
      // canvas.style.height = displayWidth * aspectRatio + "px";
      // Đặt kích thước thực của canvas bằng đúng kích thước ảnh gốc (độ phân giải cao)
      //canvas.width = canvasWidth;
      //canvas.height = canvasHeight;

      // Xóa các inline style để CSS quản lý hiển thị co giãn theo tỉ lệ gốc
      //canvas.style.width = "";
      //canvas.style.height = "";

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

      // Gap In Images Warnings
      let gapWarnings = [];
      result.parts.forEach((p) => {
        if (p.missing_images && p.missing_images.length > 0) {
          gapWarnings.push(
            `Folder <strong>${p.folder}</strong> thiếu ảnh gốc: ${p.missing_images.join(", ")}`,
          );
        }
        if (p.color_gaps) {
          Object.entries(p.color_gaps).forEach(([color, gaps]) => {
            gapWarnings.push(
              `Folder <strong>${p.folder}</strong> mẫu màu <strong style="color:#d63031;">${color}</strong> thiếu ảnh: ${gaps.join(", ")}`,
            );
          });
        }
      });

      if (gapWarnings.length > 0) {
        warningHtml += `
                  <div style="margin-top:10px; padding-top:10px; border-top:1px solid #ffe0b2;">
                      <strong>🔴 LỖI NHẢY CÓC ẢNH (1, 2, 3...):</strong><br>
                      ${gapWarnings.slice(0, 10).join("<br>")}
                      ${gapWarnings.length > 10 ? `<br>... và ${gapWarnings.length - 10} lỗi khác.` : ""}
                  </div>
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
        // Matches by folderName (more robust during reordering/renaming)
        const oldLayers = { ...characterLayers };
        characterLayers = {};

        kitStructure.forEach((part, newIdx) => {
          // Find if this part was selected before (by folder name)
          const oldIdx = Object.keys(oldLayers).find(
            (oIdx) => oldLayers[oIdx].folderName === part.folder,
          );

          if (oldIdx !== undefined) {
            const layer = oldLayers[oldIdx];
            layer.sortOrder = part.x * 1000 + newIdx;
            characterLayers[newIdx] = layer;
          }
        });
      }

      // On fresh load, restore previously saved selections from localStorage
      if (!preserveSelection) {
        restoreSelectionState();
      }

      initializeApp(
        preserveSelection || Object.keys(characterLayers).length > 0,
      );
      hideGlobalLoading();

      // Check for missing thumbnails for the current kit
      setTimeout(() => checkMissingThumbnailsForKit(CURRENT_KIT_FOLDER), 500);
      // Check for corrupted images
      setTimeout(() => checkCorruptedImagesForKit(CURRENT_KIT_FOLDER), 600);
      // Check for invalid image filenames (tên sai định dạng)
      setTimeout(() => checkInvalidFilenamesForKit(CURRENT_KIT_FOLDER), 700);
    } else {
      hideGlobalLoading();
      console.error("Error loading kit structure:", result.message);
    }
  } catch (error) {
    hideGlobalLoading();
    console.error("Error loading kit structure:", error);
  }
}

// Initialize app
function initializeApp(preserveSelection = false) {
  if (!kitStructure || kitStructure.length === 0) {
    console.error(
      "No kit structure loaded. The selected kit folder might be empty or in an incorrect format.",
    );
    // Show a user-friendly message in the warning box
    const warningBox = document.getElementById("warning-box");
    if (warningBox) {
      warningBox.style.display = "block";
      warningBox.innerHTML =
        '<div style="color: #ff9800; padding: 10px; border: 1px solid #ff9800; border-radius: 4px; background: rgba(255, 152, 0, 0.1);">' +
        "<strong>⚠️ Thông báo:</strong> Thư mục bộ sưu tập này hiện đang trống hoặc không đúng định dạng (X-Y-Tên-Thư-Mục).</div>";
    }
    // Clear navigation headers
    const navContainer = document.getElementById("nav-icons");
    const countLayer = document.getElementById("count-layer");
    if (navContainer) navContainer.innerHTML = "";
    if (countLayer) countLayer.innerHTML = "";

    // Clear the canvas and UI layers
    resetCharacter();
    renderCharacter();
    return;
  }

  const savedPartIndex = currentPart ? currentPart.index : 0;
  const savedColorIdx = currentColorIndex;

  const navContainer = document.getElementById("nav-icons");
  const countLayer = document.getElementById("count-layer");
  navContainer.innerHTML = "";
  countLayer.innerHTML = "";

  // Prepare indices for sorting to maintain part mapping
  let indices = kitStructure.map((_, i) => i);

  if (partSortType === "x") {
    indices.sort((a, b) => {
      const pA = kitStructure[a];
      const pB = kitStructure[b];
      if (pA.x !== pB.x) return pA.x - pB.x;
      return pA.y - pB.y;
    });
  } else {
    indices.sort((a, b) => {
      const pA = kitStructure[a];
      const pB = kitStructure[b];
      if (pA.y !== pB.y) return pA.y - pB.y;
      return pA.x - pB.x;
    });
  }

  // Filter by Z component
  if (currentZFilter !== "all") {
    indices = indices.filter((index) => {
      const folder = kitStructure[index].folder;
      const match = folder.match(/^\d+-\d+-(\d+)/);
      if (match) return match[1] === currentZFilter;
      // X-Y folders (no Z) are treated as Z=1 when filter is active
      return currentZFilter === "1";
    });
  }

  currentSortedIndices = [...indices];

  indices.forEach((index) => {
    const part = kitStructure[index];
    const navIcon = document.createElement("div");
    navIcon.className = "nav-icon";
    navIcon.dataset.partIndex = index;
    navIcon.dataset.folderName = part.folder;
    navIcon.draggable = true;

    // Drag and Drop Events
    navIcon.addEventListener("dragstart", handleNavDragStart);
    navIcon.addEventListener("dragover", handleNavDragOver);
    navIcon.addEventListener("dragleave", handleNavDragLeave);
    navIcon.addEventListener("drop", handleNavDrop);
    navIcon.addEventListener("dragend", handleNavDragEnd);

    if (part.is_separated) {
      navIcon.classList.add("separated");
      navIcon.title = "Bộ phận này có layer tách";
    }

    const img = document.createElement("img");
    const navBase = `${KIT_PATH}${part.folder}/nav`;

    const tryLoadNav = (imgEl, base, extensions) => {
      let currentExtIdx = 0;
      const tryNext = () => {
        if (currentExtIdx < extensions.length) {
          const ext = extensions[currentExtIdx++];
          imgEl.src = `${base}.${ext}?v=${imgVers}`;
        } else {
          imgEl.style.display = "none";
        }
      };
      imgEl.onerror = tryNext;
      tryNext();
    };

    tryLoadNav(img, navBase, ["png", "webp"]);
    img.alt = part.folder;
    img.loading = "lazy";

    const label = document.createElement("div");
    label.className = "label";
    label.textContent = part.display_name || part.folder;

    navIcon.appendChild(img);
    navIcon.appendChild(label);

    // Highlight if has gaps (Red Dot)
    // Lỗi ở root (missing_images) hoặc ở bất kỳ folder màu nào (color_gaps) đều hiện chấm đỏ ở x-y
    if (
      (part.missing_images && part.missing_images.length > 0) ||
      (part.color_gaps && Object.keys(part.color_gaps).length > 0)
    ) {
      const dot = document.createElement("div");
      dot.className = "gap-badge";
      dot.title = "Bộ phận này bị thiếu file ảnh (xem cảnh báo bên dưới)";
      navIcon.appendChild(dot);
      navIcon.style.borderColor = "#ff7675";
    }

    // Checkbox for bulk merge selection
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "merge-checkbox";
    checkbox.style.position = "absolute";
    checkbox.style.top = "5px";
    checkbox.style.left = "5px";
    checkbox.style.zIndex = "10";
    checkbox.style.width = "18px";
    checkbox.style.height = "18px";
    checkbox.style.cursor = "pointer";
    checkbox.style.display = selectMergeMode ? "block" : "none";
    checkbox.checked = selectedMergeFolders.includes(part.folder);
    checkbox.onclick = (e) => {
      e.stopPropagation();
      handleCheckboxClick(index, checkbox.checked);
    };
    navIcon.appendChild(checkbox);

    // Ctrl + Right-click contextmenu listener
    navIcon.addEventListener("contextmenu", (e) => {
      if (selectMergeMode) {
        e.preventDefault();
        handleRangeSelect(index);
      }
    });

    navIcon.onclick = (e) => {
      if (selectMergeMode) {
        e.stopPropagation();
        const cb = navIcon.querySelector(".merge-checkbox");
        if (cb) {
          cb.checked = !cb.checked;
          handleCheckboxClick(index, cb.checked);
        }
      } else {
        setFocusArea("parts");
        selectPart(index, part);
      }
    };

    navContainer.appendChild(navIcon);

    // Removed auto-select item 1 logic to prevent unwanted selections when resetting/deleting
    if (!characterLayers[index]) {
      characterLayers[index] = {
        folderName: part.folder,
        itemNumber: -1,
        color: "default",
        colorIndex: 0,
        sortOrder: part.x * 1000 + index,
      };
    }
  });

  // Update count to reflect filtered/total view
  const totalCount = kitStructure.length;
  const visibleCount = indices.length;
  countLayer.textContent =
    currentZFilter === "all"
      ? `(${totalCount})`
      : `(${visibleCount}/${totalCount})`;

  // Re-render canvas but keep layers
  renderCharacter();

  // Reselect the part to refresh item grid
  let targetIdx = preserveSelection ? savedPartIndex : 0;

  // If we have a restored active part folder, find its index
  if (restoredActivePartFolder) {
    const foundIdx = kitStructure.findIndex(
      (p) => p.folder === restoredActivePartFolder,
    );
    if (foundIdx !== -1) targetIdx = foundIdx;
    restoredActivePartFolder = null; // Use it only once per fresh load
  }

  if (kitStructure[targetIdx]) {
    selectPart(targetIdx, kitStructure[targetIdx]);
    // Restore color: first try from characterLayers (restored state), then from savedColorIdx
    const restoredLayer = characterLayers[targetIdx];
    if (restoredLayer && restoredLayer.color) {
      const colorIdx = kitStructure[targetIdx].colors.indexOf(
        restoredLayer.color,
      );
      if (colorIdx !== -1) {
        selectColor(restoredLayer.color, colorIdx);
      } else if (kitStructure[targetIdx].colors.length > savedColorIdx) {
        selectColor(
          kitStructure[targetIdx].colors[savedColorIdx],
          savedColorIdx,
        );
      }
    } else if (
      preserveSelection &&
      kitStructure[targetIdx].colors.length > savedColorIdx
    ) {
      selectColor(kitStructure[targetIdx].colors[savedColorIdx], savedColorIdx);
    }
  }
  updateFocusUI(); // Initial focus UI update
}

// Change Part Sort Type
function changePartSort(type) {
  partSortType = type;

  // Update Buttons UI
  document
    .getElementById("sort-x-btn")
    .classList.toggle("active", type === "x");
  document
    .getElementById("sort-y-btn")
    .classList.toggle("active", type === "y");

  // Re-initialize app to re-render nav icons
  initializeApp(true);
}

// Change Z Filter
function changeZFilter(z) {
  currentZFilter = z;
  document.getElementById("z-all-btn").classList.toggle("active", z === "all");
  document.getElementById("z-1-btn").classList.toggle("active", z === "1");
  document.getElementById("z-2-btn").classList.toggle("active", z === "2");
  initializeApp(true);
}

// Global variable to store indices (needed for shift logic)
let currentSortedIndices = [];

// Shift Coordinates (X or Y)
async function shiftCoordinates(delta) {
  if (!currentPart) {
    alert("Vui lòng chọn một bộ phận trước!");
    return;
  }

  const type = partSortType; // 'x' or 'y'
  // Find current position in visual order
  const startPos = currentSortedIndices.indexOf(currentPart.index);
  if (startPos === -1) {
    alert("Không tìm thấy vị trí bộ phận trong danh sách hiển thị.");
    return;
  }

  const renames = [];
  // All parts from startPos to the end of currently visible sorted list
  for (let i = startPos; i < currentSortedIndices.length; i++) {
    const partIdx = currentSortedIndices[i];
    const part = kitStructure[partIdx];

    // Regex matches X-Y-Z or X-Y
    const match = part.folder.match(/^(\d+)-(\d+)(?:-(.*))?$/);
    if (match) {
      let x = parseInt(match[1]);
      let y = parseInt(match[2]);
      const suffix = match[3] ? `-${match[3]}` : "";

      if (type === "x") x += delta;
      else y += delta;

      if (x < 0) x = 0;
      if (y < 0) y = 0;

      const newFolderName = `${x}-${y}${suffix}`;
      if (newFolderName !== part.folder) {
        renames.push({ old: part.folder, new: newFolderName });
      }
    }
  }

  if (renames.length === 0) {
    alert("Không có thay đổi nào cần thực hiện.");
    return;
  }

  const msg = `Bạn có chắc muốn cập nhật ${type.toUpperCase()} (${delta > 0 ? "+" : ""}${delta}) cho các bộ phận từ "${currentPart.part.folder}" về sau (${renames.length} bộ phận)?`;
  if (!confirm(msg)) return;

  try {
    showGlobalLoading("Đang cập nhật chỉ số...");
    const response = await fetch("/api/reorder_parts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kit: CURRENT_KIT_FOLDER, renames }),
    });
    const result = await response.json();
    if (result.success) {
      // Set new folder name for selection restoration
      const selectedRename = renames.find(
        (r) => r.old === currentPart.part.folder,
      );
      if (selectedRename) {
        restoredActivePartFolder = selectedRename.new;
      }

      await loadKitStructure(true);
      // Removed alert to keep it smooth, but could add notification
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (error) {
    console.error("Error shifting coordinates:", error);
    alert("Lỗi kết nối server.");
  } finally {
    hideGlobalLoading();
  }
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
  const activeIcon = document.querySelector(`[data-part-index="${index}"]`);
  if (activeIcon) activeIcon.classList.add("active");

  // Update part name with Rename button
  const nameContainer = document.getElementById("current-part-name");

  nameContainer.innerHTML = `
                ${part.display_name || part.folder}
                <div class="btn-group" style="display:inline-flex; gap:5px; margin-left:8px;">
                     <button class="btn" style="padding:2px 6px; font-size:12px; background:#f1c40f;" onclick="renamePartFolder('${part.folder}')" title="Đổi tên thư mục này (f2)">✎</button>
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

  // Show color thumb toggle only if part has color folders
  const colorThumbLabel = document.getElementById("color-thumb-label");
  if (colorThumbLabel) {
    colorThumbLabel.style.display = part.has_colors ? "inline-flex" : "none";
  }

  // Show thumb control buttons
  document.getElementById("create-part-thumb-btn").style.display = "block";
  document.getElementById("delete-part-thumb-btn").style.display = "block";
  document.getElementById("create-part-nav-btn").style.display = "block";

  // Don't auto-select item - respect current selection or None
  // If this part has a layer, it will be restored by loadItems
  currentItem = characterLayers[index]
    ? characterLayers[index].itemNumber
    : null;

  // Load items
  loadItems(part);

  // Load colors
  loadColors(part);

  // Save state so active part is remembered
  saveSelectionState();
}

// Load items for current part
async function loadItems(part) {
  const itemGrid = document.getElementById("item-grid");
  itemGrid.innerHTML =
    '<div class="loading"><div class="spinner"></div>Đang tải...</div>';

  itemGrid.innerHTML = "";

  // Reset part thumbnail warning
  const partWarning = document.getElementById("part-thumbnail-warning");
  if (partWarning) {
    partWarning.style.display = "none";
    partWarning.innerHTML = "";
  }

  let loadedCount = 0;
  let failedCount = 0;

  const updatePartWarning = () => {
    if (partWarning) {
      if (failedCount > 0) {
        partWarning.innerHTML = `⚠️ Phát hiện <strong>${failedCount}</strong> item thiếu thumbnail trong bộ phận này!`;
        partWarning.style.display = "block";
      } else {
        partWarning.style.display = "none";
      }
    }
  };

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

    // Determine thumb path: trying .png then .webp
    const itemPathBase = `${KIT_PATH}${part.folder}/${itemNum}`;
    const colorItemPathBase =
      currentColor && currentColor !== "default"
        ? `${KIT_PATH}${part.folder}/${currentColor}/${itemNum}`
        : null;

    const thumbPathBase = `${KIT_PATH}${part.folder}/thumb_${itemNum}`;

    // Set initial src to .png and use onerror to fallback to .webp
    const tryLoadImage = (imgEl, base, extensions, finalFallback = null) => {
      let currentExtIdx = 0;
      let hasReported = false;

      const tryNext = () => {
        if (currentExtIdx < extensions.length) {
          const ext = extensions[currentExtIdx++];
          imgEl.src = `${base}.${ext}?v=${imgVers}`;
        } else if (finalFallback) {
          finalFallback();
        } else {
          // Failure: missing thumbnail
          hasReported = true;
          itemDiv.classList.add("missing-thumbnail");
          if (!itemDiv.querySelector(".missing-thumb-label")) {
            const label = document.createElement("div");
            // label.className = "missing-thumb-label";
            // label.textContent = "Thiếu thumb";
            itemDiv.appendChild(label);
          }
          imgEl.onload = null; // Prevent onload from firing for placeholder
          imgEl.src = "img/placeholder.png";
          failedCount++;
          updatePartWarning();
        }
      };

      imgEl.onload = () => {
        if (!hasReported) {
          hasReported = true;
          loadedCount++;
        }
      };

      imgEl.onerror = tryNext;
      tryNext();
    };

    if (showColorThumb && colorItemPathBase) {
      tryLoadImage(img, colorItemPathBase, ["png", "webp"], () => {
        tryLoadImage(img, thumbPathBase, ["png", "webp"]);
      });
    } else {
      tryLoadImage(img, thumbPathBase, ["png", "webp"]);
    }

    img.loading = "lazy";
    itemDiv.appendChild(img);

    // Add Individual Crop Button
    const cropBtn = document.createElement("div");
    cropBtn.className = "item-crop-btn";
    cropBtn.title = "Cắt thumbnail riêng cho ảnh này";
    cropBtn.onclick = (e) => {
      e.stopPropagation();
      openCropThumbnailModal(itemNum);
    };
    itemDiv.appendChild(cropBtn);

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
                <span style="font-weight:bold;">Màu sắc (${colorCount}) <span id="selected-color-count" style="font-weight:normal; font-size: 11px; color: #666; margin-left: 5px;"></span></span>
                <div style="display: flex; gap: 5px;">
                    <button id="fix-all-colors-btn" onclick="fixAllPartColorCodes()" style="padding: 5px 10px; font-size: 11px; cursor: pointer; background: #9b59b6; color: white; border: none; border-radius: 4px;" title="Tự động sửa tên TOÀN BỘ folder màu trong bộ phận này">Fix toàn bộ màu (Q)</button>
                    <button id="reorder-images-btn" onclick="reorderPartImages()" style="padding: 5px 10px; font-size: 11px; cursor: pointer; background: #34495e; color: white; border: none; border-radius: 4px;" title="Sắp xếp lại tên ảnh từ 1 tới N trong các folder (Bỏ qua Thumb/Nav)">Sắp xếp ảnh (W)</button>
                    <button id="fix-colors-by-point-btn" onclick="openColorPickerModal()" style="padding: 5px 10px; font-size: 11px; cursor: pointer; background: #2ecc71; color: white; border: none; border-radius: 4px;" title="Chọn 1 điểm trên ảnh để tự động sửa mã màu cho TOÀN BỘ folder màu khác">Fix theo điểm (E)</button>
                    <button id="rename-color-btn" onclick="renameCurrentColor()" style="display:none; padding: 5px 10px; font-size: 11px; cursor: pointer; background: #3498db; color: white; border: none; border-radius: 4px;">Đổi tên folder</button>
                    <button id="fix-color-btn" onclick="fixCurrentColorCode()" style="display:none; padding: 5px 10px; font-size: 11px; cursor: pointer; background: #9b59b6; color: white; border: none; border-radius: 4px; opacity: 0.8;" title="Tự động sửa tên folder của màu đang chọn">Fix màu này</button>
                    <button id="deselect-colors-btn" onclick="deselectAllColors()" style="padding: 5px 10px; font-size: 11px; cursor: pointer; background: #7f8c8d; color: white; border: none; border-radius: 4px;" title="Bỏ chọn tất cả checkbox">Bỏ chọn (Y)</button>
                    <button id="delete-unselected-colors-btn" onclick="confirmDeleteUnselectedColors()" style="padding: 5px 10px; font-size: 11px; cursor: pointer; background: #f39c12; color: white; border: none; border-radius: 4px;">Xóa màu không chọn (R)</button>
                    <button id="delete-colors-btn" onclick="confirmDeleteColors()" style="padding: 5px 10px; font-size: 11px; cursor: pointer; background: #e74c3c; color: white; border: none; border-radius: 4px;">Xóa màu đã chọn (F)</button>
                </div>
            `;
  editFolderColor.appendChild(controlsDiv);

  const colors = part.colors.length > 0 ? part.colors : ["default"];
  let hasDuplicates = false;

  // Real Hex Comparison Check
  const hexCounts = {};
  colors.forEach((cf) => {
    if (cf === "default") return;
    const hex = getColorHex(cf).toUpperCase();
    hexCounts[hex] = (hexCounts[hex] || 0) + 1;
  });

  // Check if any hex appears more than once
  Object.values(hexCounts).forEach((count) => {
    if (count > 1) hasDuplicates = true;
  });

  if (hasDuplicates) {
    const warning = document.createElement("div");
    warning.id = "duplicate-color-warning";
    warning.innerHTML =
      " <span>Phát hiện mã màu trùng lặp trong bộ phận này</span>";
    colorGrid.appendChild(warning);
  }

  // Check for missing images (Consistency Check)
  // Base maxItems on the actual maximum count found in the color folders
  const counts = Object.values(part.color_image_counts || {});
  // Include root items count but only if it's based on actual images,
  // part.items_count might include metadata, so we might want to be careful.
  // However, for most kits, the root folder is the "default" color source.
  let maxItems =
    counts.length > 0 ? Math.max(...counts) : part.items_count || 0;

  let hasMissingImages = false;
  const missingColorsList = [];

  if (maxItems > 0 && part.color_image_counts) {
    Object.entries(part.color_image_counts).forEach(([cf, count]) => {
      if (count < maxItems) {
        hasMissingImages = true;
        missingColorsList.push({ name: cf, count: count });
      }
    });
  }

  if (hasMissingImages) {
    const missingWarning = document.createElement("div");
    missingWarning.id = "missing-images-warning";
    missingWarning.className = "warning-banner";
    missingWarning.innerHTML = ` <span>Phát hiện ${missingColorsList.length} màu bị thiếu ảnh (chuẩn là ${maxItems} ảnh)</span>`;
    colorGrid.appendChild(missingWarning);
  }

  colors.forEach((colorFolder, index) => {
    const colorDiv = document.createElement("div");
    colorDiv.className = "color-option";

    // Check if this specific folder is a duplicate (by Hex)
    const currentHex = getColorHex(colorFolder).toUpperCase();
    if (colorFolder !== "default" && hexCounts[currentHex] > 1) {
      colorDiv.classList.add("duplicate-color");
      colorDiv.title = `MÀU TRÙNG MÃ: #${currentHex} (${colorFolder})`;
    }

    // Check for missing images in this color
    const itemCount = part.color_image_counts
      ? part.color_image_counts[colorFolder] || 0
      : colorFolder === "default"
        ? part.items_count
        : 0;
    const isMissing = itemCount < maxItems;

    if (isMissing && colorFolder !== "default") {
      colorDiv.classList.add("missing-items");
      const badge = document.createElement("div");
      badge.className = "missing-badge";
      badge.textContent = `${itemCount}/${maxItems}`;
      colorDiv.appendChild(badge);
    }

    colorDiv.dataset.colorIndex = index;
    colorDiv.dataset.colorFolder = colorFolder;

    const hexColor = getColorHex(colorFolder);
    colorDiv.style.background = `#${hexColor}`;
    if (!colorDiv.classList.contains("duplicate-color")) {
      colorDiv.title =
        colorFolder === "default" ? "Màu mặc định" : `#${hexColor}`;
    }

    if (colorFolder === "default") {
      colorDiv.classList.add("default-color");
    }

    // Hàm xử lý chọn dải màu (Range Selection)
    const handleRangeSelection = (idx) => {
      if (lastColorIndex === null) lastColorIndex = idx;
      const start = Math.min(lastColorIndex, idx);
      const end = Math.max(lastColorIndex, idx);

      console.log(`Range selecting (Ctrl+Left): ${start} -> ${end}`);

      const allOptions = colorGrid.querySelectorAll(".color-option");
      allOptions.forEach((opt) => {
        const optionIdx = parseInt(opt.dataset.colorIndex);
        if (optionIdx >= start && optionIdx <= end) {
          const cb = opt.querySelector(".color-checkbox");
          if (cb) {
            cb.checked = true;
            globallySelectedColors.add(opt.dataset.colorFolder);
          }
        }
      });
      updateSelectedColorCount();
    };

    colorDiv.onclick = (e) => {
      setFocusArea("colors");
      if (e.ctrlKey) {
        handleRangeSelection(index);
      } else {
        selectColor(colorFolder, index);
      }
    };

    if (colorFolder !== "default") {
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.className = "color-checkbox";
      checkbox.name = "color-to-delete";
      checkbox.value = colorFolder;
      checkbox.checked = globallySelectedColors.has(colorFolder);
      checkbox.onclick = (e) => {
        e.stopPropagation(); // Vẫn chặn để không kích hoạt selectColor của màu
        if (e.ctrlKey) {
          handleRangeSelection(index);
        } else {
          lastColorIndex = index; // Cập nhật mốc khi tích checkbox bình thường
          if (checkbox.checked) {
            globallySelectedColors.add(colorFolder);
          } else {
            globallySelectedColors.delete(colorFolder);
          }
        }
        updateSelectedColorCount();
      };
      checkbox.title = "Chọn để xóa (D)";
      colorDiv.appendChild(checkbox);
    }

    // Highlight color folder if it has gaps
    if (part.color_gaps && part.color_gaps[colorFolder]) {
      const dot = document.createElement("div");
      dot.className = "gap-badge";
      dot.title = `Thiếu ảnh: ${part.color_gaps[colorFolder].join(", ")}`;
      colorDiv.appendChild(dot);
      colorDiv.style.borderColor = "#ff7675";
    }

    // Image count badge (bottom-left)
    if (
      colorFolder !== "default" &&
      part.color_image_counts &&
      part.color_image_counts[colorFolder] !== undefined
    ) {
      const countBadge = document.createElement("div");
      countBadge.className = "color-count-badge";
      countBadge.textContent = part.color_image_counts[colorFolder];
      countBadge.title = `${part.color_image_counts[colorFolder]} ảnh trong folder màu này`;
      colorDiv.appendChild(countBadge);
    }

    colorGrid.appendChild(colorDiv);
  });

  // (Đã chuyển sang Ctrl + Chuột trái ở trên)

  // Show/Hide Delete Button
  document.getElementById("delete-colors-btn").style.display =
    part.colors.length > 0 ? "block" : "none";

  // Initial count update
  updateSelectedColorCount();

  // Restore previously selected color or default to first
  const savedLayer = currentPart ? characterLayers[currentPart.index] : null;
  if (savedLayer && savedLayer.color && colors.includes(savedLayer.color)) {
    selectColor(savedLayer.color, colors.indexOf(savedLayer.color));
  } else if (colors.length > 0) {
    selectColor(colors[0], 0);
  }
}

// Logic chọn điểm lấy màu
let selectedPointCoords = null;
let selectedColorPickerFilename = "1.png";

function openColorPickerModal() {
  if (!currentPart) return;

  const modal = document.getElementById("color-picker-modal");
  const img = document.getElementById("color-picker-img");
  const marker = document.getElementById("color-picker-marker");
  const info = document.getElementById("color-picker-info");
  const confirmBtn = document.getElementById("confirm-fix-by-point-btn");

  modal.style.display = "flex";
  marker.style.display = "none";
  confirmBtn.disabled = true;
  info.textContent = "Đang tải ảnh...";
  selectedPointCoords = null;

  // Xác định tên tệp ảnh dựa trên Item đang chọn
  selectedColorPickerFilename =
    currentItem && currentItem > 0 ? `${currentItem}.png` : "1.png";

  // Lấy ảnh mẫu
  const colorFolder = currentColor || "default";
  let sampleImagePath = "";

  if (colorFolder === "default") {
    sampleImagePath = `${KIT_PATH}${currentPart.part.folder}/${selectedColorPickerFilename}`;
  } else {
    sampleImagePath = `${KIT_PATH}${currentPart.part.folder}/${colorFolder}/${selectedColorPickerFilename}`;
  }

  img.src = `${sampleImagePath}?v=${imgVers}`;

  img.onload = () => {
    info.textContent = `Vui lòng click vào một điểm trên ảnh ${selectedColorPickerFilename} (${img.naturalWidth}x${img.naturalHeight}px).`;
    img.onclick = (e) => handleColorPickerClick(e, img);
  };

  img.onerror = () => {
    if (selectedColorPickerFilename !== "1.png") {
      console.log(
        `Không tìm thấy ${selectedColorPickerFilename}, thử lại với 1.png`,
      );
      selectedColorPickerFilename = "1.png";
      if (colorFolder === "default") {
        sampleImagePath = `${KIT_PATH}${currentPart.part.folder}/1.png`;
      } else {
        sampleImagePath = `${KIT_PATH}${currentPart.part.folder}/${colorFolder}/1.png`;
      }
      img.src = `${sampleImagePath}?v=${imgVers}`;
      return;
    }
    info.textContent = `Không tìm thấy tệp ảnh làm mẫu (${selectedColorPickerFilename}).`;
    img.src = "img/placeholder.png";
  };
}

function handleColorPickerClick(e, imgEl) {
  const rect = imgEl.getBoundingClientRect();
  const offsetX = e.clientX - rect.left;
  const offsetY = e.clientY - rect.top;

  // Calculate original coordinates
  const scaleX = imgEl.naturalWidth / rect.width;
  const scaleY = imgEl.naturalHeight / rect.height;

  const originalX = Math.round(offsetX * scaleX);
  const originalY = Math.round(offsetY * scaleY);

  selectedPointCoords = { x: originalX, y: originalY };

  // UI Update
  const marker = document.getElementById("color-picker-marker");
  marker.style.left = `${offsetX}px`;
  marker.style.top = `${offsetY}px`;
  marker.style.display = "block";

  const confirmBtn = document.getElementById("confirm-fix-by-point-btn");
  confirmBtn.disabled = false;

  const info = document.getElementById("color-picker-info");
  info.textContent = `Đã chọn tọa độ: X=${originalX}, Y=${originalY} | File: ${selectedColorPickerFilename}`;
}

function closeColorPickerModal() {
  document.getElementById("color-picker-modal").style.display = "none";
}

async function confirmFixColorsByPoint() {
  if (!currentPart || !selectedPointCoords) return;

  if (
    !confirm(
      `Bạn có chắc chắn muốn lấy mã màu tại điểm (${selectedPointCoords.x}, ${selectedPointCoords.y}) của tệp "1.png" để sửa tên cho TOÀN BỘ folder màu trong bộ phận "${currentPart.part.folder}"?`,
    )
  ) {
    return;
  }

  closeColorPickerModal();
  showGlobalLoading("Đang xử lý đổi tên theo điểm chọn...");

  try {
    const response = await fetch("/api/fix_colors_by_point", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        part_folder: currentPart.part.folder,
        x: selectedPointCoords.x,
        y: selectedPointCoords.y,
        filename: selectedColorPickerFilename,
      }),
    });

    const result = await response.json();
    if (result.success) {
      // Reload structure to see changes
      await switchKit(CURRENT_KIT_FOLDER);

      let msg = `Thành công! Đã đổi tên ${result.processed_count} thư mục màu.`;
      if (result.errors && result.errors.length > 0) {
        msg += `\nLưu ý các lỗi: \n- ${result.errors.join("\n- ")}`;
      }
      alert(msg);
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (e) {
    alert("Lỗi kết nối server: " + e);
  } finally {
    hideGlobalLoading();
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
    characterLayers[currentPart.index] = {
      folderName: currentPart.part.folder,
      itemNumber: -1,
      color: currentColor || "default",
      colorIndex: currentColorIndex || 0,
      sortOrder: currentPart.part.x * 1000 + currentPart.index,
    };
    renderCharacter();
    saveSelectionState();
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

  // Save state for persistence across reloads
  saveSelectionState();
}

// Select color
function selectColor(colorFolder, colorIndex) {
  currentColor = colorFolder;
  currentColorIndex = colorIndex !== undefined ? colorIndex : 0;
  lastColorIndex = currentColorIndex; // Cập nhật mốc chọn màu

  document.querySelectorAll(".color-option").forEach((color) => {
    color.classList.remove("active");
  });

  const option = document.querySelector(`[data-color-folder="${colorFolder}"]`);
  if (option) option.classList.add("active");

  // Handle Rename Button Visibility
  const renameBtn = document.getElementById("rename-color-btn");
  const fixColorBtn = document.getElementById("fix-color-btn");
  if (renameBtn) {
    if (colorFolder && colorFolder !== "default") {
      renameBtn.style.display = "block";
      renameBtn.title = `Đổi tên folder: ${colorFolder}`;
      if (fixColorBtn) {
        fixColorBtn.style.display = "block";
        fixColorBtn.textContent = "Fix màu này"; // Distinguish from 'all'
      }
    } else {
      renameBtn.style.display = "none";
      if (fixColorBtn) fixColorBtn.style.display = "none";
    }
  }

  // Reload item grid thumbnails when color-thumb mode is active
  if (showColorThumb && currentPart) {
    loadItems(currentPart.part);
  }

  updateCharacter();

  // Save state for persistence across reloads
  saveSelectionState();
}

// Rename Current Color Logic
async function renameCurrentColor() {
  if (!currentPart || !currentColor || currentColor === "default") return;
  openRenameModal(currentColor, "color");
}

let renameModalTarget = null; // { type: 'part'|'color', oldName: string }

function openRenameModal(oldName, type) {
  renameModalTarget = { type, oldName };
  document.getElementById("rename-old-name").textContent = oldName;
  const input = document.getElementById("rename-new-input");
  input.value = oldName;
  document.getElementById("rename-modal-title").textContent =
    type === "part" ? "Đổi tên bộ phận (X-Y-Z)" : "Đổi tên mã màu";
  document.getElementById("rename-modal-overlay").style.display = "flex";

  setTimeout(() => {
    input.focus();
    input.select();
  }, 100);
}

function closeRenameModal() {
  document.getElementById("rename-modal-overlay").style.display = "none";
}

async function confirmRenameModal() {
  const newName = document.getElementById("rename-new-input").value.trim();
  if (!newName || !renameModalTarget) return;

  const { type, oldName } = renameModalTarget;
  if (newName === oldName) {
    closeRenameModal();
    return;
  }

  closeRenameModal();

  if (type === "part") {
    await executeRenamePartFolder(oldName, newName);
  } else {
    await executeRenameColorFolder(oldName, newName);
  }
}

async function executeRenamePartFolder(oldName, newName) {
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

async function executeRenameColorFolder(oldName, newName) {
  showLoading("Đang đổi tên màu...");
  try {
    const response = await fetch("/api/rename_color_folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        part_folder: currentPart.part.folder,
        old_color: oldName,
        new_color: newName,
      }),
    });

    const result = await response.json();
    if (result.success) {
      const index = currentPart.part.colors.indexOf(oldName);
      if (index !== -1) currentPart.part.colors[index] = newName;
      if (
        characterLayers[currentPart.index] &&
        characterLayers[currentPart.index].color === oldName
      ) {
        characterLayers[currentPart.index].color = newName;
      }
      loadColors(currentPart.part);
      setTimeout(() => selectColor(newName, index), 50);
      renderCharacter();
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (e) {
    alert("Lỗi server: " + e);
  } finally {
    hideLoading();
  }
}

// Fix Current Color Code Automatically
async function fixCurrentColorCode() {
  if (!currentPart || !currentColor || currentColor === "default") return;

  showLoading(true, `Đang phân tích màu trong folder "${currentColor}"...`);

  try {
    const response = await fetch("/api/fix_color_code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        part_folder: currentPart.part.folder,
        color: currentColor,
      }),
    });

    const result = await response.json();
    if (result.success) {
      if (result.new_name) {
        const oldName = currentColor;
        const newName = result.new_name;

        // Update local data
        const index = currentPart.part.colors.indexOf(oldName);
        if (index !== -1) {
          currentPart.part.colors[index] = newName;
        }

        // Update characterLayers
        if (
          characterLayers[currentPart.index] &&
          characterLayers[currentPart.index].color === oldName
        ) {
          characterLayers[currentPart.index].color = newName;
        }

        // Re-load UI
        loadColors(currentPart.part);
        setTimeout(() => selectColor(newName, index), 50);
        renderCharacter();

        console.log(
          `Đã sửa mã màu: ${oldName} -> ${newName} (${result.detected})`,
        );
      } else {
        alert(result.message);
      }
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (e) {
    alert("Lỗi kết nối: " + e);
  } finally {
    hideLoading();
  }
}

// Fix ALL color codes in current part
async function fixAllPartColorCodes() {
  if (!currentPart) return;

  if (
    !confirm(
      `Bạn có chắc chắn muốn quét và tự động sửa tên TOÀN BỘ (${currentPart.part.colors.length}) folder màu trong bộ phận "${currentPart.part.folder}"?`,
    )
  ) {
    return;
  }

  showLoading(
    true,
    `Đang xử lý toàn bộ folder màu của "${currentPart.part.folder}"...`,
  );

  try {
    const response = await fetch("/api/fix_all_part_colors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        part_folder: currentPart.part.folder,
      }),
    });

    const result = await response.json();
    if (result.success) {
      if (result.processed_count > 0) {
        // Success with changes
        await switchKit(CURRENT_KIT_FOLDER); // This re-fetches everything

        let msg = `Đã sửa xong ${result.processed_count} mã màu.`;
        if (result.errors && result.errors.length > 0) {
          msg += `\nLỗi tại: ${result.errors.join(", ")}`;
        }
        alert(msg);
      } else {
        alert("Tất cả mã màu đều đã chính xác!");
      }
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (e) {
    alert("Lỗi kết nối: " + e);
  } finally {
    hideLoading();
  }
}

// Reorder images (1 to N) in current part
async function reorderPartImages() {
  if (!currentPart) return;

  if (
    !confirm(
      `Bạn có chắc muốn sắp xếp lại tên ảnh (từ 1 tới N) cho toàn bộ thư mục trong bộ phận "${currentPart.part.folder}"?\n` +
      `- Sẽ tự động bỏ qua các ảnh thumbnail và nav.png.\n` +
      `- Thao tác này sẽ thay đổi tên tệp thực tế trên server.`,
    )
  ) {
    return;
  }

  showLoading(true, `Đang sắp xếp lại ảnh cho "${currentPart.part.folder}"...`);

  try {
    const response = await fetch("/api/reorder_images", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        part_folder: currentPart.part.folder,
      }),
    });

    const result = await response.json();
    if (result.success) {
      // Reload kit structure to reflect new numbering
      await loadKitStructure(true);
      alert(result.message);
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (e) {
    alert("Lỗi kết nối: " + e);
  } finally {
    hideLoading();
  }
}

async function confirmDeleteColors() {
  const checkboxes = document.querySelectorAll(".color-checkbox:checked");
  const colorsToDelete = Array.from(checkboxes).map((cb) => cb.value);

  if (colorsToDelete.length === 0) {
    alert(
      "Vui lòng tích chọn ít nhất một màu (ô vuông nhỏ trên vòng tròn màu) để xóa.",
    );
    return;
  }

  if (
    !confirm(
      `Bạn có chắc chắn muốn xóa ${colorsToDelete.length} folder màu sắc đã chọn trực tiếp khỏi bộ phận này? Thao tác này không thể hoàn tác.`,
    )
  ) {
    return;
  }

  await performDeleteColors(colorsToDelete);
}
// Bỏ chọn tất cả màu của bộ phận đang chọn
function deselectAllColors() {
  const allCheckboxes = document.querySelectorAll(".color-checkbox");
  allCheckboxes.forEach((cb) => {
    cb.checked = false;
  });
  updateSelectedColorCount();
}

// Xóa màu KHÔNG chọn
async function confirmDeleteUnselectedColors() {
  const allCheckboxes = document.querySelectorAll(".color-checkbox");
  const unselectedColors = Array.from(allCheckboxes)
    .filter((cb) => !cb.checked)
    .map((cb) => cb.value);

  if (unselectedColors.length === 0) {
    alert("Tất cả các màu đã được chọn, không có gì để xóa!");
    return;
  }

  if (
    !confirm(
      `Bạn có chắc chắn muốn xóa ${unselectedColors.length} folder màu sắc KHÔNG được chọn? Thao tác này không thể hoàn tác.`,
    )
  ) {
    return;
  }

  await performDeleteColors(unselectedColors);
}

// Core deletion logic
async function performDeleteColors(colorsToDelete) {
  showLoading(true, "Đang xóa các folder màu sắc...");

  try {
    const response = await fetch("/api/delete_color_folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        part_folder: currentPart.part.folder,
        colors: colorsToDelete,
      }),
    });

    const result = await response.json();
    if (result.success) {
      // Update local data
      currentPart.part.colors = currentPart.part.colors.filter(
        (c) => !colorsToDelete.includes(c),
      );

      // If current color was deleted, switch to default
      if (colorsToDelete.includes(currentColor)) {
        currentColor = "default";
        currentColorIndex = 0;
      }

      loadColors(currentPart.part);
      renderCharacter();
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (e) {
    alert("Lỗi kết nối: " + e);
  } finally {
    hideLoading();
  }
}

// Cập nhật số lượng màu đã chọn
function updateSelectedColorCount() {
  const countSpan = document.getElementById("selected-color-count");
  const clearBtn = document.getElementById("clear-global-colors-btn");
  if (!countSpan) return;

  // Số lượng mã màu trong bộ phận hiện tại khớp với danh sách chọn toàn cục
  const localChecked = document.querySelectorAll(
    ".color-checkbox:checked",
  ).length;
  const globalCount = globallySelectedColors.size;

  if (globalCount > 0) {
    countSpan.textContent = `- Đã chọn: ${localChecked} / ${globalCount} màu`;
    if (clearBtn) clearBtn.style.display = "block";
  } else {
    countSpan.textContent = "";
    if (clearBtn) clearBtn.style.display = "none";
  }
}

// Bỏ chọn tất cả màu đã chọn toàn cục
function clearGloballySelectedColors() {
  globallySelectedColors.clear();

  // Bỏ tích tất cả checkbox đang hiển thị
  const checkboxes = document.querySelectorAll(".color-checkbox");
  checkboxes.forEach((cb) => (cb.checked = false));

  updateSelectedColorCount();
}

// Copy danh sách mã màu đang chọn vào Clipboard
function copySelectedColorCodes() {
  if (globallySelectedColors.size === 0) {
    alert("Chưa có màu nào được chọn để copy!");
    return;
  }

  const codes = Array.from(globallySelectedColors).join(", ");
  navigator.clipboard
    .writeText(codes)
    .then(() => {
      alert(`✅ Đã copy ${globallySelectedColors.size} mã màu vào bộ nhớ tạm.`);
    })
    .catch((err) => {
      console.error("Lỗi copy:", err);
      // Fallback nếu clipboard API lỗi
      const tempInput = document.createElement("input");
      tempInput.value = codes;
      document.body.appendChild(tempInput);
      tempInput.select();
      document.execCommand("copy");
      document.body.removeChild(tempInput);
      alert("✅ Đã copy mã màu (fallback).");
    });
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
    if (itemNumber === -1) return null;

    let imagePathBase;
    if (color === "default" || !color) {
      imagePathBase = `${KIT_PATH}${folderName}/${itemNumber}`;
    } else {
      imagePathBase = `${KIT_PATH}${folderName}/${color}/${itemNumber}`;
    }

    try {
      // Thử tải .png trước, nếu lỗi thử .webp
      return await loadImageWithFallback(imagePathBase, ["png", "webp"]);
    } catch (error) {
      console.error(`Failed to load: ${imagePathBase}`);
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

// Hàm hỗ trợ tải ảnh với fallback đuôi mở rộng
async function loadImageWithFallback(basePath, extensions) {
  for (const ext of extensions) {
    try {
      return await loadImage(`${basePath}.${ext}?v=${imgVers}`);
    } catch (e) {
      // Tiếp tục thử đuôi tiếp theo
    }
  }
  throw new Error(`All extensions failed for ${basePath}`);
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
  document.getElementById("current-part-name").textContent = "Chọn một bộ phận";
}

// Reset all layers (select None for all parts)
function resetAllLayers() {
  characterLayers = {};
  if (kitStructure) {
    kitStructure.forEach((part, index) => {
      characterLayers[index] = {
        folderName: part.folder,
        itemNumber: -1,
        color: "default",
        colorIndex: 0,
        sortOrder: part.x * 1000 + index,
      };
    });
  }
  renderCharacter();
  saveSelectionState();

  // Update UI
  if (currentPart) selectPart(currentPart.index, currentPart.part);

  // Update UI to show all items as "None"
  document.querySelectorAll(".item-option").forEach((item) => {
    item.classList.remove("active");
  });
  document.querySelectorAll(".item-none").forEach((none) => {
    none.classList.add("active");
  });
}

// Randomize character
async function randomizeCharacter() {
  if (!kitStructure || kitStructure.length === 0) return;

  // Randomize each part
  for (let partIndex = 0; partIndex < kitStructure.length; partIndex++) {
    const part = kitStructure[partIndex];
    if (part.items_count === 0) continue;

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

async function downloadZip() {
  if (!CURRENT_KIT_FOLDER) {
    alert("Vui lòng chọn một bộ sưu tập trước!");
    return;
  }

  if (
    !confirm(
      `Bạn muốn tải xuống "Data ZIP" của "${CURRENT_KIT_FOLDER}"?\n\nLưu ý: Quá trình nén có thể mất vài chục giây tùy dung lượng.`,
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
async function showFolderFiles(selectedColor) {
  if (!currentPart) return;

  const modal = document.getElementById("file-debug-modal");
  const isOpening = modal.style.display !== "flex";
  if (isOpening) {
    currentDebugColor = null;
  }

  const grid = document.getElementById("file-debug-grid");
  const subtitle = document.getElementById("file-debug-subtitle");
  const listcoloritems = document.getElementById("list-color-items");
  listcoloritems.innerHTML = "";
  modal.style.display = "flex";
  grid.innerHTML = "";
  debugSelectedIds.clear();
  updateDebugSelectionUI();
  subtitle.textContent = `Đang tải danh sách file cho part: ${currentPart.part.name} (${currentPart.part.folder})...`;

  try {
    // Determine color
    let colorParam = selectedColor;
    if (!colorParam && currentDebugColor) {
      colorParam = currentDebugColor;
    }
    if (!colorParam) {
      // Let's try to query the active color button in the UI
      const activeColorBtn = document.querySelector(".color-btn.active");
      colorParam = activeColorBtn ? activeColorBtn.dataset.color : null;
      // Fix: Check if color param is actually valid (not undefined/null string due to dataset issue)
      // The dataset attribute is data-color-folder in loadColors function
      const activeColorOption = document.querySelector("#color-grid .color-option.active");
      if (activeColorOption) {
        colorParam = activeColorOption.dataset.colorFolder;
      }
    }

    currentDebugColor = colorParam;

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

      subtitle.textContent = `Folder: ${currentPart.part.folder} ${colorParam ? "/ " + colorParam : ""}`;

      if (result.files.length === 0) {
        grid.innerHTML =
          '<p style="grid-column: 1/-1; text-align: center; color: #888;">Thư mục trống</p>';
        return;
      }

      // Group files by Item ID (e.g. "1") or "nav"
      const groups = {}; // { '1': { main: file, thumb: file }, 'nav': { main: file } }
      const others = [];

      currentPart.part.colors.forEach((color) => {
        const itemCount = currentPart.part.color_image_counts
          ? currentPart.part.color_image_counts[color] || 0
          : 0;
        const isActive = (color === currentDebugColor) ? "active" : "";
        listcoloritems.innerHTML +=
          `
           <div class="color-option ${isActive}" onclick="switchColor('${color}')" data-color-index="0" data-color-folder="${color}" title="#${color}"
            style="background: #${color};">
            <div class="color-count-badge" title="${itemCount} ảnh trong folder màu này">${itemCount}</div>
          </div>
        `
      });


      result.files.forEach((file) => {
        // Check for Main Image: "1.png" or "1.webp"
        if (file.name.match(/^\d+\.(png|webp)$/)) {
          const id = file.name.split(".")[0];
          if (!groups[id]) groups[id] = {};
          groups[id].main = file;
        }
        // Check for Thumb Image: "thumb_1.png" or "thumb_1.webp"
        else if (file.name.match(/^thumb_\d+\.(png|webp)$/)) {
          const id = file.name.split(".")[0].replace("thumb_", "");
          if (!groups[id]) groups[id] = {};
          groups[id].thumb = file;
        }
        // Check for nav.png (keeping as is or could support nav.webp)
        else if (file.name === "nav.png" || file.name === "nav.webp") {
          if (!groups["nav"]) groups["nav"] = {};
          groups["nav"].main = file;
        } else {
          others.push(file);
        }
      });

      // Clear grid but set up layout
      grid.style.display = "block";
      grid.innerHTML = `
                        <div style="display: flex; gap: 20px; align-items: flex-start; margin-top:10px;align-items: start;">
                            <div id="debug-main-list" style="align-items: start;flex: 10; display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 15px;overflow-y: scroll;height: calc(100dvh - 200px);"></div>
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
            "padding: 10px; border-radius: 8px; display: flex; flex-direction: column; align-items: center; gap: 5px; width: 100%;";

          navContainer.innerHTML += `
            <div style="display:flex; justify-content:space-between; width:100%; align-items:center; margin-bottom:5px;">
                <div style="font-weight:bold; opacity: 0.7;">NAV ICON</div>
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
          "padding: 10px; border-radius: 8px; display: flex; flex-direction: row; align-items: center; justify-content: space-around; gap: 10px;";

        container.onclick = (e) => {
          if (id !== "nav") {
            toggleDebugSelection(id, e);
          }
        };

        // Main Slot
        if (group.main) {
          container.innerHTML += `
                                <div class="file-debug-slot main-slot" title="${group.main.name}" 
                                     draggable="true" ondragstart="handleDragStart(event, '${group.main ? group.main.name : ""}')"
                                     style="flex:1; display:flex; flex-direction:column; align-items:center; cursor:grab;">
                                    <img src="${group.main.url}?v=${timestamp}" style="width: 100%; height: 80px; object-fit: contain; pointer-events: none;">
                                    <span style="font-size:12px;">${group.main.name}</span>
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
                                    <span style="font-size:12px;">${thumbName}</span>
                                    
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
          "padding: 10px; border-radius: 8px; display: flex; flex-direction: column; align-items: center;";
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

let lastDebugSelectedId = null;

function toggleDebugSelection(id, event) {
  // Get all IDs in the current visual order to handle ranges
  const groups = Array.from(document.querySelectorAll(".file-debug-group"));
  const idsInOrder = groups
    .map((g) => g.dataset.id)
    .filter((did) => did && did !== "nav");

  if (event.shiftKey && lastDebugSelectedId !== null) {
    const start = idsInOrder.indexOf(lastDebugSelectedId);
    const end = idsInOrder.indexOf(id);

    if (start !== -1 && end !== -1) {
      const low = Math.min(start, end);
      const high = Math.max(start, end);
      // Select everything in the range
      for (let i = low; i <= high; i++) {
        debugSelectedIds.add(idsInOrder[i]);
      }
    }
  } else if (event.ctrlKey) {
    // Toggle individual
    if (debugSelectedIds.has(id)) {
      debugSelectedIds.delete(id);
    } else {
      debugSelectedIds.add(id);
    }
  } else {
    // Single click: clear and select
    debugSelectedIds.clear();
    debugSelectedIds.add(id);
  }

  lastDebugSelectedId = id;
  updateDebugSelectionUI();
}
function switchColor(color) {
  currentDebugColor = color;
  showFolderFiles(color);
}
function updateDebugSelectionUI() {
  const groups = document.querySelectorAll(".file-debug-group");
  groups.forEach((group) => {
    const id = group.dataset.id;
    if (debugSelectedIds.has(id)) {
      group.classList.add("selected");
    } else {
      group.classList.remove("selected");
    }
  });

  const deleteBtn = document.getElementById("delete-selected-btn");
  const countSpan = document.getElementById("selected-count");
  if (deleteBtn && countSpan) {
    if (debugSelectedIds.size > 0) {
      deleteBtn.style.display = "block";
      countSpan.textContent = debugSelectedIds.size;
    } else {
      deleteBtn.style.display = "none";
    }
  }
}

async function deleteSelectedImages() {
  if (!currentPart || debugSelectedIds.size === 0) return;

  const applyAllCheck = document.getElementById("batch-delete-all-check");
  const applyAll = applyAllCheck ? applyAllCheck.checked : true;
  const indices = Array.from(debugSelectedIds)
    .map((id) => parseInt(id))
    .filter((n) => !isNaN(n))
    .sort((a, b) => a - b);

  if (indices.length === 0) return;

  const targetDesc = applyAll
    ? "TẤT CẢ thư mục màu"
    : `folder [${currentDebugColor || currentColor || "Main"}]`;
  if (
    !confirm(
      `Bạn chắc chắn muốn XÓA VĨNH VIỄN ${indices.length} ảnh đã chọn trong ${targetDesc} và sắp xếp lại?\n(Các thumbnail liên quan cũng sẽ bị xóa)`,
    )
  )
    return;

  showLoading(`Đang xóa ${indices.length} ảnh và sắp xếp lại...`);

  try {
    const response = await fetch("/api/batch_delete_reorder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        folder: currentPart.part.folder,
        indices: indices,
        apply_all: applyAll,
        color: currentDebugColor || currentColor,
      }),
    });

    const result = await response.json();
    if (result.success) {
      debugSelectedIds.clear();
      await showFolderFiles();
      await loadKitStructure(true);
      alert(result.message);
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (e) {
    alert("Lỗi server: " + e);
  } finally {
    hideLoading();
  }
}

async function createThumbnail(sourceName, targetName) {
  // if(!confirm(`Tạo thumbnail ${targetName} từ ${sourceName}?`)) return;

  // showLoading('Đang tạo thumbnail...');
  // User removed showLoading, keeping commented out

  try {
    // Get params again
    let colorParam = currentDebugColor;
    if (!colorParam) {
      const activeColorBtn = document.querySelector(".color-btn.active");
      colorParam = activeColorBtn ? activeColorBtn.dataset.color : null;
      const activeColorOption = document.querySelector(".color-option.active");
      if (activeColorOption) {
        colorParam = activeColorOption.dataset.colorFolder;
      }
    }

    // Derive ID from targetName (thumb_X.png or thumb_X.webp)
    let id = targetName.replace("thumb_", "").split(".")[0];

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
                                <span style="color:white; font-size:12px;">${targetName}</span>
                                
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
    let colorParam = currentDebugColor;
    if (!colorParam) {
      const activeColorBtn = document.querySelector(".color-btn.active");
      colorParam = activeColorBtn ? activeColorBtn.dataset.color : null;
      const activeColorOption = document.querySelector(".color-option.active");
      if (activeColorOption) colorParam = activeColorOption.dataset.colorFolder;
    }

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
      if (filename === "nav.png" || filename === "nav.webp") {
        showFolderFiles();
        return;
      }

      if (filename.startsWith("thumb_")) {
        let id = filename.replace("thumb_", "").split(".")[0];
        const container = document.querySelector(
          `.file-debug-group[data-id="${id}"]`,
        );
        if (container) {
          const thumbSlot = container.querySelector(".thumb-slot");
          if (thumbSlot) {
            const mainNameSpan = container.querySelector(".main-slot span");
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
        let id = filename.split(".")[0];
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
    let colorParam = currentDebugColor;
    if (!colorParam) {
      const activeColorBtn = document.querySelector(".color-btn.active");
      colorParam = activeColorBtn ? activeColorBtn.dataset.color : null;
      const activeColorOption = document.querySelector(".color-option.active");
      if (activeColorOption) colorParam = activeColorOption.dataset.colorFolder;
    }

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
      let colorParam = currentDebugColor;
      if (!colorParam) {
        const activeColorBtn = document.querySelector(".color-btn.active");
        colorParam = activeColorBtn ? activeColorBtn.dataset.color : null;
        const activeColorOption = document.querySelector(".color-option.active");
        if (activeColorOption) colorParam = activeColorOption.dataset.colorFolder;
      }

      const response = await fetch("/api/upload_file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          kit: CURRENT_KIT_FOLDER,
          folder: currentPart.part.folder,
          filename: file.name.startsWith("nav") ? file.name : "nav.png", // Keep original if it's a nav file, otherwise default to png
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

// Batch delete and reorder images
async function batchDeleteAndReorder() {
  if (!currentPart) return;

  const input = document.getElementById("batch-delete-input");
  const applyAllCheck = document.getElementById("batch-delete-all-check");
  const value = input.value.trim();
  const applyAll = applyAllCheck ? applyAllCheck.checked : true;

  if (!value) {
    alert("Vui lòng nhập các số cần xóa (VD: 1, 3, 4)");
    return;
  }

  // Parse input (1, 3, 5-10 or 1;3;5-10)
  let indices = [];
  const cleanedValue = value.replace(/\s*-\s*/g, "-");
  const segments = cleanedValue.split(/[\s,;]+/);

  segments.forEach((seg) => {
    if (seg.includes("-")) {
      const parts = seg.split("-");
      if (parts.length === 2) {
        const start = parseInt(parts[0]);
        const end = parseInt(parts[1]);
        if (!isNaN(start) && !isNaN(end)) {
          const low = Math.min(start, end);
          const high = Math.max(start, end);
          for (let i = low; i <= high; i++) {
            indices.push(i);
          }
        }
      }
    } else {
      const num = parseInt(seg);
      if (!isNaN(num)) indices.push(num);
    }
  });

  // Deduplicate and sort
  indices = [...new Set(indices)].sort((a, b) => a - b);

  if (indices.length === 0) {
    alert("Danh sách số không hợp lệ.");
    return;
  }

  const targetDesc = applyAll
    ? "TẤT CẢ thư mục màu"
    : `folder [${currentDebugColor || currentColor || "Main"}]`;
  if (
    !confirm(
      `Bạn chắc chắn muốn XÓA VĨNH VIỄN các ảnh [${indices.join(", ")}] trong ${targetDesc} và sắp xếp lại?`,
    )
  )
    return;

  showLoading(`Đang xóa ${indices.length} ảnh và sắp xếp lại...`);

  try {
    const response = await fetch("/api/batch_delete_reorder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        folder: currentPart.part.folder,
        indices: indices,
        apply_all: applyAll,
        color: currentDebugColor || currentColor,
      }),
    });

    const result = await response.json();
    if (result.success) {
      // Clear input
      input.value = "";
      // Refresh file list modal
      await showFolderFiles();
      // Reload kit structure to update warnings if numbers changed
      await loadKitStructure(true); // preserveSelection = true
      alert(result.message);
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (e) {
    alert("Lỗi server: " + e);
  } finally {
    hideLoading();
  }
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
  document.getElementById("global-loading-overlay").style.display = "flex";
}

function hideLoading() {
  document.getElementById("global-loading-overlay").style.display = "none";
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
let mergeQueue = [];
let mergeFilesList = [];
let mergeCanvas, mctx;

async function renamePartFolder(oldName) {
  openRenameModal(oldName, "part");
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
  mergeQueue = [];
  document.getElementById("merge-stack-list").innerHTML = "";
  const queueList = document.getElementById("merge-queue-list");
  if (queueList) queueList.innerHTML = "";
  document.getElementById("merge-dest-name").value = "1";
  const processBtn = document.getElementById("process-queue-btn");
  if (processBtn) processBtn.disabled = true;

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
    div.innerHTML = `
            <img src="${baseUrl}${filename}?v=${imgVers}" title="${filename}">
            <div style="font-size: 10px; color: #666; word-break: break-all; margin-top: 2px; text-align: center;">${filename}</div>
        `;
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
    document.getElementById("color-picker").value = "#" + adj.target_color;
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
        let drawableSource = img;

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
          drawableSource = tempCanvas;
        }

        // Standardize rendering behavior to match the main view (renderCharacter)
        // This ensures that positioning is identical between the main canvas and the merge modal.
        mctx.drawImage(
          drawableSource,
          0,
          0,
          mergeCanvas.width,
          mergeCanvas.height,
        );

        resolve();
      };
      img.onerror = resolve;
    });
  }
}

function toggleCropBackground() {
  const wrapper = document.getElementById("crop-canvas-wrapper");
  if (wrapper) {
    wrapper.classList.toggle("white-bg");
  }
}

function toggleDebugGridTheme() {
  const grid = document.getElementById("file-debug-grid");
  if (grid) {
    grid.classList.toggle("debug-grid-light");
  }
}

function toggleColorPickerBackground() {
  const wrapper = document.getElementById("color-picker-wrapper");
  if (wrapper) {
    wrapper.classList.toggle("color-picker-dark");
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

function addToMergeQueue() {
  if (mergeStack.length === 0) {
    alert("Vui lòng chọn ít nhất một ảnh để thêm vào hàng chờ!");
    return;
  }

  const currentFiles = mergeStack.map((f) =>
    typeof f === "string" ? f : f.filename,
  );

  // Check if any file is already in the queue
  for (const task of mergeQueue) {
    for (const file of currentFiles) {
      if (task.selected_files.includes(file)) {
        alert(
          `Cảnh báo: Ảnh "${file}" đã có trong hàng chờ (Task: ${task.destination_name}.png). \n\nVì ảnh gốc sẽ bị xóa sau khi ghép, bạn không được dùng một ảnh cho nhiều lệnh ghép khác nhau!`,
        );
        return;
      }
    }
  }

  const destName =
    document.getElementById("merge-dest-name").value.trim() ||
    (mergeQueue.length + 1).toString();

  const task = {
    destination_name: destName,
    selected_files: currentFiles,
    offsets: mergeStack.reduce((acc, f) => {
      if (typeof f !== "string" && f.x !== undefined) {
        acc[f.filename] = { x: f.x, y: f.y };
      }
      return acc;
    }, {}),
    layer_adjustments: JSON.parse(JSON.stringify(layerColorAdjustments)), // Deep copy
  };

  mergeQueue.push(task);

  // Clear current stack to prepare for next task
  mergeStack = [];
  // Increment destination name for convenience
  let nextId = parseInt(destName);
  if (!isNaN(nextId)) {
    document.getElementById("merge-dest-name").value = (nextId + 1).toString();
  }

  renderStack();
  redrawMergePreview();
  renderMergeQueue();
}

function renderMergeQueue() {
  const list = document.getElementById("merge-queue-list");
  if (!list) return;
  list.innerHTML = "";

  const btn = document.getElementById("process-queue-btn");
  if (btn) btn.disabled = mergeQueue.length === 0;

  mergeQueue.forEach((task, idx) => {
    const item = document.createElement("div");
    item.className = "stack-item mb-5";
    item.style.border = "1px dashed #ccc";
    item.style.padding = "5px";
    item.style.marginBottom = "5px";

    item.innerHTML = `
      <div class="flex-between" style="display:flex; justify-content:space-between; align-items:center;">
        <strong style="font-size: 12px;">#${idx + 1}: ${task.destination_name}.png</strong>
        <button class="btn btn-tiny btn-red" style="padding: 2px 5px; font-size: 10px;" onclick="removeFromMergeQueue(${idx})">✖</button>
      </div>
      <div style="font-size: 10px; color: #777; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
        ${task.selected_files.join(", ")}
      </div>
    `;
    list.appendChild(item);
  });
}

function removeFromMergeQueue(index) {
  mergeQueue.splice(index, 1);
  renderMergeQueue();
}

async function confirmBatchMerge() {
  if (mergeQueue.length === 0) return;

  if (
    !confirm(
      `Bạn có chắc chắn muốn thực hiện ${mergeQueue.length} lệnh ghép này không?`,
    )
  )
    return;

  const bulkApply = document.getElementById("bulk-apply-check").checked;
  const btn = document.getElementById("process-queue-btn");

  btn.disabled = true;
  btn.textContent = "⏳ Đang xử lý...";
  showLoading(`Đang xử lý ${mergeQueue.length} lệnh ghép...`);

  try {
    const response = await fetch("/api/batch_merge_layers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        folder: currentPart.part.folder,
        color: currentColor || "default",
        tasks: mergeQueue,
        bulk_apply: bulkApply,
      }),
    });

    const result = await response.json();
    if (result.success) {
      alert(result.message);
      mergeQueue = [];
      closeMergeModal();
      loadKitStructure(true);
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (error) {
    console.error(error);
    alert("Lỗi server khi ghép hàng loạt.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "🚀 Ghép tất cả";
    }
    hideLoading();
  }
}

function setFocusArea(area) {
  activeFocusArea = area;
  updateFocusUI();
}

function updateFocusUI() {
  document
    .getElementById("part-navigation-area")
    .classList.remove("active-focus");
  document
    .getElementById("item-selector-area")
    .classList.remove("active-focus");
  document
    .getElementById("color-selector-area")
    .classList.remove("active-focus");

  if (activeFocusArea === "parts") {
    document
      .getElementById("part-navigation-area")
      .classList.add("active-focus");
  } else if (activeFocusArea === "items") {
    document.getElementById("item-selector-area").classList.add("active-focus");
  } else if (activeFocusArea === "colors") {
    document
      .getElementById("color-selector-area")
      .classList.add("active-focus");
  }
}

// Keyboard navigation for colors
window.addEventListener("keydown", (e) => {
  // Only ignore if user is typing in a text input or textarea
  if (
    e.target.tagName === "TEXTAREA" ||
    (e.target.tagName === "INPUT" &&
      ["text", "number", "search"].includes(e.target.type))
  ) {
    return;
  }

  // Also check if any modal is open
  const modals = [
    "merge-modal-overlay",
    "layer-details-modal",
    "file-debug-modal",
  ];
  for (const id of modals) {
    const m = document.getElementById(id);
    if (m && m.style.display !== "none" && m.style.display !== "") return;
  }

  // 1, 2, 3 to switch focus regions
  if (e.key === "1") {
    setFocusArea("parts");
    return;
  }
  if (e.key === "2") {
    setFocusArea("items");
    return;
  }
  if (e.key === "3") {
    setFocusArea("colors");
    return;
  }

  if (!currentPart) return;

  // F2 Shortcut for Rename
  if (e.key === "F2") {
    e.preventDefault();
    // Default to part rename if in items or parts area, or if no area explicitly selected
    if (
      activeFocusArea === "colors" &&
      currentColor &&
      currentColor !== "default"
    ) {
      openRenameModal(currentColor, "color");
    } else if (currentPart) {
      openRenameModal(currentPart.part.folder, "part");
    }
    return;
  }

  // Logic based on focused area
  if (activeFocusArea === "parts") {
    let newIdx = currentPart.index;
    if (e.key === "ArrowUp" || e.key === "ArrowLeft") newIdx--;
    else if (e.key === "ArrowDown" || e.key === "ArrowRight") newIdx++;
    else return;

    if (newIdx >= 0 && newIdx < kitStructure.length) {
      e.preventDefault();
      selectPart(newIdx, kitStructure[newIdx]);
      document
        .querySelector(".nav-icon.active")
        ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    return;
  }

  if (activeFocusArea === "items") {
    const grid = document.getElementById("item-grid");
    const items = grid.querySelectorAll(".item-option");
    if (!items.length) return;

    const gridStyle = window.getComputedStyle(grid);
    const columns = gridStyle
      .getPropertyValue("grid-template-columns")
      .split(" ").length;

    // Find current active index
    let currentIndex = -1;
    items.forEach((item, idx) => {
      if (item.classList.contains("active")) currentIndex = idx;
    });

    let newIdx = currentIndex;
    switch (e.key) {
      case "ArrowLeft":
        newIdx--;
        break;
      case "ArrowRight":
        newIdx++;
        break;
      case "ArrowUp":
        newIdx -= columns;
        break;
      case "ArrowDown":
        newIdx += columns;
        break;
      default:
        return;
    }

    if (newIdx >= 0 && newIdx < items.length) {
      e.preventDefault();
      items[newIdx].click();
      items[newIdx].scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    return;
  }

  if (activeFocusArea === "colors") {
    const colors =
      currentPart.part.colors.length > 0
        ? currentPart.part.colors
        : ["default"];
    const grid = document.getElementById("color-grid");
    if (!grid || !grid.children.length) return;

    const gridStyle = window.getComputedStyle(grid);
    const columns = gridStyle
      .getPropertyValue("grid-template-columns")
      .split(" ").length;

    let newIndex = currentColorIndex;
    // phím tắt
    switch (e.key) {
      case "ArrowLeft":
        newIndex = currentColorIndex - 1;
        break;
      case "ArrowRight":
        newIndex = currentColorIndex + 1;
        break;
      case "ArrowUp":
        newIndex = currentColorIndex - columns;
        break;
      case "ArrowDown":
        newIndex = currentColorIndex + columns;
        break;
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
      case "z":
      case "Z":
        randomizeCharacter();
        e.preventDefault();
        return;
      case "x":
      case "X":
        resetAllLayers();
        e.preventDefault();
        c;
        return;
      case "c":
      case "C":
        autoCreateThumbs();
        e.preventDefault();
        return;
      case "v":
      case "V":
        deleteAllThumbs();
        e.preventDefault();
        return;
      case "q":
      case "Q":
        fixAllPartColorCodes();
        e.preventDefault();
        return;
      case "w":
      case "W":
        reorderPartImages();
        e.preventDefault();
        return;
      case "e":
      case "E":
        openColorPickerModal();
        e.preventDefault();
        return;
      case "r":
      case "R":
        confirmDeleteUnselectedColors();
        e.preventDefault();
        return;
      case "y":
      case "Y":
        deselectAllColors();
        e.preventDefault();
        return;
      case "t":
      case "T":
        createPartNav();
        e.preventDefault();
        return;
      case "a":
      case "A":
        promptDeletePart();
        e.preventDefault();
        return;
      default:
        return;
    }

    if (newIndex >= 0 && newIndex < colors.length) {
      e.preventDefault();
      selectColor(colors[newIndex], newIndex);
      const targetElement = grid.children[newIndex];
      if (targetElement)
        targetElement.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }
});

// --- Merged Script ---

function toggleMergeBackground() {
  const canvas = document.getElementById("merge-preview-canvas");
  if (canvas.dataset.bg === "dark") {
    canvas.style.background = "";
    canvas.dataset.bg = "light";
  } else {
    canvas.style.background = "#222";
    canvas.dataset.bg = "dark";
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

  if (
    !confirm(
      "Tạo thumbnail tự động cho tất cả folder X-Y trong data này?\n\nChỉ tạo thumb cho file chưa có.",
    )
  ) {
    return;
  }

  // Show loading
  showGlobalLoading("Đang quét và tạo thumbnail...");

  try {
    const response = await fetch("/api/auto_create_thumbs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kit: CURRENT_KIT_FOLDER }),
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
        stats.details.forEach((d) => {
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

  if (
    !confirm(
      "⚠️ CẢNH BÁO: Bạn có chắc chắn muốn xóa TẤT CẢ thumbnail (thumb_*.png) trong data này không?",
    )
  ) {
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
      body: JSON.stringify({ kit: CURRENT_KIT_FOLDER }),
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
  let overlay = document.getElementById("global-loading-overlay");
  if (!overlay) {
    // Create if not exists
    overlay = document.createElement("div");
    overlay.id = "global-loading-overlay";
    overlay.innerHTML = `<div class="spinner"></div><p id="global-loading-message"></p>`;
    document.body.appendChild(overlay);
  }
  const msgEl = document.getElementById("global-loading-message");
  if (msgEl) msgEl.textContent = msg || "Đang xử lý...";
  overlay.style.display = "flex";
}

function hideGlobalLoading() {
  const overlay = document.getElementById("global-loading-overlay");
  if (overlay) overlay.style.display = "none";
}

// Create thumbs for current part
async function createPartThumbs() {
  if (!CURRENT_KIT_FOLDER || !currentPart) {
    alert("Vui lòng chọn bộ phận trước!");
    return;
  }

  const folderName = currentPart.part.folder;

  // Allow cropping even for default color (single color parts)
  if (currentColor) {
    openCropThumbnailModal();
    return;
  }

  if (
    !confirm(
      `Tạo thumbnail tự động cho bộ phận "${folderName}"?\n\nChỉ tạo thumb cho file chưa có.`,
    )
  ) {
    return;
  }

  showGlobalLoading(`Đang tạo thumbnail cho ${folderName}...`);

  try {
    const response = await fetch("/api/auto_create_thumbs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        folder: folderName,
      }),
    });

    const result = await response.json();
    hideGlobalLoading();

    if (result.success) {
      alert(
        `✅ Hoàn tất!\n\n✨ Đã tạo thêm: ${result.stats.created_thumbs} thumb.`,
      );
      imgVers = Date.now(); // Cập nhật version để xóa cache ảnh
      loadItems(currentPart.part); // Refresh item grid
    } else {
      alert("❌ Lỗi: " + result.message);
    }
  } catch (error) {
    hideGlobalLoading();
    alert("❌ Lỗi kết nối: " + error.message);
  }
}

// Delete thumbs for current part
async function deletePartThumbs() {
  if (!CURRENT_KIT_FOLDER || !currentPart) {
    alert("Vui lòng chọn bộ phận trước!");
    return;
  }

  const folderName = currentPart.part.folder;

  if (
    !confirm(`⚠️ CẢNH BÁO: Xóa TẤT CẢ thumbnail trong bộ phận "${folderName}"?`)
  ) {
    return;
  }

  showGlobalLoading(`Đang xóa thumbnail của ${folderName}...`);

  try {
    const response = await fetch("/api/delete_all_thumbs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        folder: folderName,
      }),
    });

    const result = await response.json();
    hideGlobalLoading();

    if (result.success) {
      alert(`✅ Đã xóa xong thumbnail của "${folderName}".`);
      imgVers = Date.now(); // Cập nhật version để xóa cache ảnh
      loadItems(currentPart.part); // Refresh item grid
    } else {
      alert("❌ Lỗi: " + result.message);
    }
  } catch (error) {
    hideGlobalLoading();
    alert("❌ Lỗi kết nối: " + error.message);
  }
}

// Create nav.png for current part from 1.png
async function createPartNav() {
  if (!CURRENT_KIT_FOLDER || !currentPart) {
    alert("Vui lòng chọn bộ phận trước!");
    return;
  }

  const folderName = currentPart.part.folder;
  const itemNo = currentItem;
  const colorFolder = currentColor || "default";

  if (itemNo === null || itemNo === -1) {
    alert("Vui lòng chọn một Item (ảnh) để làm Nav!");
    return;
  }

  if (
    !confirm(
      `Tạo Nav cho bộ phận "${folderName}" từ Item #${itemNo} (Màu: ${colorFolder})?`,
    )
  ) {
    return;
  }

  showGlobalLoading(`Đang tạo Nav cho ${folderName}...`);

  try {
    const response = await fetch("/api/create_nav", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        folder: folderName,
        item_number: itemNo,
        color: colorFolder,
      }),
    });

    const result = await response.json();
    hideGlobalLoading();

    if (result.success) {
      alert(`✅ Hoàn tất: ${result.message}`);

      // Update the nav icon image in the UI
      imgVers = Date.now();
      const navIconImg = document.querySelector(
        `[data-part-index="${currentPart.index}"] img`,
      );
      if (navIconImg) {
        // Sử dụng tên file thực tế từ server trả về (nav.png hoặc nav.webp)
        const filename = result.filename || "nav.png";
        navIconImg.src = `${KIT_PATH}${folderName}/${filename}?v=${imgVers}`;
        navIconImg.style.display = "block";
      }
    } else {
      alert("❌ Lỗi: " + result.message);
    }
  } catch (error) {
    hideGlobalLoading();
    alert("❌ Lỗi kết nối: " + error.message);
  }
}

// --- Cropping Modal Logic ---
let cropCanvas, cropCtx, cropImg;
let isDraggingCrop = false;
let isResizingCrop = false;
let startX, startY, startW, startH;
let currentCropItemNo = null; // New: track single item crop
let cropX = 100,
  cropY = 100;
let cropScale = 1;

function openCropThumbnailModal(itemNo = null) {
  if (!currentPart || !currentColor) return;

  const folder = currentPart.part.folder;
  const color = currentColor;
  currentCropItemNo = itemNo;

  const titleSuffix = itemNo ? ` cho ảnh #${itemNo}` : "";
  document.getElementById("crop-part-name").textContent =
    folder + (itemNo ? ` [Ảnh #${itemNo}]` : "");
  document.getElementById("crop-color-name").textContent = color;
  document.getElementById("crop-modal-overlay").style.display = "flex";

  cropCanvas = document.getElementById("crop-canvas");
  cropCtx = cropCanvas.getContext("2d");

  // Load sample image. If itemNo is set, use it.
  const displayNum = itemNo || 1;
  cropImg = new Image();
  cropImg.crossOrigin = "anonymous";
  const imagePath =
    color === "default"
      ? `${KIT_PATH}${folder}/${displayNum}.png`
      : `${KIT_PATH}${folder}/${color}/${displayNum}.png`;
  cropImg.src = `${imagePath}?v=${Date.now()}`;

  cropImg.onload = () => {
    // Limit display size but keep aspect ratio
    const maxDisplayW = 600;
    const maxDisplayH = 600;

    cropScale = Math.min(
      maxDisplayW / cropImg.naturalWidth,
      maxDisplayH / cropImg.naturalHeight,
      1,
    );

    cropCanvas.width = cropImg.naturalWidth * cropScale;
    cropCanvas.height = cropImg.naturalHeight * cropScale;

    cropCtx.drawImage(cropImg, 0, 0, cropCanvas.width, cropCanvas.height);

    // Initial frame setup
    updateCropFrameSize();
    updateCropFramePosition();

    // Setup mouse listeners on the canvas container
    const container = cropCanvas.parentElement;
    container.onmousedown = (e) => {
      const isResizer = e.target.id === "crop-resizer";
      if (isResizer) {
        isResizingCrop = true;
        startX = e.clientX;
        startY = e.clientY;
        startW = parseInt(document.getElementById("crop-w").value) || 44;
        startH = parseInt(document.getElementById("crop-h").value) || 44;
        e.stopPropagation();
      } else {
        isDraggingCrop = true;
        handleCropMove(e);
      }
    };
    window.onmousemove = (e) => {
      if (isResizingCrop) {
        const dx = (e.clientX - startX) / cropScale;
        const dy = (e.clientY - startY) / cropScale;

        let newW = Math.round(startW + dx);
        let newH = Math.round(startH + dy);

        // Respect min size and bounds
        newW = Math.max(10, Math.min(newW, cropImg.naturalWidth - cropX));
        newH = Math.max(10, Math.min(newH, cropImg.naturalHeight - cropY));

        const lock = document.getElementById("crop-lock-ratio").checked;
        if (lock) {
          // In 1:1 lock, use the larger of the two deltas to feel natural
          const side = Math.max(newW, newH);
          // Re-clamp for square
          const maxSide = Math.min(
            cropImg.naturalWidth - cropX,
            cropImg.naturalHeight - cropY,
          );
          newW = Math.min(side, maxSide);
          newH = newW;
        }

        document.getElementById("crop-w").value = newW;
        document.getElementById("crop-h").value = newH;
        updateCropFrameSize();
      } else if (isDraggingCrop) {
        handleCropMove(e);
      }
    };
    window.onmouseup = () => {
      isDraggingCrop = false;
      isResizingCrop = false;
    };
  };
}

function handleCropMove(e) {
  if (!isDraggingCrop) return;
  const rect = cropCanvas.getBoundingClientRect();
  const w = parseInt(document.getElementById("crop-w").value);
  const h = parseInt(document.getElementById("crop-h").value);

  // Calculate center position
  let x = (e.clientX - rect.left) / cropScale - w / 2;
  let y = (e.clientY - rect.top) / cropScale - h / 2;

  // Clamp values
  cropX = Math.max(0, Math.min(x, cropImg.naturalWidth - w));
  cropY = Math.max(0, Math.min(y, cropImg.naturalHeight - h));

  updateCropFramePosition();
}

function updateCropFrameSize() {
  const frame = document.getElementById("crop-frame");
  const wInput = document.getElementById("crop-w");
  const hInput = document.getElementById("crop-h");
  const lockCheck = document.getElementById("crop-lock-ratio");

  let w = parseInt(wInput.value) || 44;
  let h = parseInt(hInput.value) || 44;

  if (lockCheck && lockCheck.checked) {
    // If called from a manual input change, we might need to sync
    // This part handles the "height follows width" requirement
    if (document.activeElement === wInput || isResizingCrop) {
      h = w;
      hInput.value = h;
    } else if (document.activeElement === hInput) {
      w = h;
      wInput.value = w;
    } else {
      // Fallback for programmatic calls
      h = w;
      hInput.value = h;
    }
  }

  frame.style.width = w * cropScale + "px";
  frame.style.height = h * cropScale + "px";

  // Sync size preview display
  const wDisp = document.getElementById("crop-w-disp");
  const hDisp = document.getElementById("crop-h-disp");
  if (wDisp) wDisp.textContent = w;
  if (hDisp) hDisp.textContent = h;

  // Re-clamp position if size changed
  cropX = Math.max(0, Math.min(cropX, cropImg.naturalWidth - w));
  cropY = Math.max(0, Math.min(cropY, cropImg.naturalHeight - h));
  updateCropFramePosition();
}

function updateCropFramePosition() {
  const frame = document.getElementById("crop-frame");
  frame.style.left = cropX * cropScale + "px";
  frame.style.top = cropY * cropScale + "px";

  document.getElementById("crop-x-val").textContent = Math.round(cropX);
  document.getElementById("crop-y-val").textContent = Math.round(cropY);
}

function closeCropModal() {
  document.getElementById("crop-modal-overlay").style.display = "none";
  window.onmousemove = null;
  window.onmouseup = null;
}

async function confirmBatchCrop() {
  const w = parseInt(document.getElementById("crop-w").value);
  const h = parseInt(document.getElementById("crop-h").value);

  const scopeMsg = currentCropItemNo
    ? `cho duy nhất ảnh #${currentCropItemNo}`
    : `hàng loạt cho tất cả ảnh trong folder màu "${currentColor}"`;

  if (
    !confirm(
      `Bắt đầu tạo thumbnail ${scopeMsg} với kích thước ${w}x${h} tại tọa độ (${Math.round(
        cropX,
      )}, ${Math.round(cropY)})?\n\nẢnh gốc sẽ KHÔNG bị thay đổi.`,
    )
  ) {
    return;
  }

  const btn = document.getElementById("start-crop-btn");
  btn.disabled = true;
  btn.textContent = "⌛ Đang xử lý...";

  try {
    const response = await fetch("/api/crop_batch_thumbs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        folder: currentPart.part.folder,
        color: currentColor,
        x: Math.round(cropX),
        y: Math.round(cropY),
        width: w,
        height: h,
        item_no: currentCropItemNo,
      }),
    });

    const result = await response.json();
    if (result.success) {
      alert(`✅ Hoàn tất: ${result.message}`);
      closeCropModal();
      imgVers = Date.now(); // Cập nhật version để xóa cache ảnh
      loadItems(currentPart.part); // Refresh UI
    } else {
      alert("❌ Lỗi: " + result.message);
    }
  } catch (error) {
    console.error(error);
    alert("❌ Lỗi kết nối server");
  } finally {
    btn.disabled = false;
    btn.textContent = "🚀 Bắt đầu tạo Thumbnail";
  }
}

// ================= DRAG & DROP REORDERING =================
let draggedNavIcon = null;

function handleNavDragStart(e) {
  draggedNavIcon = this;
  this.classList.add("dragging");
  e.dataTransfer.effectAllowed = "move";
  // Firefox needs some data to be set
  e.dataTransfer.setData("text/plain", this.dataset.folderName);
}

function handleNavDragOver(e) {
  if (e.preventDefault) {
    e.preventDefault();
  }
  if (draggedNavIcon !== this) {
    this.classList.add("drag-over");
  }
  e.dataTransfer.dropEffect = "move";
  return false;
}

function handleNavDragLeave(e) {
  this.classList.remove("drag-over");
}

function handleNavDragEnd(e) {
  document.querySelectorAll(".nav-icon").forEach((icon) => {
    icon.classList.remove("dragging", "drag-over");
  });
  draggedNavIcon = null;
}

async function handleNavDrop(e) {
  if (e.stopPropagation) {
    e.stopPropagation();
  }

  if (draggedNavIcon && draggedNavIcon !== this) {
    // Determine move direction
    const container = document.getElementById("nav-icons");
    const icons = Array.from(container.querySelectorAll(".nav-icon"));
    const draggedIdx = icons.indexOf(draggedNavIcon);
    const dropIdx = icons.indexOf(this);

    if (draggedIdx < dropIdx) {
      this.after(draggedNavIcon);
    } else {
      this.before(draggedNavIcon);
    }

    // Trigger physical reordering on server
    await commitPartReorder();
  }

  return false;
}

async function commitPartReorder() {
  const container = document.getElementById("nav-icons");
  const icons = Array.from(container.querySelectorAll(".nav-icon"));
  const renames = [];

  // Important: we need to use the current kitStructure to get original X/Y values
  // but update either X or Y based on the NEW sequence index.
  icons.forEach((icon, newIndex) => {
    const partIdx = parseInt(icon.dataset.partIndex);
    const part = kitStructure[partIdx];
    const oldName = icon.dataset.folderName;

    let newX = part.x;
    let newY = part.y;

    const sequenceOrder = newIndex + 1; // 1-based index for naming

    if (partSortType === "x") {
      newX = sequenceOrder;
    } else {
      newY = sequenceOrder;
    }

    // Capture existing suffix from old name
    const match = oldName.match(/^(\d+)-(\d+)(?:-(.*))?$/);
    const suffix = match && match[3] ? `-${match[3]}` : "";

    const newName = `${newX}-${newY}${suffix}`;

    // We only send renames if the name actually changes
    if (oldName !== newName) {
      renames.push({ old: oldName, new: newName });
    }
  });

  if (renames.length === 0) return;

  try {
    showGlobalLoading("Đang lưu thứ tự mới...");

    // We also need to update characterLayers locally if any currently selected parts are being renamed
    // so that preservation logic in loadKitStructure works.
    Object.keys(characterLayers).forEach((idx) => {
      const layer = characterLayers[idx];
      const r = renames.find((ren) => ren.old === layer.folderName);
      if (r) {
        layer.folderName = r.new;
      }
    });

    const response = await fetch("/api/reorder_parts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        renames: renames,
      }),
    });

    const result = await response.json();
    if (result.success) {
      // Reload kit structure with preservation
      // This will rebuild kitStructure and update characterLayers mapping
      await loadKitStructure(true);
    } else {
      alert("Lỗi khi sắp xếp: " + result.message);
      await loadKitStructure(true); // Revert UI
    }
  } catch (error) {
    console.error("Reorder error:", error);
    alert("Lỗi kết nối khi sắp xếp bộ phận.");
    await loadKitStructure(true); // Revert UI
  } finally {
    hideGlobalLoading();
  }
}

// --- Instruction Modal ---
function showInstructions() {
  const modal = document.getElementById("instruction-modal-overlay");
  if (modal) modal.style.display = "flex";
}

function closeInstructionModal() {
  const modal = document.getElementById("instruction-modal-overlay");
  if (modal) modal.style.display = "none";
}

// Close modal when clicking outside
window.addEventListener("click", (event) => {
  const instructionModal = document.getElementById("instruction-modal-overlay");
  if (event.target === instructionModal) {
    closeInstructionModal();
  }
  const mergeFoldersModal = document.getElementById("merge-folders-modal-overlay");
  if (event.target === mergeFoldersModal) {
    closeMergeFoldersModal();
  }
  const multiMergeModal = document.getElementById("multi-merge-modal-overlay");
  if (event.target === multiMergeModal) {
    closeMultiMergeModal();
  }
});

// --- Merge Folders Modal Logic ---
function openMergeFoldersModal() {
  if (!CURRENT_KIT_FOLDER) {
    alert("Vui lòng chọn một bộ sưu tập trước.");
    return;
  }

  // Populate datalists
  const list1 = document.getElementById("merge-folders-list1");
  const list2 = document.getElementById("merge-folders-list2");
  list1.innerHTML = "";
  list2.innerHTML = "";

  if (kitStructure) {
    kitStructure.forEach(part => {
      const opt1 = document.createElement("option");
      opt1.value = part.folder;
      list1.appendChild(opt1);

      const opt2 = document.createElement("option");
      opt2.value = part.folder;
      list2.appendChild(opt2);
    });
  }

  document.getElementById("merge-folders-input1").value = "";
  document.getElementById("merge-folders-input2").value = "";
  document.getElementById("merge-folders-new-name").value = "";
  document.getElementById("merge-folders-modal-overlay").style.display = "flex";
}

function closeMergeFoldersModal() {
  document.getElementById("merge-folders-modal-overlay").style.display = "none";
}

async function confirmMergeFolders() {
  const folder1 = document.getElementById("merge-folders-input1").value.trim();
  const folder2 = document.getElementById("merge-folders-input2").value.trim();
  const newFolder = document.getElementById("merge-folders-new-name").value.trim();

  if (!folder1 || !folder2 || !newFolder) {
    alert("Vui lòng nhập đầy đủ thông tin.");
    return;
  }

  if (folder1 === folder2) {
    alert("Hai thư mục cần gộp phải khác nhau.");
    return;
  }

  if (!/^\d+-\d+(?:-.*)?$/.test(newFolder)) {
    alert("Tên thư mục mới phải đúng định dạng số X-Y (hoặc X-Y-Z) (VD: 100-3-toc-gop) để sắp xếp layer.");
    return;
  }

  if (!confirm(`Bạn chắc chắn muốn gộp thư mục "${folder1}" và "${folder2}" thành "${newFolder}"?\n\nChú ý: Hai thư mục cũ sẽ bị xóa (được đưa vào Thùng rác).`)) {
    return;
  }

  showGlobalLoading("Đang gộp 2 thư mục bộ phận...");
  try {
    const response = await fetch("/api/merge_folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        folder1: folder1,
        folder2: folder2,
        new_folder: newFolder
      })
    });

    const result = await response.json();
    if (result.success) {
      alert(result.message);
      closeMergeFoldersModal();
      location.reload();
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (error) {
    console.error(error);
    alert("Lỗi server hoặc lỗi kết nối khi gộp thư mục.");
  } finally {
    hideGlobalLoading();
  }
}

function toggleSelectMergeMode() {
  selectMergeMode = !selectMergeMode;
  selectedMergeFolders = [];
  lastCheckedIndex = null;

  const btn = document.getElementById("toggle-select-merge-btn");
  const confirmBtn = document.getElementById("confirm-select-merge-btn");

  if (selectMergeMode) {
    btn.textContent = "Hủy chọn gộp";
    btn.className = "btn btn-red btn-small m-l-5";
    confirmBtn.style.display = "inline-block";
    confirmBtn.disabled = true;
    document.getElementById("select-merge-count").textContent = "0";
  } else {
    btn.textContent = "Chọn gộp nhiều";
    btn.className = "btn btn-orange btn-small m-l-5";
    confirmBtn.style.display = "none";
  }

  // Toggle checkboxes and style display in UI
  document.querySelectorAll(".nav-icon").forEach(navEl => {
    const cb = navEl.querySelector(".merge-checkbox");
    if (cb) {
      cb.style.display = selectMergeMode ? "block" : "none";
      cb.checked = false;
      cb.disabled = false;
    }
    navEl.style.opacity = "";
  });
}

function handleCheckboxClick(index, isChecked) {
  const part = kitStructure[index];
  if (isChecked) {
    if (!selectedMergeFolders.includes(part.folder)) {
      selectedMergeFolders.push(part.folder);
    }
    lastCheckedIndex = index;
  } else {
    selectedMergeFolders = selectedMergeFolders.filter(f => f !== part.folder);
    if (lastCheckedIndex === index) {
      lastCheckedIndex = null;
    }
  }
  updateMergeButtonState();
}

function handleRangeSelect(index) {
  if (lastCheckedIndex === null) {
    // Treat as first selection
    const part = kitStructure[index];
    const navEl = document.querySelector(`.nav-icon[data-part-index="${index}"]`);
    if (navEl) {
      const cb = navEl.querySelector(".merge-checkbox");
      if (cb) {
        cb.checked = true;
        handleCheckboxClick(index, true);
      }
    }
    return;
  }

  // Find position in current sorted view
  const idx1 = currentSortedIndices.indexOf(lastCheckedIndex);
  const idx2 = currentSortedIndices.indexOf(index);
  if (idx1 === -1 || idx2 === -1) return;

  const start = Math.min(idx1, idx2);
  const end = Math.max(idx1, idx2);

  for (let i = start; i <= end; i++) {
    const partIdx = currentSortedIndices[i];
    const part = kitStructure[partIdx];

    const navEl = document.querySelector(`.nav-icon[data-part-index="${partIdx}"]`);
    if (navEl) {
      const cb = navEl.querySelector(".merge-checkbox");
      if (cb) {
        cb.checked = true;
        if (!selectedMergeFolders.includes(part.folder)) {
          selectedMergeFolders.push(part.folder);
        }
      }
    }
  }

  lastCheckedIndex = index;
  updateMergeButtonState();
}

function updateMergeButtonState() {
  const confirmBtn = document.getElementById("confirm-select-merge-btn");
  const countSpan = document.getElementById("select-merge-count");
  const count = selectedMergeFolders.length;

  countSpan.textContent = count;
  if (count >= 2) {
    confirmBtn.disabled = false;
  } else {
    confirmBtn.disabled = true;
  }
}

function openMultiMergeDialog() {
  if (selectedMergeFolders.length < 2) {
    alert("Vui lòng chọn ít nhất 2 thư mục để gộp.");
    return;
  }

  const listDiv = document.getElementById("multi-merge-selected-list");
  listDiv.innerHTML = selectedMergeFolders.map(f => `<div>📁 ${f}</div>`).join("");

  document.getElementById("multi-merge-new-suffix").value = "";
  document.getElementById("multi-merge-modal-overlay").style.display = "flex";
}

function closeMultiMergeModal() {
  document.getElementById("multi-merge-modal-overlay").style.display = "none";
}

async function confirmMultiMergeFolders() {
  const newFolderName = document.getElementById("multi-merge-new-suffix").value.trim();
  if (!newFolderName) {
    alert("Vui lòng nhập tên cho thư mục gộp mới.");
    return;
  }

  if (!/^[a-zA-Z0-9_\-]+$/.test(newFolderName)) {
    alert("Tên thư mục chỉ chấp nhận chữ cái không dấu, số, dấu gạch ngang và gạch dưới.");
    return;
  }

  if (!confirm(`Bạn chắc chắn muốn gộp ${selectedMergeFolders.length} thư mục đã chọn?\n\n* Sau khi gộp, hệ thống sẽ tự động đổi tên và đánh số lại tất cả thư mục còn lại.`)) {
    return;
  }

  showGlobalLoading("Đang thực hiện gộp nhiều thư mục bộ phận...");
  try {
    const response = await fetch("/api/merge_multiple_folders", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit: CURRENT_KIT_FOLDER,
        folders: selectedMergeFolders,
        new_folder_name: newFolderName
      })
    });

    const result = await response.json();
    if (result.success) {
      alert(result.message);
      closeMultiMergeModal();
      toggleSelectMergeMode(); // Turn off merge mode
      location.reload(); // Reload kit sequence
    } else {
      alert("Lỗi: " + result.message);
    }
  } catch (error) {
    console.error(error);
    alert("Lỗi kết nối hoặc lỗi máy chủ khi gộp thư mục.");
  } finally {
    hideGlobalLoading();
  }
}
