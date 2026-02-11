-- nexus.nvim - NEXUS integration for Neovim
-- Talks to the NEXUS server running on localhost:4200
--
-- Installation:
--   Copy this file to ~/.config/nvim/lua/nexus.lua
--   Add to your init.lua:
--     require('nexus').setup()
--
-- Commands:
--   :Nexus <message>        - Send any message (CEO natural language)
--   :NexusTalk <agent> <msg> - Talk to a specific agent
--   :NexusOrg               - Show current org chart
--   :NexusStatus            - Show server status
--   :NexusKpi               - Show KPI dashboard
--   :NexusCost              - Show cost report
--
-- Keymaps (after setup):
--   <leader>nx  - Open NEXUS prompt
--   <leader>no  - Show org
--   <leader>ns  - Show status
--   <leader>nk  - Show KPIs

local M = {}

M.config = {
  host = "127.0.0.1",
  port = 4200,
  float_width = 0.8,
  float_height = 0.8,
  keymaps = true,
}

-- HTTP client using curl (works everywhere, no dependencies)
local function http_request(method, path, body, callback)
  local url = string.format("http://%s:%d%s", M.config.host, M.config.port, path)

  local cmd
  if method == "GET" then
    cmd = string.format("curl -s -X GET '%s'", url)
  else
    local json_body = vim.fn.json_encode(body or {})
    -- Escape single quotes in the JSON for shell safety
    json_body = json_body:gsub("'", "'\\''")
    cmd = string.format(
      "curl -s -X POST '%s' -H 'Content-Type: application/json' -d '%s'",
      url, json_body
    )
  end

  vim.fn.jobstart(cmd, {
    stdout_buffered = true,
    on_stdout = function(_, data)
      if data and data[1] and data[1] ~= "" then
        local raw = table.concat(data, "\n")
        local ok, result = pcall(vim.fn.json_decode, raw)
        if ok then
          vim.schedule(function() callback(nil, result) end)
        else
          vim.schedule(function() callback("JSON parse error: " .. raw, nil) end)
        end
      end
    end,
    on_stderr = function(_, data)
      if data and data[1] and data[1] ~= "" then
        vim.schedule(function()
          callback("NEXUS server not reachable. Is it running?", nil)
        end)
      end
    end,
  })
end

-- Floating window for results
local function open_float(title, lines)
  local width = math.floor(vim.o.columns * M.config.float_width)
  local height = math.floor(vim.o.lines * M.config.float_height)
  local row = math.floor((vim.o.lines - height) / 2)
  local col = math.floor((vim.o.columns - width) / 2)

  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(buf, "modifiable", false)
  vim.api.nvim_buf_set_option(buf, "filetype", "markdown")

  local win = vim.api.nvim_open_win(buf, true, {
    relative = "editor",
    width = width,
    height = height,
    row = row,
    col = col,
    style = "minimal",
    border = "rounded",
    title = " " .. title .. " ",
    title_pos = "center",
  })

  -- Close on q or Esc
  vim.api.nvim_buf_set_keymap(buf, "n", "q", ":close<CR>", { noremap = true, silent = true })
  vim.api.nvim_buf_set_keymap(buf, "n", "<Esc>", ":close<CR>", { noremap = true, silent = true })

  return buf, win
end

-- Format a result dict into readable lines
local function format_result(result)
  local lines = {}

  if result.error then
    table.insert(lines, "ERROR: " .. result.error)
    return lines
  end

  if result.category then
    table.insert(lines, "Category: " .. result.category)
    table.insert(lines, "")
  end

  if result.summary then
    table.insert(lines, "Summary: " .. result.summary)
    table.insert(lines, "")
  end

  if result.answer then
    table.insert(lines, "--- Answer ---")
    for line in result.answer:gmatch("[^\n]+") do
      table.insert(lines, line)
    end
  end

  if result.result then
    table.insert(lines, "--- Result ---")
    for line in result.result:gmatch("[^\n]+") do
      table.insert(lines, line)
    end
  end

  if result.response then
    table.insert(lines, "--- " .. (result.agent or "Agent") .. " ---")
    for line in result.response:gmatch("[^\n]+") do
      table.insert(lines, line)
    end
  end

  if result.org_summary then
    table.insert(lines, "")
    table.insert(lines, "--- Updated Org ---")
    for line in result.org_summary:gmatch("[^\n]+") do
      table.insert(lines, line)
    end
  end

  if result.dashboard then
    for line in result.dashboard:gmatch("[^\n]+") do
      table.insert(lines, line)
    end
  end

  if result.reporting_tree then
    table.insert(lines, "--- Reporting Tree ---")
    for line in result.reporting_tree:gmatch("[^\n]+") do
      table.insert(lines, line)
    end
  end

  if result.message then
    table.insert(lines, result.message)
  end

  if result.cost then
    table.insert(lines, "")
    table.insert(lines, string.format("Cost: $%.4f", result.cost))
  end

  if #lines == 0 then
    -- Fallback: pretty print the whole thing
    local encoded = vim.fn.json_encode(result)
    for line in encoded:gmatch("[^\n]+") do
      table.insert(lines, line)
    end
  end

  return lines
end

-- ============================================
-- PUBLIC API
-- ============================================

function M.message(text)
  vim.notify("NEXUS: Processing...", vim.log.levels.INFO)
  http_request("POST", "/message", {
    message = text,
    source = "ide",
    project_path = vim.fn.getcwd(),
  }, function(err, result)
    if err then
      vim.notify("NEXUS: " .. err, vim.log.levels.ERROR)
      return
    end
    local lines = format_result(result)
    open_float("NEXUS", lines)
  end)
end

function M.talk(agent, text)
  vim.notify("NEXUS: Talking to " .. agent .. "...", vim.log.levels.INFO)
  http_request("POST", "/talk", {
    agent_name = agent,
    message = text,
    source = "ide",
  }, function(err, result)
    if err then
      vim.notify("NEXUS: " .. err, vim.log.levels.ERROR)
      return
    end
    local lines = format_result(result)
    open_float("NEXUS - " .. (result.agent or agent), lines)
  end)
end

function M.org()
  http_request("GET", "/org", nil, function(err, result)
    if err then
      vim.notify("NEXUS: " .. err, vim.log.levels.ERROR)
      return
    end
    local lines = {}
    if result.reporting_tree then
      table.insert(lines, "NEXUS Organization")
      table.insert(lines, string.rep("=", 40))
      table.insert(lines, "")
      for line in result.reporting_tree:gmatch("[^\n]+") do
        table.insert(lines, line)
      end
    end
    if result.summary then
      table.insert(lines, "")
      for line in result.summary:gmatch("[^\n]+") do
        table.insert(lines, line)
      end
    end
    open_float("NEXUS Org", lines)
  end)
end

function M.status()
  http_request("GET", "/status", nil, function(err, result)
    if err then
      vim.notify("NEXUS: " .. err, vim.log.levels.ERROR)
      return
    end
    local lines = {
      "NEXUS Server Status",
      string.rep("=", 40),
      "",
      "Status:          " .. (result.status or "unknown"),
      "Active Agents:   " .. (result.active_agents or 0),
      "Active Sessions: " .. (result.active_sessions or 0),
      "Active Runs:     " .. (result.active_runs or 0),
      string.format("Total Cost:      $%.2f", result.total_cost or 0),
      string.format("Hourly Rate:     $%.2f/hr", result.hourly_rate or 0),
    }
    if result.sessions and #result.sessions > 0 then
      table.insert(lines, "")
      table.insert(lines, "Sessions:")
      for _, s in ipairs(result.sessions) do
        table.insert(lines, string.format("  [%s] %s", s.status, s.directive))
      end
    end
    open_float("NEXUS Status", lines)
  end)
end

function M.kpi()
  http_request("POST", "/command", {
    command = "kpi",
    source = "ide",
  }, function(err, result)
    if err then
      vim.notify("NEXUS: " .. err, vim.log.levels.ERROR)
      return
    end
    local lines = format_result(result)
    open_float("NEXUS KPIs", lines)
  end)
end

function M.cost()
  http_request("POST", "/command", {
    command = "cost",
    source = "ide",
  }, function(err, result)
    if err then
      vim.notify("NEXUS: " .. err, vim.log.levels.ERROR)
      return
    end
    local lines = {
      "NEXUS Cost Report",
      string.rep("=", 40),
      "",
      string.format("Total Cost:   $%.2f", result.total_cost or 0),
      string.format("Hourly Rate:  $%.2f/hr", result.hourly_rate or 0),
      "Over Budget:  " .. tostring(result.over_budget or false),
    }
    if result.by_model then
      table.insert(lines, "")
      table.insert(lines, "By Model:")
      for model, cost in pairs(result.by_model) do
        table.insert(lines, string.format("  %s: $%.4f", model, cost))
      end
    end
    if result.by_agent then
      table.insert(lines, "")
      table.insert(lines, "By Agent:")
      for agent, cost in pairs(result.by_agent) do
        table.insert(lines, string.format("  %s: $%.4f", agent, cost))
      end
    end
    open_float("NEXUS Cost", lines)
  end)
end

-- ============================================
-- SETUP
-- ============================================

function M.setup(opts)
  M.config = vim.tbl_deep_extend("force", M.config, opts or {})

  -- Register commands
  vim.api.nvim_create_user_command("Nexus", function(cmd)
    M.message(cmd.args)
  end, { nargs = "+", desc = "Send a message to NEXUS" })

  vim.api.nvim_create_user_command("NexusTalk", function(cmd)
    local args = vim.split(cmd.args, " ", { trimempty = true })
    if #args < 2 then
      vim.notify("Usage: :NexusTalk <agent> <message>", vim.log.levels.WARN)
      return
    end
    local agent = table.remove(args, 1)
    M.talk(agent, table.concat(args, " "))
  end, { nargs = "+", desc = "Talk to a NEXUS agent" })

  vim.api.nvim_create_user_command("NexusOrg", function()
    M.org()
  end, { desc = "Show NEXUS org chart" })

  vim.api.nvim_create_user_command("NexusStatus", function()
    M.status()
  end, { desc = "Show NEXUS server status" })

  vim.api.nvim_create_user_command("NexusKpi", function()
    M.kpi()
  end, { desc = "Show NEXUS KPI dashboard" })

  vim.api.nvim_create_user_command("NexusCost", function()
    M.cost()
  end, { desc = "Show NEXUS cost report" })

  -- Keymaps
  if M.config.keymaps then
    vim.keymap.set("n", "<leader>nx", function()
      vim.ui.input({ prompt = "NEXUS> " }, function(input)
        if input and input ~= "" then
          M.message(input)
        end
      end)
    end, { desc = "NEXUS: Send message" })

    vim.keymap.set("n", "<leader>no", M.org, { desc = "NEXUS: Show org" })
    vim.keymap.set("n", "<leader>ns", M.status, { desc = "NEXUS: Status" })
    vim.keymap.set("n", "<leader>nk", M.kpi, { desc = "NEXUS: KPIs" })
    vim.keymap.set("n", "<leader>nc", M.cost, { desc = "NEXUS: Cost" })
  end

  vim.notify("NEXUS: Plugin loaded. Server at " .. M.config.host .. ":" .. M.config.port, vim.log.levels.INFO)
end

return M
