
    // State
    let rawFiles = [];
    let currentRawFile = null;
    let currentRawPage = 1;
    let currentRawPageSize = 25;
    let currentRawSearch = "";
    let currentRawData = null;

    let lakehousePage = 1;
    let lakehousePageSize = 25;
    let lakehouseSearch = "";

    let auditPage = 1;
    let auditPageSize = 50;
    let auditSearch = "";
    let auditCategory = "";

    let lastValidationReport = null;
    let chatHistory = [];

    // INITIALIZATION
    document.addEventListener("DOMContentLoaded", () => {
      fetchDashboardStats();
      fetchRawFiles();
      loadSamplePayload(0);
      fetchLakehouseMaster();
      fetchAuditTrail();
    });

    // TOAST NOTIFIER
    function showToast(message, type = "info") {
      const container = document.getElementById("toastContainer");
      const toast = document.createElement("div");
      toast.className = `toast ${type}`;
      const icon = type === "success" ? "fa-circle-check" : type === "error" ? "fa-circle-exclamation" : "fa-circle-info";
      toast.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
      container.appendChild(toast);
      setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
      }, 3500);
    }

    // HORIZONTAL SCROLL HELPER
    function scrollTableHorizontally(wrapperId, delta) {
      const el = document.getElementById(wrapperId);
      if (el) {
        el.scrollBy({ left: delta, behavior: 'smooth' });
      }
    }

    // MAIN TAB NAVIGATION
    function switchMainTab(tabId) {
      document.querySelectorAll(".nav-tab-btn").forEach(btn => btn.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(panel => panel.classList.remove("active"));

      if (tabId === "explorer") {
        document.getElementById("tabBtnExplorer").classList.add("active");
        document.getElementById("tabPanelExplorer").classList.add("active");
      } else if (tabId === "validator") {
        document.getElementById("tabBtnValidator").classList.add("active");
        document.getElementById("tabPanelValidator").classList.add("active");
      } else if (tabId === "lakehouse") {
        document.getElementById("tabBtnLakehouse").classList.add("active");
        document.getElementById("tabPanelLakehouse").classList.add("active");
        fetchLakehouseMaster();
      } else if (tabId === "audit") {
        document.getElementById("tabBtnAudit").classList.add("active");
        document.getElementById("tabPanelAudit").classList.add("active");
        fetchAuditTrail();
      }
    }

    // DASHBOARD STATS
    async function fetchDashboardStats() {
      try {
        const res = await fetch("/api/ingestion/stats");
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById("kpiRawRows").innerText = Number(data.raw_total_rows).toLocaleString();
        document.getElementById("kpiRawFiles").innerText = data.raw_files_count;
        document.getElementById("kpiLakehouseRows").innerText = Number(data.lakehouse_records).toLocaleString();
        document.getElementById("kpiAuditFixes").innerText = Number(data.audit_fixes_count).toLocaleString();
        document.getElementById("kpiMasters").innerText = `${data.supported_code_masters} States`;
      } catch (err) {
        console.error("Error fetching stats:", err);
      }
    }

    // ========================================================
    // TAB 1: RAW DATA LAKE EXPLORER
    // ========================================================
    async function fetchRawFiles() {
      try {
        const res = await fetch("/api/ingestion/raw-files");
        const files = await res.json();
        rawFiles = files;
        document.getElementById("rawFilesCount").innerText = `${files.length} Files`;

        const container = document.getElementById("rawFilesContainer");
        container.innerHTML = "";

        files.forEach((file, index) => {
          const item = document.createElement("div");
          item.className = `raw-file-item ${index === 0 ? "active" : ""}`;
          item.onclick = () => selectRawFile(file.filename);

          item.innerHTML = `
            <div class="file-item-top">
              <span class="file-item-name"><i class="fa-solid fa-${file.icon || 'file'}"></i> ${file.filename}</span>
              <span class="pill pill-purple">${file.format}</span>
            </div>
            <div class="file-item-desc">${file.description}</div>
            <div class="file-item-meta">
              <span><i class="fa-solid fa-list-ol"></i> ${Number(file.rows).toLocaleString()} rows</span>
              <span><i class="fa-solid fa-table-columns"></i> ${file.columns_count} cols</span>
              <span><i class="fa-solid fa-hard-drive"></i> ${file.size_mb} MB</span>
            </div>
          `;
          container.appendChild(item);
        });

        if (files.length > 0) {
          selectRawFile(files[0].filename);
        }
      } catch (err) {
        console.error("Error loading raw files:", err);
      }
    }

    async function selectRawFile(filename) {
      currentRawFile = filename;
      currentRawPage = 1;
      currentRawSearch = "";
      document.getElementById("rawSearchInput").value = "";

      document.querySelectorAll(".raw-file-item").forEach(item => {
        item.classList.toggle("active", item.innerText.includes(filename));
      });

      const meta = rawFiles.find(f => f.filename === filename);
      if (meta) {
        document.getElementById("currentDatasetName").innerText = meta.filename;
        document.getElementById("currentDatasetFormat").innerText = meta.format;
        document.getElementById("currentDatasetDesc").innerText = meta.description;
      }

      await fetchRawData();
    }

    async function fetchRawData() {
      if (!currentRawFile) return;

      const tbody = document.getElementById("rawTableBody");
      tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:3rem; color:var(--text-dim);"><div class="spinner"></div> Reading ${currentRawFile}...</td></tr>`;

      try {
        const url = `/api/ingestion/raw-data?filename=${encodeURIComponent(currentRawFile)}&page=${currentRawPage}&page_size=${currentRawPageSize}&search=${encodeURIComponent(currentRawSearch)}`;
        const res = await fetch(url);
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Failed to load data");
        }
        const data = await res.json();
        currentRawData = data;

        renderRawTable(data);
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:2rem; color:var(--accent-red);">${err.message}</td></tr>`;
      }
    }

    function renderRawTable(data) {
      const thead = document.getElementById("rawTableHeaders");
      const tbody = document.getElementById("rawTableBody");

      thead.innerHTML = `<th>#</th><th>Action</th>`;
      const visibleCols = data.column_names.slice(0, 15);
      visibleCols.forEach(col => {
        const th = document.createElement("th");
        th.innerText = col;
        thead.appendChild(th);
      });
      if (data.column_names.length > 15) {
        const thMore = document.createElement("th");
        thMore.innerText = `+${data.column_names.length - 15} more cols`;
        thead.appendChild(thMore);
      }

      tbody.innerHTML = "";
      if (data.records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${visibleCols.length + 3}" style="text-align:center; padding:2.5rem; color:var(--text-dim);">No records match your search filter.</td></tr>`;
        updateRawPagination(0, 0, 0);
        return;
      }

      data.records.forEach((row, idx) => {
        const tr = document.createElement("tr");
        const rowNum = (data.page - 1) * data.page_size + idx + 1;

        let cellsHtml = `
          <td style="font-family:var(--font-mono); color:var(--text-dim);">${rowNum}</td>
          <td>
            <button class="btn" style="padding:4px 8px; font-size:0.72rem;" onclick="viewRecordInspector(${idx})">
              <i class="fa-solid fa-eye" style="color:var(--accent-cyan)"></i> View
            </button>
          </td>
        `;

        visibleCols.forEach(col => {
          let val = row[col];
          if (Array.isArray(val)) {
            val = `[${val.length} items]`;
          } else if (val === null || val === undefined) {
            val = "";
          }
          cellsHtml += `<td title="${String(val)}">${String(val)}</td>`;
        });

        if (data.column_names.length > 15) {
          cellsHtml += `<td style="color:var(--text-dim); font-size:0.75rem;">...</td>`;
        }

        tr.innerHTML = cellsHtml;
        tbody.appendChild(tr);
      });

      updateRawPagination(data.total_filtered, data.page, data.total_pages);
    }

    function updateRawPagination(total, page, totalPages) {
      const start = total === 0 ? 0 : (page - 1) * currentRawPageSize + 1;
      const end = Math.min(page * currentRawPageSize, total);
      document.getElementById("rawPageInfo").innerText = `Showing ${start.toLocaleString()} to ${end.toLocaleString()} of ${total.toLocaleString()} records`;
      document.getElementById("rawCurrentPageBadge").innerText = `${page} / ${totalPages}`;
      document.getElementById("rawPrevBtn").disabled = (page <= 1);
      document.getElementById("rawNextBtn").disabled = (page >= totalPages);
    }

    function navigateRawPage(delta) {
      currentRawPage += delta;
      fetchRawData();
    }

    function changeRawPageSize() {
      currentRawPageSize = parseInt(document.getElementById("rawPageSizeSelect").value);
      currentRawPage = 1;
      fetchRawData();
    }

    let searchDebounceTimer = null;
    function handleRawSearch(event) {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => {
        currentRawSearch = event.target.value;
        currentRawPage = 1;
        fetchRawData();
      }, 300);
    }

    function viewRecordInspector(recordIndex) {
      if (!currentRawData || !currentRawData.records[recordIndex]) return;
      const record = currentRawData.records[recordIndex];
      document.getElementById("modalRecordTitle").innerText = `Dataset: ${currentRawFile} | Row #${(currentRawPage - 1) * currentRawPageSize + recordIndex + 1}`;
      document.getElementById("modalJsonViewer").innerText = JSON.stringify(record, null, 2);
      document.getElementById("recordModal").classList.add("active");
    }

    function closeRecordModal() {
      document.getElementById("recordModal").classList.remove("active");
    }

    function openSchemaModal() {
      if (!currentRawData) return;
      const tbody = document.getElementById("schemaTableBody");
      tbody.innerHTML = "";
      currentRawData.columns.forEach((col, idx) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td style="font-family:var(--font-mono); color:var(--text-dim);">${idx + 1}</td>
          <td style="font-family:var(--font-mono); color:var(--text-main); font-weight:600;">${col.name}</td>
          <td><span class="pill pill-purple">${col.type}</span></td>
          <td><span class="pill ${col.nullable ? 'pill-amber' : 'pill-green'}">${col.nullable ? 'YES' : 'NO'}</span></td>
        `;
        tbody.appendChild(tr);
      });
      document.getElementById("schemaModal").classList.add("active");
    }

    function closeSchemaModal() {
      document.getElementById("schemaModal").classList.remove("active");
    }

    function closeModalOnBackdrop(e) {
      if (e.target.classList.contains("modal-overlay")) {
        e.target.classList.remove("active");
      }
    }

    function exportCurrentViewCSV() {
      if (!currentRawData || currentRawData.records.length === 0) {
        showToast("No records to export", "error");
        return;
      }
      const headers = currentRawData.column_names;
      const rows = currentRawData.records.map(row => 
        headers.map(h => {
          let val = row[h];
          if (val === null || val === undefined) val = "";
          val = String(val).replace(/"/g, '""');
          return `"${val}"`;
        }).join(",")
      );
      const csvContent = [headers.join(","), ...rows].join("\n");
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${currentRawFile.split('.')[0]}_export.csv`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("CSV file exported successfully", "success");
    }


    // ========================================================
    // TAB 2: INGESTION HUB MODES & VALIDATION
    // ========================================================
    function selectInputMode(mode) {
      document.getElementById("modeCardPreset").classList.toggle("active", mode === "preset");
      document.getElementById("modeCardGenerator").classList.toggle("active", mode === "generator");
      document.getElementById("modeCardUpload").classList.toggle("active", mode === "upload");

      document.getElementById("subcontrolPreset").classList.toggle("active", mode === "preset");
      document.getElementById("subcontrolGenerator").classList.toggle("active", mode === "generator");
      document.getElementById("subcontrolUpload").classList.toggle("active", mode === "upload");
    }

    async function loadSamplePayload(index) {
      try {
        const res = await fetch(`/api/ingestion/sample-payload?invoice_index=${index}`);
        const data = await res.json();
        document.getElementById("payloadEditor").value = JSON.stringify(data.payload, null, 2);
        document.getElementById("activeInvBadge").innerText = (data.payload.docdt1 && data.payload.docdt1.docno) || `INV-SAMPLE-${index+1}`;
        showToast(`Loaded customer invoice sample #${index + 1}`, "info");
      } catch (err) {
        console.error("Error loading sample payload:", err);
      }
    }

    async function generateDirtyBatch() {
      const count = parseInt(document.getElementById("genBatchCount").value) || 1;
      try {
        const res = await fetch("/api/ingestion/generate-dirty", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ count: count })
        });
        const data = await res.json();
        document.getElementById("payloadEditor").value = JSON.stringify(data.payload, null, 2);
        document.getElementById("activeInvBadge").innerText = `DIRTY-BATCH (${count})`;
        showToast(`Generated ${count} randomized dirty invoice(s)!`, "success");
      } catch (err) {
        showToast("Error generating dirty payload: " + err.message, "error");
      }
    }

    // Drag and drop / Manual upload handlers
    function handleDragOver(e) {
      e.preventDefault();
      document.getElementById("dropZone").classList.add("dragover");
    }

    function handleDragLeave(e) {
      e.preventDefault();
      document.getElementById("dropZone").classList.remove("dragover");
    }

    function handleFileDrop(e) {
      e.preventDefault();
      document.getElementById("dropZone").classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        processUploadedFile(e.dataTransfer.files[0]);
      }
    }

    function handleFileSelect(e) {
      if (e.target.files && e.target.files.length > 0) {
        processUploadedFile(e.target.files[0]);
      }
    }

    function processUploadedFile(file) {
      const reader = new FileReader();
      const ext = file.name.split('.').pop().toLowerCase();

      reader.onload = function(event) {
        const content = event.target.result;
        if (ext === 'json' || ext === 'txt') {
          try {
            const parsed = JSON.parse(content);
            document.getElementById("payloadEditor").value = JSON.stringify(parsed, null, 2);
            document.getElementById("activeInvBadge").innerText = file.name;
            showToast(`Loaded ${file.name} successfully`, "success");
          } catch (e) {
            document.getElementById("payloadEditor").value = content;
            document.getElementById("activeInvBadge").innerText = file.name;
            showToast(`Loaded raw text from ${file.name}`, "info");
          }
        } else {
          // For CSV or other files, place raw text into editor
          document.getElementById("payloadEditor").value = content;
          document.getElementById("activeInvBadge").innerText = file.name;
          showToast(`Uploaded ${file.name}`, "info");
        }
      };

      if (ext === 'xlsx' || ext === 'xls') {
        showToast(`Reading spreadsheet file ${file.name}...`, "info");
        reader.readAsBinaryString(file);
      } else {
        reader.readAsText(file);
      }
    }

    function formatEditorJson() {
      try {
        const val = JSON.parse(document.getElementById("payloadEditor").value);
        document.getElementById("payloadEditor").value = JSON.stringify(val, null, 2);
        showToast("JSON formatted cleanly", "success");
      } catch (e) {
        showToast("Invalid JSON syntax: " + e.message, "error");
      }
    }

    function clearEditor() {
      document.getElementById("payloadEditor").value = "{\n  \n}";
      document.getElementById("activeInvBadge").innerText = "EMPTY";
      showToast("Editor cleared", "info");
    }

    // Portal verifiers
    async function verifyGstinLive() {
      const gstin = document.getElementById("verifyGstinInput").value.trim();
      const box = document.getElementById("verifyResultBox");
      if (!gstin) return showToast("Enter a GSTIN to verify", "error");

      box.style.display = "block";
      box.innerHTML = `<div class="spinner"></div> Checking Modulo-36 & portal...`;

      try {
        const res = await fetch(`/api/ingestion/verify-gstin/${encodeURIComponent(gstin)}`);
        const data = await res.json();
        const valid = data.is_valid || data.status === "ACTIVE" || data.valid;
        box.innerHTML = `
          <div style="color:${valid ? 'var(--accent-green)' : 'var(--accent-red)'}">
            <i class="fa-solid fa-${valid ? 'circle-check' : 'circle-xmark'}"></i> <strong>GSTIN: ${gstin}</strong>
          </div>
          <div style="margin-top:2px;">State: ${data.state || data.state_code || '—'} | Status: ${data.status || 'Verified'}</div>
          <div>${data.legal_name || data.trade_name || data.message || ''}</div>
        `;
      } catch (err) {
        box.innerHTML = `<span style="color:var(--accent-red)">Error: ${err.message}</span>`;
      }
    }

    async function verifyVehicleLive() {
      const veh = document.getElementById("verifyVehInput").value.trim();
      const box = document.getElementById("verifyResultBox");
      if (!veh) return showToast("Enter a Vehicle Number to verify", "error");

      box.style.display = "block";
      box.innerHTML = `<div class="spinner"></div> Checking MoRTH Vahan 4.0...`;

      try {
        const res = await fetch(`/api/ingestion/verify-vehicle/${encodeURIComponent(veh)}`);
        const data = await res.json();
        const valid = data.is_valid || data.valid || data.status === "ACTIVE";
        box.innerHTML = `
          <div style="color:${valid ? 'var(--accent-green)' : 'var(--accent-red)'}">
            <i class="fa-solid fa-${valid ? 'truck' : 'triangle-exclamation'}"></i> <strong>Vehicle: ${veh}</strong>
          </div>
          <div>Format: ${data.format || 'Standard MoRTH'} | RC: ${data.status || 'Active'}</div>
        `;
      } catch (err) {
        box.innerHTML = `<span style="color:var(--accent-red)">Error: ${err.message}</span>`;
      }
    }

    // VALIDATE & PERSIST
    async function runLiveValidation() {
      const editor = document.getElementById("payloadEditor");
      const btn = document.getElementById("btnValidateLive");
      let rawJson;

      try {
        rawJson = JSON.parse(editor.value);
      } catch (e) {
        showToast("Invalid JSON syntax: " + e.message, "error");
        return;
      }

      btn.disabled = true;
      btn.innerHTML = `<div class="spinner"></div> Harmonizing...`;

      try {
        const res = await fetch("/api/ingestion/validate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(rawJson)
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Validation failed");
        }

        const data = await res.json();
        lastValidationReport = data;
        renderValidationResults(data);
        showToast(`Harmonized: ${data.corrections_count} customer errors auto-corrected!`, "success");
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-bolt"></i> Validate & Auto-Correct`;
      }
    }

    function renderValidationResults(data) {
      const badge = document.getElementById("validationStatusBadge");
      if (data.status === "VALID") {
        badge.className = "pill pill-green";
        badge.innerText = `STATUS: VALID (${data.invoice_number})`;
      } else {
        badge.className = "pill pill-amber";
        badge.innerText = `STATUS: NEEDS ATTENTION (${data.invoice_number})`;
      }

      document.getElementById("correctionsCountBadge").innerText = data.corrections_count;
      document.getElementById("statutoryErrorsCount").innerText = (data.statutory_errors || []).length;

      const tbody = document.getElementById("correctionsTableBody");
      tbody.innerHTML = "";
      if (data.corrections_applied.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:2rem; color:var(--text-muted);"><i class="fa-solid fa-circle-check" style="color:var(--accent-green)"></i> Payload is 100% clean. No corrections required.</td></tr>`;
      } else {
        data.corrections_applied.forEach(corr => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td><span class="pill pill-cyan">${corr.action || corr.category || 'FIX'}</span></td>
            <td style="font-family:var(--font-mono); color:#38bdf8;">${corr.field}</td>
            <td style="color:var(--accent-red); font-family:var(--font-mono);">${corr.original}</td>
            <td style="color:var(--accent-green); font-family:var(--font-mono); font-weight:600;">${corr.corrected}</td>
            <td style="color:var(--text-muted); font-size:0.75rem;">${corr.reason}</td>
          `;
          tbody.appendChild(tr);
        });
      }

      document.getElementById("cleanPayloadViewer").innerText = JSON.stringify(data.clean_payload, null, 2);
      document.getElementById("nicPayloadViewer").innerText = JSON.stringify(data.nic_irp_payload, null, 2);
      document.getElementById("ewbPayloadViewer").innerText = JSON.stringify(data.standalone_ewb_payload, null, 2);

      const errBox = document.getElementById("statutoryErrorsViewer");
      if (!data.statutory_errors || data.statutory_errors.length === 0) {
        errBox.innerHTML = `<div style="text-align:center; padding:2rem; color:var(--accent-green);"><i class="fa-solid fa-circle-check fa-2x"></i><br><br>All 28 NIC statutory validation rules passed with zero compliance violations!</div>`;
      } else {
        let errHtml = `<div style="display:flex; flex-direction:column; gap:0.75rem;">`;
        data.statutory_errors.forEach(err => {
          errHtml += `
            <div style="background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); border-radius:6px; padding:10px 14px;">
              <div style="display:flex; align-items:center; gap:0.5rem; margin-bottom:4px;">
                <span class="pill pill-red">RULE ${err.code}</span>
                <span style="font-weight:600; font-family:var(--font-mono);">${err.field}</span>
              </div>
              <div style="font-size:0.8rem; color:var(--text-muted);">${err.message}</div>
            </div>
          `;
        });
        errHtml += `</div>`;
        errBox.innerHTML = errHtml;
      }
    }

    async function persistLivePayload() {
      const editor = document.getElementById("payloadEditor");
      const btn = document.getElementById("btnPersistLive");
      let rawJson;

      try {
        rawJson = JSON.parse(editor.value);
      } catch (e) {
        showToast("Invalid JSON syntax: " + e.message, "error");
        return;
      }

      btn.disabled = true;
      btn.innerHTML = `<div class="spinner"></div> Persisting...`;

      try {
        const res = await fetch("/api/ingestion/persist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(rawJson)
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Persistence failed");
        }

        const data = await res.json();
        showToast(`Persisted invoice ${data.invoice_number} to Parquet lakehouse (+${data.parquet_row_count} rows)`, "success");
        fetchDashboardStats();
        fetchLakehouseMaster();
        fetchAuditTrail();
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<i class="fa-solid fa-cloud-arrow-up"></i> Persist to Lakehouse`;
      }
    }

    function switchResultSubTab(tab) {
      document.querySelectorAll(".sub-tab-btn").forEach(btn => btn.classList.remove("active"));
      document.querySelectorAll(".result-subpanel").forEach(panel => panel.classList.remove("active"));

      if (tab === "corrections") {
        document.getElementById("subTabCorrections").classList.add("active");
        document.getElementById("subPanelCorrections").classList.add("active");
      } else if (tab === "clean") {
        document.getElementById("subTabClean").classList.add("active");
        document.getElementById("subPanelClean").classList.add("active");
      } else if (tab === "nic") {
        document.getElementById("subTabNic").classList.add("active");
        document.getElementById("subPanelNic").classList.add("active");
      } else if (tab === "ewb") {
        document.getElementById("subTabEwb").classList.add("active");
        document.getElementById("subPanelEwb").classList.add("active");
      } else if (tab === "errors") {
        document.getElementById("subTabErrors").classList.add("active");
        document.getElementById("subPanelErrors").classList.add("active");
      }
    }

    function downloadArtifact(type) {
      const url = `/api/ingestion/download/${type}`;
      window.open(url, "_blank");
      showToast(`Downloading ${type} artifact...`, "info");
    }

    // ========================================================
    // AI COMPLIANCE COPILOT (CHATBOT)
    // ========================================================
    async function handleChatSubmit(e) {
      e.preventDefault();
      const input = document.getElementById("chatInputBox");
      const msg = input.value.trim();
      if (!msg) return;
      input.value = "";
      await sendChatMessage(msg);
    }

    function sendQuickChat(msg) {
      sendChatMessage(msg);
    }

    async function sendChatMessage(msg) {
      const feed = document.getElementById("copilotFeed");

      // Append user msg
      const userDiv = document.createElement("div");
      userDiv.className = "chat-msg user";
      userDiv.innerHTML = `<div class="chat-bubble">${msg}</div>`;
      feed.appendChild(userDiv);
      feed.scrollTop = feed.scrollHeight;

      // Thinking placeholder
      const thinkingDiv = document.createElement("div");
      thinkingDiv.className = "chat-msg bot";
      thinkingDiv.id = "chatThinking";
      thinkingDiv.innerHTML = `<div class="chat-bubble" style="color:var(--accent-cyan); display:flex; align-items:center; gap:8px;"><div class="spinner"></div> Analyzing statutory rules...</div>`;
      feed.appendChild(thinkingDiv);
      feed.scrollTop = feed.scrollHeight;

      let currentPayload = null;
      try {
        currentPayload = JSON.parse(document.getElementById("payloadEditor").value);
      } catch (err) {
        currentPayload = null;
      }

      try {
        const res = await fetch("/api/ingestion/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: msg,
            payload: currentPayload,
            validation_report: lastValidationReport,
            chat_history: chatHistory
          })
        });

        const thinking = document.getElementById("chatThinking");
        if (thinking) thinking.remove();

        const data = await res.json();
        chatHistory.push({ role: "user", content: msg });
        chatHistory.push({ role: "assistant", content: data.reply });

        // If copilot patched payload, update editor!
        if (data.patch_applied && data.updated_payload) {
          document.getElementById("payloadEditor").value = JSON.stringify(data.updated_payload, null, 2);
          showToast("Copilot applied correction patch to active payload!", "success");
        }

        const botDiv = document.createElement("div");
        botDiv.className = "chat-msg bot";

        let pillsHtml = "";
        const prompts = data.quick_prompts || data.interactive_actions || [];
        if (prompts.length > 0) {
          pillsHtml = `<div class="chat-quick-pills">` + prompts.map(p => 
            `<button class="chat-pill-btn" onclick="sendQuickChat('${p.replace(/'/g, "\\'")}')">${p}</button>`
          ).join(" ") + `</div>`;
        }

        botDiv.innerHTML = `<div class="chat-bubble">${data.reply.replace(/\n/g, '<br>')}</div>${pillsHtml}`;
        feed.appendChild(botDiv);
        feed.scrollTop = feed.scrollHeight;

      } catch (err) {
        const thinking = document.getElementById("chatThinking");
        if (thinking) thinking.remove();

        const errDiv = document.createElement("div");
        errDiv.className = "chat-msg bot";
        errDiv.innerHTML = `<div class="chat-bubble" style="color:var(--accent-red)">⚠️ Error connecting to Copilot: ${err.message}</div>`;
        feed.appendChild(errDiv);
        feed.scrollTop = feed.scrollHeight;
      }
    }


    // ========================================================
    // TAB 3: PROCESSED LAKEHOUSE MASTER
    // ========================================================
    async function fetchLakehouseMaster() {
      const tbody = document.getElementById("lakehouseTableBody");
      try {
        const url = `/api/ingestion/lakehouse-master?page=${lakehousePage}&page_size=${lakehousePageSize}&search=${encodeURIComponent(lakehouseSearch)}`;
        const res = await fetch(url);
        const data = await res.json();

        tbody.innerHTML = "";
        if (!data.exists || data.records.length === 0) {
          tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:2.5rem; color:var(--text-dim);">No processed invoices in lakehouse yet. Run ingestion to persist records.</td></tr>`;
          document.getElementById("lakehousePageInfo").innerText = "0 records";
          return;
        }

        data.records.forEach((row, idx) => {
          const tr = document.createElement("tr");
          const rowNum = (data.page - 1) * data.page_size + idx + 1;
          tr.innerHTML = `
            <td style="font-family:var(--font-mono); color:var(--text-dim);">${rowNum}</td>
            <td style="font-family:var(--font-mono); font-weight:600; color:var(--accent-cyan);">${row.docno || '—'}</td>
            <td>${row.docdt || '—'}</td>
            <td style="font-family:var(--font-mono);">${row.supplier_gstin || '—'}</td>
            <td style="font-family:var(--font-mono);">${row.buyer_gstin || '—'}</td>
            <td style="font-family:var(--font-mono); font-weight:600;">₹${Number(row.assval || 0).toLocaleString('en-IN', {minimumFractionDigits:2})}</td>
            <td style="font-family:var(--font-mono); font-weight:700; color:var(--accent-green);">₹${Number(row.totinvval || 0).toLocaleString('en-IN', {minimumFractionDigits:2})}</td>
            <td><span class="pill ${row.ewb_required === 'Y' ? 'pill-green' : 'pill-amber'}">${row.ewb_required || 'N'}</span></td>
            <td style="font-size:0.75rem; color:var(--text-dim);">${row.created_at || '—'}</td>
          `;
          tbody.appendChild(tr);
        });

        document.getElementById("lakehousePageInfo").innerText = `Showing ${data.records.length} of ${data.total_filtered} records`;
        document.getElementById("lakehouseCurrentPageBadge").innerText = `${data.page} / ${data.total_pages}`;
        document.getElementById("lakehousePrevBtn").disabled = (data.page <= 1);
        document.getElementById("lakehouseNextBtn").disabled = (data.page >= data.total_pages);
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:2rem; color:var(--accent-red);">${err.message}</td></tr>`;
      }
    }

    function navigateLakehousePage(delta) {
      lakehousePage += delta;
      fetchLakehouseMaster();
    }

    let lakehouseDebounce = null;
    function handleLakehouseSearch(event) {
      clearTimeout(lakehouseDebounce);
      lakehouseDebounce = setTimeout(() => {
        lakehouseSearch = event.target.value;
        lakehousePage = 1;
        fetchLakehouseMaster();
      }, 300);
    }


    // ========================================================
    // TAB 4: TRANSFORMATION AUDIT TRAIL
    // ========================================================
    async function fetchAuditTrail() {
      const tbody = document.getElementById("auditTableBody");
      try {
        const url = `/api/ingestion/audit-trail?page=${auditPage}&page_size=${auditPageSize}&search=${encodeURIComponent(auditSearch)}&category=${encodeURIComponent(auditCategory)}`;
        const res = await fetch(url);
        const data = await res.json();

        const catSelect = document.getElementById("auditCategorySelect");
        if (data.categories && data.categories.length > 0 && catSelect.options.length <= 1) {
          data.categories.forEach(cat => {
            const opt = document.createElement("option");
            opt.value = cat;
            opt.innerText = cat;
            catSelect.appendChild(opt);
          });
        }

        tbody.innerHTML = "";
        if (!data.exists || data.records.length === 0) {
          tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:2.5rem; color:var(--text-dim);">No transformation audit records found.</td></tr>`;
          document.getElementById("auditPageInfo").innerText = "0 records";
          return;
        }

        data.records.forEach(row => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td style="font-family:var(--font-mono); font-weight:600; color:var(--accent-cyan);">${row["Invoice Number"] || '—'}</td>
            <td><span class="pill pill-green">${row["Invoice Status"] || 'VALID'}</span></td>
            <td><span class="pill pill-purple">${row["Type"] || 'AUTO_CORRECTION'}</span></td>
            <td><span class="pill pill-cyan">${row["Category / Error Code"] || '—'}</span></td>
            <td style="font-family:var(--font-mono); color:#38bdf8;">${row["Field / JSON Path"] || '—'}</td>
            <td style="color:var(--accent-red); font-family:var(--font-mono);">${row["Customer Original Value"] || '—'}</td>
            <td style="color:var(--accent-green); font-family:var(--font-mono); font-weight:600;">${row["System Corrected Value"] || '—'}</td>
            <td style="font-size:0.75rem; color:var(--text-muted);">${row["Description / Rule Reason"] || '—'}</td>
          `;
          tbody.appendChild(tr);
        });

        document.getElementById("auditPageInfo").innerText = `Showing ${data.records.length} of ${data.total_records} audit entries`;
        document.getElementById("auditCurrentPageBadge").innerText = `${data.page} / ${data.total_pages}`;
        document.getElementById("auditPrevBtn").disabled = (data.page <= 1);
        document.getElementById("auditNextBtn").disabled = (data.page >= data.total_pages);
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:2rem; color:var(--accent-red);">${err.message}</td></tr>`;
      }
    }

    function navigateAuditPage(delta) {
      auditPage += delta;
      fetchAuditTrail();
    }

    function changeAuditCategory() {
      auditCategory = document.getElementById("auditCategorySelect").value;
      auditPage = 1;
      fetchAuditTrail();
    }

    let auditDebounce = null;
    function handleAuditSearch(event) {
      clearTimeout(auditDebounce);
      auditDebounce = setTimeout(() => {
        auditSearch = event.target.value;
        auditPage = 1;
        fetchAuditTrail();
      }, 300);
    }
  


        // =========================================================================
        // CONVERTER MODULE CORE LOGIC & PIPELINE CONTROLLERS
        // =========================================================================

        // Global State
        let currentMode = 'random'; // 'random' or 'custom'
        let currentRandomCount = 1;
        let pipelineData = null;
        let currentValidationReport = null;
        let currentCorrectedPayload = null;
        let initialDirtyPayloadStr = '';
        let currentLivePayload = null;
        let lastRawJsonStr = '';
        let lastCleanJsonStr = '';
        let lastSummaryText = '';
        let fullAuditRecords = [];
        let cumulativeErrorLogs = [];

        // DOM Elements
        const rawJsonEditor = document.getElementById('rawJsonEditor');
        const jsonStatusBadge = document.getElementById('jsonStatusBadge');
        const charCountLabel = document.getElementById('charCountLabel');
        const invoiceCountLabel = document.getElementById('invoiceCountLabel');
        const loadingOverlay = document.getElementById('loadingOverlay');
        const loadingText = document.getElementById('loadingText');
        const toastBox = document.getElementById('toastBox');
        const toastMessage = document.getElementById('toastMessage');

        // Initialize on page load
        window.addEventListener('DOMContentLoaded', async () => {
            initSplitResizer();
            const savedLayout = localStorage.getItem('copilot_layout_mode') || 'auto';
            setCopilotLayout(savedLayout);
            // Fetch live API module endpoint configurations
            await loadConfiguredEndpoints();
            // Load initial random batch so the user has immediate data to explore
            await handleGenerateRandom();
        });


        // Mode Switching
        function selectInputMode(mode) {
            currentMode = mode;
            const cardRandom = document.getElementById('modeCardRandom');
            const cardCustom = document.getElementById('modeCardCustom');
            const randomBox = document.getElementById('randomSettingsBox');
            const editorTitle = document.getElementById('editorPanelTitle');

            if (mode === 'random') {
                cardRandom.classList.add('active');
                cardCustom.classList.remove('active');
                randomBox.style.display = 'flex';
                editorTitle.textContent = 'Dirty Payload Inspector (Generated)';
            } else {
                cardCustom.classList.add('active');
                cardRandom.classList.remove('active');
                randomBox.style.display = 'none';
                editorTitle.textContent = 'Customer Payload Ingestion';
            }
        }

        // Pill selector for invoice count
        function setRandomCount(count, btnElement) {
            currentRandomCount = count;
            document.querySelectorAll('.pill-selector-group .pill-btn').forEach(btn => btn.classList.remove('active'));
            btnElement.classList.add('active');
            document.getElementById('selectedCountLabel').textContent = `${count} Invoice${count > 1 ? 's' : ''}`;
        }

        // Generate Random Dirty Batch via Backend API
        async function handleGenerateRandom() {
            showLoading(`Generating ${currentRandomCount} randomized invoice(s) with dirty fields...`);
            try {
                const response = await fetch('/api/converter/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ count: currentRandomCount })
                });

                if (!response.ok) {
                    throw new Error(`Server returned error ${response.status}`);
                }

                const result = await response.json();
                if (result.status === 'success' && result.payload) {
                    const dirtyStr = JSON.stringify(result.payload, null, 2);
                    rawJsonEditor.value = dirtyStr;
                    initialDirtyPayloadStr = dirtyStr;
                    currentLivePayload = result.payload;
                    validateJsonInput();
                    
                    // Silent background audit preview to initialize Copilot state
                    try {
                        const auditResp = await fetch('/api/converter/process', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ payload: result.payload })
                        });
                        if (auditResp.ok) {
                            pipelineData = await auditResp.json();
                            currentValidationReport = pipelineData.validation_report;
                            currentCorrectedPayload = pipelineData.corrected_payload;
                        }
                    } catch (auditErr) {
                        console.warn('Initial background audit preview:', auditErr);
                    }

                    showToast(`Generated ${result.count} invoice(s) with dirty field values!`, 'success');
                    // Automatically inspect and seed Copilot diagnostic with the fresh payload
                    await triggerCopilotAutoDiagnostic();
                } else {
                    throw new Error('Invalid response structure from generator API');
                }
            } catch (err) {
                console.error(err);
                showToast(`Failed to generate: ${err.message}`, 'error');
            } finally {
                hideLoading();
            }
        }

        // Load Default Sample from Backend
        async function handleLoadSample() {
            showLoading('Loading canonical sample dirty payload...');
            try {
                const response = await fetch('/api/converter/sample');
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                if (data.payload) {
                    const dirtyStr = JSON.stringify(data.payload, null, 2);
                    rawJsonEditor.value = dirtyStr;
                    initialDirtyPayloadStr = dirtyStr;
                    currentLivePayload = data.payload;
                    validateJsonInput();

                    // Silent background audit preview to initialize Copilot state
                    try {
                        const auditResp = await fetch('/api/converter/process', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ payload: data.payload })
                        });
                        if (auditResp.ok) {
                            pipelineData = await auditResp.json();
                            currentValidationReport = pipelineData.validation_report;
                            currentCorrectedPayload = pipelineData.corrected_payload;
                        }
                    } catch (auditErr) {
                        console.warn('Initial background audit preview:', auditErr);
                    }

                    showToast('Sample dirty payload loaded!', 'success');
                    // Automatically inspect and seed Copilot diagnostic with the sample payload
                    await triggerCopilotAutoDiagnostic();
                }
            } catch (err) {
                showToast(`Error loading sample: ${err.message}`, 'error');
            } finally {
                hideLoading();
            }
        }

        // File Upload Handling
        function handleFileUpload(event) {
            const file = event.target.files[0];
            if (!file) return;

            selectInputMode('custom');
            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const parsed = JSON.parse(e.target.result);
                    rawJsonEditor.value = JSON.stringify(parsed, null, 2);
                    validateJsonInput();
                    showToast(`Loaded "${file.name}" (${(file.size / 1024).toFixed(1)} KB)`, 'success');
                } catch (jsonErr) {
                    rawJsonEditor.value = e.target.result;
                    validateJsonInput();
                    showToast(`File loaded with JSON syntax warning!`, 'error');
                }
            };
            reader.readAsText(file);
        }

        // JSON Input Validation & Stats Counter
        function validateJsonInput() {
            const val = rawJsonEditor.value.trim();
            charCountLabel.textContent = `${val.length.toLocaleString()} Characters`;

            if (!val) {
                jsonStatusBadge.textContent = 'Empty';
                jsonStatusBadge.className = 'editor-status-indicator';
                invoiceCountLabel.textContent = '0 Invoices Detected';
                return false;
            }

            try {
                const parsed = JSON.parse(val);
                jsonStatusBadge.textContent = 'Valid JSON ✓';
                jsonStatusBadge.className = 'editor-status-indicator';

                let invCount = 0;
                if (Array.isArray(parsed)) {
                    invCount = parsed.length;
                } else if (parsed && typeof parsed === 'object') {
                    if (Array.isArray(parsed.einvoices)) {
                        invCount = parsed.einvoices.length;
                    } else {
                        invCount = 1;
                    }
                }
                invoiceCountLabel.textContent = `${invCount} Invoice${invCount === 1 ? '' : 's'} Detected`;
                return true;
            } catch (err) {
                jsonStatusBadge.textContent = 'Syntax Error ✗';
                jsonStatusBadge.className = 'editor-status-indicator error';
                invoiceCountLabel.textContent = 'Parsing error';
                return false;
            }
        }

        // Format / Prettify Editor Content
        function handleFormatJson() {
            try {
                const parsed = JSON.parse(rawJsonEditor.value);
                rawJsonEditor.value = JSON.stringify(parsed, null, 2);
                validateJsonInput();
                showToast('JSON beautified with 2-space indentation', 'success');
            } catch (err) {
                showToast('Cannot format: invalid JSON syntax', 'error');
            }
        }

        // Clear Editor Content
        function handleClearEditor() {
            rawJsonEditor.value = '';
            validateJsonInput();
            showToast('Editor cleared', 'success');
        }

        // Copy Text
        function handleCopyPayload() {
            copyTextToClipboard(rawJsonEditor.value, 'Payload copied to clipboard!');
        }

        // Main Conversion Pipeline Execution
        async function handleProcessPipeline() {
            const rawText = rawJsonEditor.value.trim();
            if (!rawText) {
                showToast('Please provide a JSON payload before running the pipeline', 'error');
                return;
            }

            let parsedPayload;
            try {
                parsedPayload = JSON.parse(rawText);
            } catch (err) {
                showToast('Invalid JSON syntax: please correct errors before audit', 'error');
                return;
            }

            showLoading('Running auto-corrections, NIC schema transformation, and rule audits...');

            try {
                const response = await fetch('/api/converter/process', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ payload: parsedPayload })
                });

                if (!response.ok) {
                    const errDetail = await response.json();
                    throw new Error(errDetail.detail || `HTTP Error ${response.status}`);
                }

                pipelineData = await response.json();
                currentValidationReport = pipelineData.validation_report;
                currentCorrectedPayload = pipelineData.corrected_payload;
                initialDirtyPayloadStr = JSON.stringify(parsedPayload, null, 2);
                currentLivePayload = pipelineData.corrected_payload;
                lastRawJsonStr = initialDirtyPayloadStr;
                lastCleanJsonStr = JSON.stringify(pipelineData.corrected_payload, null, 2);
                lastSummaryText = pipelineData.summary_text;
                fullAuditRecords = pipelineData.audit_records || [];

                // Render Dashboard
                renderExecutiveKPIs(pipelineData.metrics);
                renderAuditTable(fullAuditRecords);
                renderDiffPanes(lastRawJsonStr, lastCleanJsonStr);
                renderValidationCards(pipelineData.validation_report);
                renderTerminalSummary(pipelineData.summary_text);
                renderPriceAnomalyPane(pipelineData.validation_report);

                // Show Dashboard Sections
                document.getElementById('kpiDashboardSection').style.display = 'block';
                document.getElementById('outputDashboardSection').style.display = 'block';

                // Scroll smoothly down to the KPI section
                document.getElementById('kpiDashboardSection').scrollIntoView({ behavior: 'smooth' });

                showToast('Pipeline audit completed successfully!', 'success');
            } catch (err) {
                console.error(err);
                showToast(`Audit failed: ${err.message}`, 'error');
            } finally {
                hideLoading();
            }
        }

        // Render KPI Counters & Financials
        function renderExecutiveKPIs(metrics) {
            document.getElementById('kpiTotalInvoices').textContent = metrics.total_invoices || 0;
            document.getElementById('kpiValidInvoices').textContent = metrics.valid_invoices || 0;
            document.getElementById('kpiFailedInvoices').textContent = metrics.failed_invoices || 0;
            document.getElementById('kpiTotalCorrections').textContent = metrics.total_corrections || 0;

            const complianceRate = metrics.compliance_rate || 0;
            document.getElementById('kpiValidRateBadge').textContent = `${complianceRate}% Compliant`;

            const errCount = metrics.total_errors || 0;
            document.getElementById('kpiFailedRateBadge').textContent = `${errCount} Error${errCount === 1 ? '' : 's'}`;

            // Tab counter pills
            document.getElementById('tabCountCorrections').textContent = metrics.total_corrections || 0;
            document.getElementById('tabCountErrors').textContent = metrics.total_errors || 0;

            // AI Price Anomaly Metrics
            const anom = metrics.price_anomalies || {};
            const anomStatusEl = document.getElementById('finPriceAnomalyStatus');
            const anomTabCount = document.getElementById('tabCountPriceAnomalies');
            if (anomTabCount) anomTabCount.textContent = anom.total_anomalies || 0;
            if (anomStatusEl) {
                if (anom.total_anomalies > 0) {
                    anomStatusEl.innerHTML = `<span style="color:#f43f5e; font-weight:700;">🚨 ${anom.total_anomalies} Anomaly (${anom.status})</span>`;
                } else {
                    anomStatusEl.innerHTML = `<span style="color:#10b981; font-weight:700;">🛡️ Clean (0 Anomaly)</span>`;
                }
            }

            // Financial valuations
            const fin = metrics.financials || {};
            document.getElementById('finTtlassval').textContent = formatCurrency(fin.ttlassval || 0);
            document.getElementById('finCgstval').textContent = formatCurrency(fin.cgstval || 0);
            document.getElementById('finSgstval').textContent = formatCurrency(fin.sgstval || 0);
            document.getElementById('finIgstval').textContent = formatCurrency(fin.igstval || 0);
            document.getElementById('finTotinvval').textContent = formatCurrency(fin.totinvval || 0);

            // Populate category dropdown in table filter
            populateCategoryFilter(metrics.category_counts || {});
        }

        // Render AI Price Anomaly Diagnostic Table (Tab 5)
        function renderPriceAnomalyPane(report) {
            const tbody = document.getElementById('priceAnomalyTableBody');
            const overviewBadge = document.getElementById('priceAnomalyOverviewBadge');
            if (!tbody) return;
            tbody.innerHTML = '';

            const results = report?.results || [];
            let allFindings = [];

            results.forEach(invRes => {
                const invNum = invRes.invoice_number || 'INV';
                const anomReport = invRes.price_anomaly_report;
                if (anomReport && anomReport.findings) {
                    anomReport.findings.forEach(f => {
                        allFindings.push({ ...f, invoice_number: invNum });
                    });
                }
            });

            if (allFindings.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="text-align: center; padding: 36px; color: var(--text-dim);">
                            🛡️ All line items conform to statutory price benchmarks. No anomalies detected.
                        </td>
                    </tr>
                `;
                if (overviewBadge) {
                    overviewBadge.innerHTML = '<span class="pill-status status-valid">🛡️ No Price Anomalies (Clean)</span>';
                }
                return;
            }

            const anomaliesOnly = allFindings.filter(f => f.is_anomaly);
            if (overviewBadge) {
                if (anomaliesOnly.length > 0) {
                    overviewBadge.innerHTML = `<span class="pill-status status-invalid" style="background: rgba(244,63,94,0.2); color:#fda4af; border:1px solid rgba(244,63,94,0.4);">🚨 ${anomaliesOnly.length} Price Anomaly Flagged</span>`;
                } else {
                    overviewBadge.innerHTML = '<span class="pill-status status-valid">🛡️ All Items Within Normal Benchmarks</span>';
                }
            }

            allFindings.forEach(f => {
                const tr = document.createElement('tr');
                if (f.is_anomaly) {
                    tr.style.background = f.severity === 'CRITICAL' ? 'rgba(244, 63, 94, 0.08)' : 'rgba(245, 158, 11, 0.05)';
                }

                let typeBadge = '';
                if (f.anomaly_type === 'OVER_INVOICING') {
                    typeBadge = '<span class="type-pill" style="background: rgba(244,63,94,0.25); color:#fda4af; border:1px solid #f43f5e;">OVER-INVOICING</span>';
                } else if (f.anomaly_type === 'UNDER_INVOICING') {
                    typeBadge = '<span class="type-pill" style="background: rgba(245,158,11,0.25); color:#fde68a; border:1px solid #f59e0b;">UNDER-INVOICING</span>';
                } else if (f.anomaly_type === 'DECIMAL_SHIFT_TYPO') {
                    typeBadge = '<span class="type-pill" style="background: rgba(168,85,247,0.25); color:#e9d5ff; border:1px solid #a855f7;">TYPO DETECTED</span>';
                } else {
                    typeBadge = '<span class="type-pill type-correction" style="background: rgba(16,185,129,0.2); color:#6ee7b7; border:1px solid #10b981;">NORMAL</span>';
                }

                let riskMeter = '';
                if (f.risk_score >= 80) {
                    riskMeter = `<span style="color:#f43f5e; font-weight:700;">🔴 ${f.risk_score}/100 (Critical)</span>`;
                } else if (f.risk_score >= 50) {
                    riskMeter = `<span style="color:#f59e0b; font-weight:700;">🟡 ${f.risk_score}/100 (High)</span>`;
                } else if (f.risk_score > 0) {
                    riskMeter = `<span style="color:#38bdf8; font-weight:600;">🔵 ${f.risk_score}/100 (Moderate)</span>`;
                } else {
                    riskMeter = '<span style="color:#10b981; font-weight:600;">🟢 0/100 (Safe)</span>';
                }

                let actionBtn = '';
                if (f.is_anomaly) {
                    const fixRate = f.suggested_rate || f.benchmark_median;
                    actionBtn = `
                        <button type="button" class="btn-copy-url" style="margin-top:4px; font-size:0.75rem; background:rgba(99,102,241,0.25); color:#a5b4fc; border:1px solid #6366f1; cursor:pointer;" 
                            onclick="sendCopilotQuickMessage('Fix Item ${f.item_index} rate to ${fixRate}')">
                            🔧 Auto-Fix to ₹${Number(fixRate).toLocaleString('en-IN', {minimumFractionDigits: 2})}
                        </button>
                    `;
                } else {
                    actionBtn = '<span style="color:var(--text-dim); font-size:0.75rem;">Verified OK</span>';
                }

                const benchText = f.benchmark_min !== undefined ? `₹${Number(f.benchmark_min).toLocaleString('en-IN')} - ₹${Number(f.benchmark_max).toLocaleString('en-IN')}` : 'General UQC';

                tr.innerHTML = `
                    <td style="font-family:'JetBrains Mono', monospace; font-weight:700;">${escapeHtml(f.invoice_number)}</td>
                    <td><strong>Item #${f.item_index}:</strong> ${escapeHtml(f.prdnm)}</td>
                    <td><span class="field-tag">${escapeHtml(f.hsncd || '-')} / ${escapeHtml(f.uqc)}</span></td>
                    <td style="font-family:'JetBrains Mono', monospace; font-weight:700; ${f.is_anomaly ? 'color:#fda4af;' : ''}">₹${Number(f.unitrate).toLocaleString('en-IN', {minimumFractionDigits: 2})}</td>
                    <td style="font-size:0.78rem; color:var(--text-muted);">${benchText}</td>
                    <td>${typeBadge}</td>
                    <td>${riskMeter}</td>
                    <td style="max-width:320px; font-size:0.78rem; line-height:1.4;">
                        <div>${escapeHtml(f.reason)}</div>
                        ${actionBtn}
                    </td>
                `;

                tbody.appendChild(tr);
            });
        }

        function formatCurrency(val) {
            return '₹ ' + Number(val).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }

        function populateCategoryFilter(categoryCounts) {
            const select = document.getElementById('auditCategoryFilterSelect');
            select.innerHTML = '<option value="ALL">All Categories</option>';
            for (const [cat, count] of Object.entries(categoryCounts)) {
                const opt = document.createElement('option');
                opt.value = cat;
                opt.textContent = `${cat} (${count})`;
                select.appendChild(opt);
            }
        }

        // Render Tabular Audit Records (Tab 1)
        function renderAuditTable(records) {
            const tbody = document.getElementById('auditTableBody');
            tbody.innerHTML = '';

            if (!records || records.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="text-align: center; padding: 36px; color: var(--text-dim);">
                            No auto-corrections or validation errors logged for this payload.
                        </td>
                    </tr>
                `;
                return;
            }

            records.forEach(row => {
                const tr = document.createElement('tr');

                // Status pill
                const isStatusValid = row.status === 'VALID';
                const statusPill = `<span class="pill-status ${isStatusValid ? 'status-valid' : 'status-invalid'}">${escapeHtml(row.status)}</span>`;

                // Type pill
                const isCorrection = row.type === 'AUTO_CORRECTION';
                const typePill = `<span class="type-pill ${isCorrection ? 'type-correction' : 'type-error'}">${isCorrection ? 'AUTO-FIX' : 'NIC ERROR'}</span>`;

                // Value pills
                const origVal = row.original && row.original !== '-' 
                    ? `<span class="val-original">${escapeHtml(row.original)}</span>` 
                    : '<span style="color:var(--text-dim);">-</span>';

                const corrVal = row.corrected && row.corrected !== '-' 
                    ? `<span class="val-corrected">${escapeHtml(row.corrected)}</span>` 
                    : '<span style="color:var(--text-dim);">-</span>';

                tr.innerHTML = `
                    <td style="font-weight: 700; font-family: 'JetBrains Mono', monospace;">${escapeHtml(row.invoice_number)}</td>
                    <td>${statusPill}</td>
                    <td>${typePill}</td>
                    <td><span style="font-size: 0.78rem; font-weight: 600; color: #a5b4fc;">${escapeHtml(row.category)}</span></td>
                    <td><span class="field-tag">${escapeHtml(row.field)}</span></td>
                    <td>${origVal}</td>
                    <td>${corrVal}</td>
                    <td style="max-width: 320px; color: var(--text-muted); line-height: 1.4;">${escapeHtml(row.description)}</td>
                `;

                tbody.appendChild(tr);
            });
        }

        // Filter Audit Table
        function filterAuditTable() {
            const query = document.getElementById('auditTableSearchInput').value.toLowerCase().trim();
            const typeFilter = document.getElementById('auditTypeFilterSelect').value;
            const categoryFilter = document.getElementById('auditCategoryFilterSelect').value;

            const filtered = fullAuditRecords.filter(item => {
                // Type filter
                if (typeFilter !== 'ALL' && item.type !== typeFilter) return false;
                // Category filter
                if (categoryFilter !== 'ALL' && item.category !== categoryFilter) return false;
                // Text search
                if (query) {
                    const matchText = (
                        (item.invoice_number || '') + ' ' +
                        (item.field || '') + ' ' +
                        (item.category || '') + ' ' +
                        (item.description || '') + ' ' +
                        (item.original || '') + ' ' +
                        (item.corrected || '')
                    ).toLowerCase();
                    if (!matchText.includes(query)) return false;
                }
                return true;
            });

            renderAuditTable(filtered);
        }

        // Render Side-by-Side Diff (Tab 2)
        function renderDiffPanes(rawStr, cleanStr) {
            document.getElementById('diffDirtyPane').textContent = rawStr;
            document.getElementById('diffCleanPane').textContent = cleanStr;
        }

        // Render NIC Rule Validation Cards (Tab 3)
        function renderValidationCards(report) {
            const container = document.getElementById('validationCardsContainer');
            container.innerHTML = '';

            const results = report.results || [];
            if (results.length === 0) {
                container.innerHTML = '<div style="color: var(--text-dim); padding: 20px;">No invoice results available.</div>';
                return;
            }

            results.forEach((invRes, index) => {
                const card = document.createElement('div');
                card.className = 'invoice-rule-card';

                const isValid = invRes.status === 'VALID';
                const statusBadge = isValid 
                    ? '<span class="pill-status status-valid">APPROVED (VALID)</span>'
                    : '<span class="pill-status status-invalid">REJECTED (FAIL)</span>';

                let errorBlocks = '';
                if (invRes.errors && invRes.errors.length > 0) {
                    errorBlocks = invRes.errors.map(err => `
                        <div class="rule-issue-box">
                            <div>
                                <span class="rule-code-badge">NIC Code ${err.error_code}</span>
                                <span class="rule-message">Field: [${escapeHtml(err.field)}] — ${escapeHtml(err.message)}</span>
                            </div>
                            <div class="rule-meta-line">
                                <strong>Root Cause:</strong> ${escapeHtml(err.reason || 'Rule mismatch')}
                            </div>
                            ${err.resolution ? `
                                <div class="rule-resolution-line">
                                    💡 <strong>Recommended Fix:</strong> ${escapeHtml(err.resolution)}
                                </div>
                            ` : ''}
                        </div>
                    `).join('');
                } else {
                    errorBlocks = `
                        <div class="clean-pass-box">
                            <span>✓</span>
                            <span>All 18 NIC IRN Pre-Flight Validation Rules Passed Successfully. No business rule violations detected.</span>
                        </div>
                    `;
                }

                card.innerHTML = `
                    <div class="inv-card-header">
                        <div class="inv-card-title">
                            <h3>Invoice #${index + 1}: ${escapeHtml(invRes.invoice_number)}</h3>
                            ${statusBadge}
                        </div>
                        <div style="font-size: 0.8rem; color: var(--text-muted); display: flex; gap: 14px;">
                            <span>Auto-Corrections: <strong>${invRes.corrections_applied_count || 0}</strong></span>
                            <span>Errors: <strong>${invRes.error_count || 0}</strong></span>
                        </div>
                    </div>
                    <div>
                        ${errorBlocks}
                    </div>
                `;

                container.appendChild(card);
            });
        }

        // Render Terminal Summary (Tab 4)
        function renderTerminalSummary(summaryText) {
            document.getElementById('terminalSummaryBody').textContent = summaryText || 'No summary generated.';
        }

        // Switch Output Dashboard Tabs
        function switchDashboardTab(tabId, el) {
            document.querySelectorAll('.dashboard-nav-tabs .dash-tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.output-dashboard-card .tab-pane').forEach(pane => pane.classList.remove('active'));

            const targetBtn = el || (window.event && window.event.currentTarget) || document.querySelector(`.dashboard-nav-tabs .dash-tab-btn[data-tab="${tabId}"]`);
            if (targetBtn) targetBtn.classList.add('active');
            const pane = document.getElementById(tabId);
            if (pane) pane.classList.add('active');
        }

        // File Download Handler
        function downloadFile(fileType) {
            const a = document.createElement('a');
            a.href = `/api/converter/download/${fileType}`;
            a.download = '';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            showToast(`Initiating ${fileType} download...`, 'success');
        }

        // Utility: Copy to Clipboard
        function copyTextToClipboard(text, successMsg) {
            if (!text) return;
            navigator.clipboard.writeText(text).then(() => {
                showToast(successMsg, 'success');
            }).catch(() => {
                showToast('Failed to copy text', 'error');
            });
        }

        // Utility: Toast
        function showToast(msg, type = 'success') {
            toastMessage.textContent = msg;
            toastBox.className = `toast-notification show ${type === 'success' ? 'toast-success' : 'toast-error'}`;
            setTimeout(() => {
                toastBox.classList.remove('show');
            }, 3500);
        }

        // Utility: Loading
        function showLoading(msg = 'Processing GST Sentinel Pipeline...') {
            loadingText.textContent = msg;
            loadingOverlay.style.display = 'flex';
        }

        function hideLoading() {
            loadingOverlay.style.display = 'none';
        }

        // Utility: Escape HTML
        function escapeHtml(str) {
            if (str === null || str === undefined) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        // ==============================================================
        // AI COMPLIANCE COPILOT & SPLIT-SCREEN CHATBOT LOGIC
        // ==============================================================
        let copilotChatHistory = [];
        let isCopilotSplitActive = true;
        let activeCopilotLayout = localStorage.getItem('copilot_layout_mode') || 'auto';

        // Set Copilot Layout & Screen Split Width
        function setCopilotLayout(mode) {
            const splitContainer = document.getElementById('editorCopilotSplit');
            if (!splitContainer) return;
            const buttons = document.querySelectorAll('.copilot-layout-btn');
            buttons.forEach(btn => btn.classList.remove('active'));

            // Clear any inline drag styling
            splitContainer.style.gridTemplateColumns = '';

            splitContainer.classList.remove('split-half', 'split-wide', 'split-max', 'editor-only');
            activeCopilotLayout = mode;

            if (mode === 'half') {
                splitContainer.classList.add('split-half');
                document.getElementById('btnSplitHalf')?.classList.add('active');
                showToast('📐 50:50 Balanced Split Activated', 'info');
            } else if (mode === 'wide') {
                splitContainer.classList.add('split-wide');
                document.getElementById('btnSplitWide')?.classList.add('active');
                showToast('📐 Wide Chat Window Activated (65% width)', 'info');
            } else if (mode === 'full') {
                splitContainer.classList.add('split-max');
                document.getElementById('btnSplitFull')?.classList.add('active');
                showToast('⤢ Full Chat Mode Activated', 'info');
            } else {
                // 'auto'
                document.getElementById('btnSplitAuto')?.classList.add('active');
                showToast('⚡ Smart Resolution Auto-Adjust Active', 'info');
            }

            localStorage.setItem('copilot_layout_mode', mode);
        }

        // Toggle between Split Screen and Full-Width Editor
        function toggleCopilotSplit() {
            const splitContainer = document.getElementById('editorCopilotSplit');
            const toggleText = document.getElementById('toggleCopilotText');
            isCopilotSplitActive = !isCopilotSplitActive;

            if (isCopilotSplitActive) {
                splitContainer.classList.remove('editor-only');
                toggleText.textContent = 'Copilot Split';
                const savedMode = localStorage.getItem('copilot_layout_mode') || 'auto';
                setCopilotLayout(savedMode);
                showToast('AI Copilot Split-Screen Enabled', 'success');
            } else {
                splitContainer.classList.remove('split-half', 'split-wide', 'split-max');
                splitContainer.classList.add('editor-only');
                toggleText.textContent = 'Show Copilot';
                showToast('Full-Width Editor Mode Activated', 'success');
            }
        }

        // Initialize Draggable Split Resizer
        function initSplitResizer() {
            const resizer = document.getElementById('splitResizer');
            const splitContainer = document.getElementById('editorCopilotSplit');
            if (!resizer || !splitContainer) return;

            let isDragging = false;

            resizer.addEventListener('mousedown', (e) => {
                isDragging = true;
                resizer.classList.add('is-dragging');
                document.body.style.cursor = 'col-resize';
                document.body.style.userSelect = 'none';
                e.preventDefault();
            });

            window.addEventListener('mousemove', (e) => {
                if (!isDragging) return;
                const rect = splitContainer.getBoundingClientRect();
                const totalWidth = rect.width;
                if (totalWidth <= 0) return;

                // Position within splitContainer
                const mouseX = e.clientX - rect.left;
                let editorPct = (mouseX / totalWidth) * 100;

                // Bounds checking (keep editor between 22% and 78%)
                if (editorPct < 22) editorPct = 22;
                if (editorPct > 78) editorPct = 78;

                const copilotPct = 100 - editorPct;

                // Remove preset classes while custom dragging
                splitContainer.classList.remove('split-half', 'split-wide', 'split-max');
                const buttons = document.querySelectorAll('.copilot-layout-btn');
                buttons.forEach(btn => btn.classList.remove('active'));

                splitContainer.style.gridTemplateColumns = `${editorPct.toFixed(1)}% ${copilotPct.toFixed(1)}%`;
            });

            window.addEventListener('mouseup', () => {
                if (isDragging) {
                    isDragging = false;
                    resizer.classList.remove('is-dragging');
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                }
            });

            // Double click on resizer knob to reset to Auto
            resizer.addEventListener('dblclick', () => {
                setCopilotLayout('auto');
            });
        }

        // Update Copilot Status Badge in Header
        function updateCopilotHeaderStatus(validationReport) {
            const statusText = document.getElementById('copilotStatusText');
            const statusPill = document.getElementById('copilotStatusPill');
            if (!statusText) return;

            if (!validationReport || !validationReport.results || validationReport.results.length === 0) {
                statusText.textContent = 'Active';
                statusText.style.color = '#38bdf8';
                return;
            }

            const firstRes = validationReport.results[0] || {};
            const errCount = (firstRes.errors || []).length;
            if (errCount === 0) {
                statusText.textContent = '100% Compliant';
                statusText.style.color = '#10b981';
                if (statusPill) {
                    statusPill.style.borderColor = 'rgba(16, 185, 129, 0.4)';
                    const dot = statusPill.querySelector('span');
                    if (dot) dot.style.background = '#10b981';
                }
            } else {
                statusText.textContent = `${errCount} Error${errCount > 1 ? 's' : ''} Remaining`;
                statusText.style.color = '#f43f5e';
                if (statusPill) {
                    statusPill.style.borderColor = 'rgba(244, 63, 94, 0.4)';
                    const dot = statusPill.querySelector('span');
                    if (dot) dot.style.background = '#f43f5e';
                }
            }
        }

        // Trigger Automatic Diagnostic on current payload in editor
        async function triggerCopilotAutoDiagnostic(customNotice = null) {
            const feed = document.getElementById('copilotMessagesFeed');
            if (!feed) return;

            copilotChatHistory = [];

            let currentPayload = null;
            try {
                const rawEditorText = rawJsonEditor.value.trim();
                if (rawEditorText) {
                    currentPayload = JSON.parse(rawEditorText);
                }
            } catch (err) {
                currentPayload = null;
            }

            if (!currentPayload) {
                feed.innerHTML = `
                    <div class="copilot-msg bot">
                        <div class="msg-bubble">
                            👋 <strong>No valid JSON payload in editor.</strong> Load a sample payload or generate a batch to begin real-time NIC compliance audits!
                        </div>
                    </div>
                `;
                updateCopilotPills(["Load Sample", "Generate Fresh Dirty Batch", "Format JSON"]);
                updateCopilotHeaderStatus(null);
                return;
            }

            feed.innerHTML = `
                <div class="copilot-msg bot" id="copilotAutoThinking">
                    <div class="msg-bubble" style="color: var(--accent-cyan); display: flex; align-items: center; gap: 8px;">
                        <span class="pulse-dot" style="width: 8px; height: 8px; background: #38bdf8;"></span>
                        <span>Auto-detecting NIC compliance errors across active payload...</span>
                    </div>
                </div>
            `;

            try {
                const response = await fetch('/api/converter/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: "Why did my invoice fail?",
                        payload: currentPayload,
                        validation_report: currentValidationReport || null,
                        chat_history: []
                    })
                });

                const thinkingEl = document.getElementById('copilotAutoThinking');
                if (thinkingEl) thinkingEl.remove();

                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();

                const botMsgDiv = document.createElement('div');
                botMsgDiv.className = 'copilot-msg bot';

                let noticePrefix = customNotice ? `<div style="font-size:0.85rem; color:#94a3b8; margin-bottom:8px;">${escapeHtml(customNotice)}</div>` : '';
                let replyHtml = `<div class="msg-bubble">${noticePrefix}${formatMarkdownReply(data.reply)}</div>`;

                if (data.interactive_actions && data.interactive_actions.length > 0) {
                    const actionBtns = data.interactive_actions.map(act => 
                        `<button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('${escapeHtml(act)}')">${escapeHtml(act)}</button>`
                    ).join(' ');
                    replyHtml += `<div class="msg-action-bar">${actionBtns}</div>`;
                }

                botMsgDiv.innerHTML = replyHtml;
                feed.innerHTML = '';
                feed.appendChild(botMsgDiv);
                feed.scrollTop = feed.scrollHeight;

                if (data.quick_prompts && data.quick_prompts.length > 0) {
                    updateCopilotPills(data.quick_prompts);
                } else if (data.interactive_actions && data.interactive_actions.length > 0) {
                    updateCopilotPills(data.interactive_actions);
                }

                updateCopilotHeaderStatus(data.validation_report);

            } catch (err) {
                const thinkingEl = document.getElementById('copilotAutoThinking');
                if (thinkingEl) thinkingEl.remove();

                feed.innerHTML = `
                    <div class="copilot-msg bot">
                        <div class="msg-bubble">
                            👋 <strong>Inspection Ready.</strong> Tell me your GSTIN or ask to fix an error to start.
                        </div>
                    </div>
                `;
            }
        }

        // Clear Chat History and Auto-Detect Active Errors Immediately
        async function clearCopilotChat() {
            showToast('Chat cleared — re-evaluating invoice errors...', 'info');
            await triggerCopilotAutoDiagnostic('🧹 Chat history cleared. Active payload re-inspected:');
        }

        // Quick Message Pill Click
        function sendCopilotQuickMessage(text) {
            const input = document.getElementById('copilotInputBox');
            input.value = text;
            handleCopilotSubmit(new Event('submit'));
        }

        // Update Quick Prompt Pills
        function updateCopilotPills(prompts) {
            if (!prompts || !prompts.length) return;
            const container = document.getElementById('copilotPillsBar');
            container.innerHTML = prompts.map(p => `
                <button type="button" class="copilot-pill" onclick="sendCopilotQuickMessage('${escapeHtml(p)}')">
                    ${escapeHtml(p)}
                </button>
            `).join('');
        }

        // Toggle Connected Module Endpoints Hub Drawer
        function toggleEndpointsHub() {
            const body = document.getElementById('endpointsHubBody');
            const arrow = document.getElementById('endpointsToggleArrow');
            const text = document.getElementById('endpointsToggleText');
            if (!body) return;
            const isCollapsed = body.classList.toggle('is-collapsed');
            if (isCollapsed) {
                if (arrow) arrow.textContent = '▼';
                if (text) text.textContent = 'Show Details';
            } else {
                if (arrow) arrow.textContent = '▲';
                if (text) text.textContent = 'Hide Details';
            }
        }

        // Copy Endpoint URL to Clipboard
        function copyEndpointText(text, btn) {
            if (!navigator.clipboard) {
                showToast(`Endpoint: ${text}`, 'info');
                return;
            }
            navigator.clipboard.writeText(text).then(() => {
                const orig = btn.innerHTML;
                btn.innerHTML = '✓ Copied!';
                btn.style.color = '#34d399';
                showToast(`Copied URL: ${text}`, 'success');
                setTimeout(() => {
                    btn.innerHTML = orig;
                    btn.style.color = '';
                }, 2000);
            }).catch(() => {
                showToast(`Copied URL: ${text}`, 'info');
            });
        }

        // Switch Right Column View: Module Endpoints vs Copilot Assistant
        function switchRightPanelView(view) {
            const endpointsView = document.getElementById('moduleEndpointsPanelView');
            const chatView = document.getElementById('copilotChatView');
            const btnEndpoints = document.getElementById('tabBtnEndpoints');
            const btnCopilot = document.getElementById('tabBtnCopilot');
            const title = document.getElementById('panelPrimaryTitle');
            const subtitle = document.getElementById('panelPrimarySubtitle');

            if (view === 'endpoints') {
                if (endpointsView) endpointsView.style.display = 'flex';
                if (chatView) chatView.style.display = 'none';
                if (btnEndpoints) btnEndpoints.classList.add('active');
                if (btnCopilot) btnCopilot.classList.remove('active');
                if (title) title.textContent = 'Module Endpoints & Live URLs';
                if (subtitle) subtitle.textContent = 'Government Portals, API Verification & Statutory Schemas';
            } else {
                if (endpointsView) endpointsView.style.display = 'none';
                if (chatView) chatView.style.display = 'flex';
                if (btnEndpoints) btnEndpoints.classList.remove('active');
                if (btnCopilot) btnCopilot.classList.add('active');
                if (title) title.textContent = 'GST Compliance Copilot';
                if (subtitle) subtitle.textContent = 'Real-Time NIC Diagnostics & Smart Patcher';
            }
        }

        // Quick Interactive GSTIN Live Tester
        async function runLiveGstinTest() {
            const input = document.getElementById('testGstinInput');
            const resultBox = document.getElementById('testGstinResult');
            if (!input || !resultBox) return;
            const gstin = input.value.trim().toUpperCase();
            if (!gstin) {
                showToast('Please enter a GSTIN to test', 'warning');
                return;
            }
            resultBox.style.display = 'block';
            resultBox.innerHTML = '<span style="color:#38bdf8;">⏳ Querying live GSTIN API...</span>';
            try {
                const res = await fetch(`/api/converter/verify-gstin/${encodeURIComponent(gstin)}`);
                const data = await res.json();
                if (data.is_live && data.trade_name) {
                    resultBox.innerHTML = `
                        <div style="color:#10b981; font-weight:700;">🟢 LIVE VERIFIED (GST Common Portal)</div>
                        <div style="color:#ffffff;">• Legal Name: <strong>${escapeHtml(data.legal_name || data.trade_name)}</strong></div>
                        <div style="color:#94a3b8;">• Trade Name: ${escapeHtml(data.trade_name)}</div>
                        <div style="color:#94a3b8;">• State: ${escapeHtml(data.state || '')} (Code ${escapeHtml(data.state_code || '')})</div>
                        <div style="color:#94a3b8;">• Status: <span style="color:#10b981;">${escapeHtml(data.status || 'Active')}</span> | Type: ${escapeHtml(data.taxpayer_type || 'Regular')}</div>
                    `;
                } else if (data.is_valid) {
                    resultBox.innerHTML = `
                        <div style="color:#10b981; font-weight:700;">🟢 Modulo-36 Checksum Valid</div>
                        <div style="color:#ffffff;">• State: ${escapeHtml(data.state || '')} (Code ${escapeHtml(data.state_code || '')})</div>
                        <div style="color:#94a3b8;">• Entity: ${escapeHtml(data.entity_type || 'Regular')}</div>
                    `;
                } else {
                    resultBox.innerHTML = `
                        <div style="color:#f43f5e; font-weight:700;">❌ Checksum / API Notice</div>
                        <div style="color:#fca5a5;">${escapeHtml(data.error || 'Invalid GSTIN')}</div>
                        ${data.corrected_gstin ? `<div style="color:#38bdf8;">• Suggested: <code>${escapeHtml(data.corrected_gstin)}</code></div>` : ''}
                    `;
                }
            } catch (err) {
                resultBox.innerHTML = `<span style="color:#f43f5e;">Error: ${escapeHtml(err.message)}</span>`;
            }
        }

        // Quick Interactive Vehicle Plate Tester
        async function runLiveVehicleTest() {
            const input = document.getElementById('testVehInput');
            const resultBox = document.getElementById('testVehResult');
            if (!input || !resultBox) return;
            const veh = input.value.trim().toUpperCase();
            if (!veh) {
                showToast('Please enter a vehicle plate number', 'warning');
                return;
            }
            resultBox.style.display = 'block';
            resultBox.innerHTML = '<span style="color:#38bdf8;">⏳ Verifying vehicle format &amp; MoRTH jurisdiction...</span>';
            try {
                const res = await fetch(`/api/converter/verify-vehicle/${encodeURIComponent(veh)}`);
                const data = await res.json();
                if (data.is_valid) {
                    resultBox.innerHTML = `
                        <div style="color:#fbbf24; font-weight:700;">🟡 MoRTH Statutory Validated (EWB Rule 138)</div>
                        <div style="color:#ffffff;">• Jurisdiction: <strong>${escapeHtml(data.rto_name || '')}</strong></div>
                        <div style="color:#94a3b8;">• State: ${escapeHtml(data.state || '')}</div>
                        <div style="color:#94a3b8;">• Series: ${escapeHtml(data.series_type || 'State RTO')}</div>
                        <div style="margin-top:4px;"><a href="${escapeHtml(data.carinfo_url || 'https://carinfo.app/rc-search')}" target="_blank" style="color:#38bdf8; text-decoration:underline;">View RC Details on CarInfo ↗</a></div>
                    `;
                } else {
                    resultBox.innerHTML = `
                        <div style="color:#f43f5e; font-weight:700;">❌ Invalid MoRTH Vehicle Plate</div>
                        <div style="color:#fca5a5;">${escapeHtml(data.error || 'Format invalid')}</div>
                    `;
                }
            } catch (err) {
                resultBox.innerHTML = `<span style="color:#f43f5e;">Error: ${escapeHtml(err.message)}</span>`;
            }
        }

        // Fetch Live Configured Endpoints from Server and dynamically sync UI
        async function loadConfiguredEndpoints() {
            try {
                const res = await fetch('/api/converter/endpoints');
                if (!res.ok) return;
                const data = await res.json();
                if (data && data.modules) {
                    const gstinMod = data.modules.find(m => m.module_id === 'gstin');
                    const vahanMod = data.modules.find(m => m.module_id === 'vahan');
                    if (gstinMod && document.getElementById('epGstinUrl')) {
                        document.getElementById('epGstinUrl').textContent = gstinMod.url;
                    }
                    if (vahanMod && document.getElementById('epVahanUrl')) {
                        document.getElementById('epVahanUrl').textContent = vahanMod.url;
                    }
                }
            } catch (e) {
                console.warn('Could not fetch live endpoints info:', e);
            }
        }

        // Format Markdown-like text to safe HTML
        function formatMarkdownReply(text) {
            if (!text) return '';
            let html = escapeHtml(text);
            // Clickable Links [title](url)
            html = html.replace(/\[(.*?)\]\((https?:\/\/[^\s\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" style="color:#38bdf8; text-decoration:underline; font-weight:600;">$1 ↗</a>');
            // Bold **text**
            html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            // Italic *text*
            html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
            // Inline code `code`
            html = html.replace(/`(.*?)`/g, '<code>$1</code>');
            // Bullet points
            html = html.replace(/^[•\-\*]\s+(.*)$/gm, '<div style="margin-left: 12px; margin-bottom: 4px;">• $1</div>');
            // Newlines
            html = html.replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');
            return html;
        }


        // Submit message to Copilot
        async function handleCopilotSubmit(e) {
            if (e && e.preventDefault) e.preventDefault();
            const input = document.getElementById('copilotInputBox');
            const sendBtn = document.getElementById('copilotSendBtn');
            const feed = document.getElementById('copilotMessagesFeed');
            const message = (input.value || '').trim();

            if (!message) return;

            // 1. Append User Message
            const userMsgDiv = document.createElement('div');
            userMsgDiv.className = 'copilot-msg user';
            userMsgDiv.innerHTML = `<div class="msg-bubble">${escapeHtml(message)}</div>`;
            feed.appendChild(userMsgDiv);

            input.value = '';
            input.disabled = true;
            sendBtn.disabled = true;
            feed.scrollTop = feed.scrollHeight;

            // Add thinking indicator
            const typingDiv = document.createElement('div');
            typingDiv.className = 'copilot-msg bot';
            typingDiv.id = 'copilotTypingIndicator';
            typingDiv.innerHTML = `
                <div class="msg-bubble" style="color: var(--accent-cyan); display: flex; align-items: center; gap: 8px;">
                    <span class="pulse-dot" style="width: 8px; height: 8px; background: #38bdf8;"></span>
                    <span>Analyzing compliance rules & payload...</span>
                </div>
            `;
            feed.appendChild(typingDiv);
            feed.scrollTop = feed.scrollHeight;

            // 2. Prepare payload from active state or raw editor
            let currentPayload = currentLivePayload;
            if (!currentPayload) {
                try {
                    const rawEditorText = rawJsonEditor.value.trim();
                    if (rawEditorText) {
                        currentPayload = JSON.parse(rawEditorText);
                        initialDirtyPayloadStr = rawEditorText;
                    }
                } catch (err) {
                    currentPayload = null;
                }
            }

            try {
                const response = await fetch('/api/converter/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: message,
                        payload: currentPayload,
                        validation_report: currentValidationReport || null,
                        chat_history: copilotChatHistory
                    })
                });

                // Remove typing indicator
                const typingEl = document.getElementById('copilotTypingIndicator');
                if (typingEl) typingEl.remove();

                if (!response.ok) {
                    throw new Error(`Server returned HTTP ${response.status}`);
                }

                const data = await response.json();

                // 3. Render Assistant Reply
                const botMsgDiv = document.createElement('div');
                botMsgDiv.className = 'copilot-msg bot';

                let replyHtml = `<div class="msg-bubble">${formatMarkdownReply(data.reply)}</div>`;

                // Interactive Action Buttons inside Chat Bubble
                if (data.interactive_actions && data.interactive_actions.length > 0) {
                    const actionBtns = data.interactive_actions.map(act => 
                        `<button type="button" class="copilot-action-btn" onclick="sendCopilotQuickMessage('${escapeHtml(act)}')">${escapeHtml(act)}</button>`
                    ).join(' ');
                    replyHtml += `<div class="msg-action-bar">${actionBtns}</div>`;
                }

                if (data.patch_applied && data.patch_summary && data.patch_summary.length > 0) {
                    const patchTags = data.patch_summary.map(s => `<div>⚡ ${escapeHtml(s)}</div>`).join('');
                    replyHtml += `
                        <div class="msg-patch-banner">
                            <div>${patchTags}</div>
                        </div>
                    `;
                }

                botMsgDiv.innerHTML = replyHtml;
                feed.appendChild(botMsgDiv);
                feed.scrollTop = feed.scrollHeight;

                // 4. Update Chat History
                copilotChatHistory.push({ role: 'user', text: message });
                copilotChatHistory.push({ role: 'assistant', text: data.reply });

                // 5. Update Quick Pills
                if (data.quick_prompts) {
                    updateCopilotPills(data.quick_prompts);
                }

                // 6. If Patch was Applied: Automatically update the Live UI Screens!
                if (data.patch_applied && data.updated_payload) {
                    currentLivePayload = data.updated_payload;
                    if (!initialDirtyPayloadStr && rawJsonEditor.value.trim()) {
                        initialDirtyPayloadStr = rawJsonEditor.value.trim();
                    }

                    // Keep Customer Raw Dirty Input showing the DIRTY payload only!
                    // Do NOT overwrite rawJsonEditor or diffDirtyPane with clean/patched payload.
                    if (!rawJsonEditor.value.trim() && initialDirtyPayloadStr) {
                        rawJsonEditor.value = initialDirtyPayloadStr;
                    }
                    validateJsonInput();

                    // 6A. Synchronize Side-by-Side Diff Panes (Tab 2)
                    // Left Pane: Customer Raw Dirty Input ONLY!
                    // Right Pane: Clean Normalized Patched NIC Payload!
                    lastRawJsonStr = initialDirtyPayloadStr || rawJsonEditor.value;
                    lastCleanJsonStr = data.corrected_payload 
                        ? JSON.stringify(data.corrected_payload, null, 2) 
                        : JSON.stringify(data.updated_payload, null, 2);

                    if (typeof renderDiffPanes === 'function') {
                        renderDiffPanes(lastRawJsonStr, lastCleanJsonStr);
                    }

                    // 6B. Synchronize Validation Cards & Tab Error Counts (Tab 3)
                    if (data.validation_report) {
                        currentValidationReport = data.validation_report;
                        currentCorrectedPayload = data.corrected_payload || data.updated_payload;

                        // Render Cards
                        renderValidationCards(currentValidationReport);

                        // Update Status Badge on Copilot Header
                        updateCopilotHeaderStatus(currentValidationReport);

                        // Update Tab Counter Pills (Tab 1 Corrections & Tab 3 Errors)
                        const firstRes = (currentValidationReport.results || [])[0] || {};
                        const errCount = firstRes.error_count ?? (firstRes.errors || []).length;
                        const corrCount = firstRes.corrections_applied_count ?? (firstRes.corrections_applied || []).length;
                        const tabErrEl = document.getElementById('tabCountErrors');
                        if (tabErrEl) tabErrEl.textContent = errCount;
                        const tabCorrEl = document.getElementById('tabCountCorrections');
                        if (tabCorrEl) tabCorrEl.textContent = corrCount;
                    }

                    // 6C. Synchronize Terminal Summary Report (Tab 4)
                    if (data.summary_text) {
                        lastSummaryText = data.summary_text;
                        if (typeof renderTerminalSummary === 'function') {
                            renderTerminalSummary(data.summary_text);
                        }
                    }

                    // 6D. Synchronize Audit Records Table (Tab 1)
                    if (data.audit_records && Array.isArray(data.audit_records)) {
                        fullAuditRecords = data.audit_records;
                        if (typeof renderAuditTable === 'function') {
                            renderAuditTable(fullAuditRecords);
                        }
                    }

                    // 6E. Synchronize Executive KPIs & Financials
                    if (data.metrics && typeof renderExecutiveKPIs === 'function') {
                        renderExecutiveKPIs(data.metrics);
                    }

                    // 6F. Ensure Output Dashboard & KPI Sections are visible
                    const kpiSec = document.getElementById('kpiDashboardSection');
                    if (kpiSec) kpiSec.style.display = 'block';
                    const outSec = document.getElementById('outputDashboardSection');
                    if (outSec) outSec.style.display = 'block';

                    showToast('⚡ All screens & output tabs synchronized in real-time!', 'success');
                }

            } catch (err) {
                const typingEl = document.getElementById('copilotTypingIndicator');
                if (typingEl) typingEl.remove();

                const botMsgDiv = document.createElement('div');
                botMsgDiv.className = 'copilot-msg bot';
                botMsgDiv.innerHTML = `<div class="msg-bubble" style="color: #fca5a5;">⚠️ <strong>Error contacting Copilot:</strong> ${escapeHtml(err.message)}</div>`;
                feed.appendChild(botMsgDiv);
                feed.scrollTop = feed.scrollHeight;
            } finally {
                input.disabled = false;
                sendBtn.disabled = false;
                input.focus();
            }
        }
    

        // Connect Ingestion Persist button to backend Lakehouse persistence
        async function persistLivePayload() {
            const rawEditorText = rawJsonEditor ? rawJsonEditor.value.trim() : document.getElementById("payloadEditor")?.value.trim();
            if (!rawEditorText) {
                showToast("Please enter or generate a payload to persist", "warning");
                return;
            }
            let parsedPayload;
            try {
                parsedPayload = JSON.parse(rawEditorText);
            } catch (e) {
                showToast("Invalid JSON syntax: " + e.message, "error");
                return;
            }

            showLoading();
            try {
                const res = await fetch("/api/ingestion/persist", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(parsedPayload)
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || "Persistence failed");
                }

                const data = await res.json();
                showToast(`Persisted invoice ${data.invoice_number} to Parquet lakehouse (+${data.parquet_row_count} rows)`, "success");
                fetchDashboardStats();
                fetchLakehouseMaster();
                fetchAuditTrail();
            } catch (err) {
                showToast(err.message, "error");
            } finally {
                hideLoading();
            }
        }

        // Enhance renderDiffPanes to also populate canonical NIC and EWB panes
        const origRenderDiffPanes = typeof renderDiffPanes === 'function' ? renderDiffPanes : null;
        renderDiffPanes = function(rawStr, cleanStr) {
            if (origRenderDiffPanes) origRenderDiffPanes(rawStr, cleanStr);
            if (pipelineData) {
                const nicPre = document.getElementById('nicPayloadPre');
                const ewbPre = document.getElementById('ewbPayloadPre');
                if (nicPre) nicPre.textContent = JSON.stringify(pipelineData.nic_irp_payload || pipelineData.corrected_payload, null, 2);
                if (ewbPre) ewbPre.textContent = JSON.stringify(pipelineData.standalone_ewb_payload || pipelineData.corrected_payload, null, 2);
            }
        };

  