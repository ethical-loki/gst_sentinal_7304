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
  


        