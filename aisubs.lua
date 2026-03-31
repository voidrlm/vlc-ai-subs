--[[
vlc-ai-subs — VLC extension for AI-powered subtitle generation.

Compatible with VLC 3.x and VLC 4.x.

Two modes:
  1. Real-time OSD  — transcribes then shows subtitles via OSD
  2. Generate & Load — full SRT is created then loaded synced to playback

Requires: Python 3 + faster-whisper (or openai-whisper)
Install:  Run setup.sh (Linux/macOS) or setup.bat (Windows).

https://github.com/voidrlm/vlc-ai-subs
]]

function descriptor()
    return {
        title = "AI Subs Generator",
        version = "3.2",
        author = "voidrlm",
        url = "https://github.com/voidrlm/vlc-ai-subs",
        shortdesc = "AI subtitle generator (Whisper)",
        description = "Generate subtitles using Whisper AI. "
            .. "Real-time OSD or generate-and-load SRT. "
            .. "Compatible with VLC 3.x and 4.x.",
        capabilities = {"menu"},
    }
end

local dlg          = nil
local model_dropdown = nil
local lang_input   = nil
local task_dropdown = nil
local mode_dropdown = nil
local status_label = nil
local osd_channel  = nil

-- Polling state (set by start_generation, used by poll_progress)
local _poll_tmp   = nil
local _poll_mode  = nil
local _poll_model = nil
local _poll_tmr   = nil
local _poll_secs  = 0
local POLL_US     = 3000000  -- poll every 3 seconds

----------------------------------------------------------------
-- Lifecycle
----------------------------------------------------------------

function activate()   create_dialog() end
function deactivate() if dlg then dlg:delete(); dlg = nil end end
function close()      deactivate() end

function menu() return {"Generate Subtitles"} end
function trigger_menu(id) if id == 1 then create_dialog() end end

----------------------------------------------------------------
-- Dialog
----------------------------------------------------------------

function create_dialog()
    if dlg then dlg:delete() end
    dlg = vlc.dialog("AI Subs Generator")

    dlg:add_label("Mode:", 1, 1, 1, 1)
    mode_dropdown = dlg:add_dropdown(2, 1, 2, 1)
    mode_dropdown:add_value("Real-time OSD", 1)
    mode_dropdown:add_value("Generate & Load SRT", 2)

    dlg:add_label("Model:", 1, 2, 1, 1)
    model_dropdown = dlg:add_dropdown(2, 2, 2, 1)
    model_dropdown:add_value("tiny (fastest)", 1)
    model_dropdown:add_value("base (balanced)", 2)
    model_dropdown:add_value("small (accurate)", 3)
    model_dropdown:add_value("medium (very accurate)", 4)
    model_dropdown:add_value("large (best quality)", 5)

    dlg:add_label("Language:", 1, 3, 1, 1)
    lang_input = dlg:add_text_input("auto", 2, 3, 2, 1)

    dlg:add_label("Task:", 1, 4, 1, 1)
    task_dropdown = dlg:add_dropdown(2, 4, 2, 1)
    task_dropdown:add_value("Transcribe (same language)", 1)
    task_dropdown:add_value("Translate to English", 2)

    dlg:add_button("Generate", start_generation, 1, 5, 3, 1)
    status_label = dlg:add_label("Ready. Play a media file and click Generate.", 1, 6, 3, 1)
    dlg:show()
end

----------------------------------------------------------------
-- Dropdown helpers
----------------------------------------------------------------

function get_model_name()
    local models = {"tiny", "base", "small", "medium", "large"}
    local id = model_dropdown:get_value()
    if id and id >= 1 and id <= 5 then return models[id] end
    return "base"
end

function get_task()
    if task_dropdown:get_value() == 2 then return "translate" end
    return "transcribe"
end

function get_mode()
    if mode_dropdown:get_value() == 2 then return "srt" end
    return "realtime"
end

----------------------------------------------------------------
-- VLC version compatibility (3.x / 4.x)
----------------------------------------------------------------

function get_input_item()
    local ok, item
    ok, item = pcall(function() return vlc.player.item() end)
    if ok and item then return item end
    ok, item = pcall(function() return vlc.input.item() end)
    if ok and item then return item end
    return nil
end

function add_subtitle_track(srt_path)
    local ok
    ok = pcall(function() vlc.player.add_subtitle(srt_path) end)
    if ok then return true end
    ok = pcall(function() vlc.input.add_subtitle(srt_path) end)
    if ok then return true end
    ok = pcall(function()
        local input = vlc.object.input()
        if input then vlc.var.set(input, "sub-file", srt_path) end
    end)
    return ok
end

function register_osd()
    local ok, ch = pcall(function() return vlc.osd.channel_register() end)
    if ok and ch then return ch end
    return 1
end

function show_osd(text, duration)
    if not text then return end
    local ok = pcall(function()
        vlc.osd.message(text, osd_channel, "bottom", duration)
    end)
    if not ok then
        pcall(function() vlc.osd.message(text, osd_channel) end)
    end
end

----------------------------------------------------------------
-- Path helpers
----------------------------------------------------------------

function is_windows()
    return package.config:sub(1, 1) == "\\"
end

function get_home()
    -- USERPROFILE is the standard Windows home directory variable
    local home = os.getenv("USERPROFILE") or os.getenv("HOME") or ""
    return home
end

function get_temp_file()
    local tmp
    if is_windows() then
        tmp = os.getenv("TEMP") or os.getenv("TMP") or (get_home() .. "\\AppData\\Local\\Temp")
        return tmp .. "\\aisubs_" .. os.time() .. ".txt"
    else
        tmp = os.getenv("TMPDIR") or "/tmp"
        return tmp .. "/aisubs_" .. os.time() .. ".txt"
    end
end

----------------------------------------------------------------
-- Media path
----------------------------------------------------------------

function get_media_path()
    local item = get_input_item()
    if not item then return nil, "No media is currently playing." end
    local uri = item:uri()
    if not uri then return nil, "Cannot get media URI." end
    if not string.find(uri, "^file://") then return nil, "Only local files are supported." end

    -- Strip file:// prefix
    local path = string.gsub(uri, "^file://", "")

    -- URL-decode percent-encoded characters
    path = string.gsub(path, "%%(%x%x)", function(hex)
        return string.char(tonumber(hex, 16))
    end)

    -- On Windows, VLC produces file:///C:/path → after strip → /C:/path
    -- Remove the leading slash before the drive letter
    if is_windows() then
        path = string.gsub(path, "^/([A-Za-z]:)", "%1")
        path = string.gsub(path, "/", "\\")
    end

    vlc.msg.info("[AI Subs] media path: " .. path)
    return path, nil
end

----------------------------------------------------------------
-- Locate the Python backend script
----------------------------------------------------------------

function find_script()
    local home = get_home()
    local candidates = {}

    if is_windows() then
        local appdata = os.getenv("APPDATA") or (home .. "\\AppData\\Roaming")
        table.insert(candidates, home .. "\\Documents\\vlc-ai-subs\\aisubs_whisper.py")
        table.insert(candidates, home .. "\\Desktop\\vlc-ai-subs\\aisubs_whisper.py")
        table.insert(candidates, home .. "\\Desktop\\aisubs\\aisubs_whisper.py")
        table.insert(candidates, home .. "\\vlc-ai-subs\\aisubs_whisper.py")
        table.insert(candidates, appdata .. "\\vlc-ai-subs\\aisubs_whisper.py")
        table.insert(candidates, "C:\\vlc-ai-subs\\aisubs_whisper.py")
    else
        table.insert(candidates, home .. "/Desktop/vlc-ai-subs/aisubs_whisper.py")
        table.insert(candidates, home .. "/Desktop/aisubs/aisubs_whisper.py")
        table.insert(candidates, home .. "/vlc-ai-subs/aisubs_whisper.py")
        table.insert(candidates, home .. "/.local/share/vlc-ai-subs/aisubs_whisper.py")
        table.insert(candidates, "/opt/vlc-ai-subs/aisubs_whisper.py")
        table.insert(candidates, "/usr/local/share/vlc-ai-subs/aisubs_whisper.py")
    end

    for _, path in ipairs(candidates) do
        local f = io.open(path, "r")
        if f then f:close(); return path end
    end
    return nil
end

function find_python(script_dir)
    local sep = is_windows() and "\\" or "/"

    -- venv on Unix
    local p = script_dir .. sep .. "venv" .. sep .. "bin" .. sep .. "python3"
    local f = io.open(p, "r")
    if f then f:close(); return p end

    -- venv on Windows
    p = script_dir .. sep .. "venv" .. sep .. "Scripts" .. sep .. "python.exe"
    f = io.open(p, "r")
    if f then f:close(); return p end

    return is_windows() and "python" or "python3"
end

----------------------------------------------------------------
-- Main entry
----------------------------------------------------------------

function start_generation()
    -- Cancel any in-progress transcription
    if _poll_tmr then
        pcall(function() _poll_tmr:cancel() end)
        _poll_tmr = nil
    end

    local media_path, err = get_media_path()
    if not media_path then
        set_status("Error: " .. err)
        return
    end

    local script = find_script()
    if not script then
        set_status("Error: aisubs_whisper.py not found. Run setup.sh first.")
        return
    end

    local script_dir = string.match(script, "(.+)[/\\][^/\\]+$") or "."
    local python    = find_python(script_dir)
    local model     = get_model_name()
    local language  = lang_input:get_text() or "auto"
    local task      = get_task()
    local mode      = get_mode()
    local tmp_file  = get_temp_file()

    -- Write sentinel so we can detect if Python started writing
    local test_f = io.open(tmp_file, "w")
    if not test_f then
        set_status("Error: cannot write to temp dir: " .. tmp_file)
        return
    end
    test_f:write("init\n")
    test_f:close()

    -- Build and launch command NON-BLOCKING so VLC's thread is not frozen.
    -- Windows: VBScript with bWaitOnReturn=False → wscript exits immediately.
    -- Unix:    trailing & → shell forks Python and exits immediately.
    -- In both cases io.popen returns at once and we poll tmp_file via vlc.timer.
    local cmd
    if is_windows() then
        local vbs_file = string.gsub(tmp_file, "%.txt$", ".vbs")
        local vf = io.open(vbs_file, "w")
        if not vf then
            set_status("Error: cannot write helper file: " .. vbs_file)
            return
        end
        -- In VBScript string literals a literal double-quote is written as ""
        local raw_cmd = string.format('"%s" -u "%s" "%s" "%s" "%s" "%s" "%s"',
            python, script, media_path, model, language, task, tmp_file)
        local vbs_cmd = raw_cmd:gsub('"', '""')
        vf:write('Set sh = CreateObject("WScript.Shell")\n')
        vf:write('sh.Run "' .. vbs_cmd .. '", 0, False\n')  -- 0=hidden, False=don't wait
        vf:close()
        cmd = 'wscript.exe /nologo "' .. vbs_file .. '"'
    else
        cmd = string.format('"%s" -u "%s" "%s" "%s" "%s" "%s" "%s" &',
            python, script, media_path, model, language, task, tmp_file)
    end

    vlc.msg.info("[AI Subs] python: " .. python)
    vlc.msg.info("[AI Subs] media:  " .. media_path)
    vlc.msg.info("[AI Subs] tmp:    " .. tmp_file)

    local pipe = io.popen(cmd)
    if not pipe then
        set_status("Error: failed to launch Python. Check VLC logs.")
        return
    end
    pipe:read("*a")  -- returns immediately (process is backgrounded)
    pipe:close()

    -- Poll tmp_file every 3 s; VLC's thread stays free the whole time
    _poll_tmp   = tmp_file
    _poll_mode  = mode
    _poll_model = model
    _poll_secs  = 0
    set_status("Transcribing with " .. model .. "... please wait")
    _poll_tmr = vlc.timer(poll_progress)
    _poll_tmr:schedule(POLL_US)
end

----------------------------------------------------------------
-- Polling callback — called by vlc.timer every POLL_US microseconds
----------------------------------------------------------------

function poll_progress()
    _poll_secs = _poll_secs + (POLL_US / 1000000)

    local f = io.open(_poll_tmp, "r")
    if not f then
        -- Temp file gone — shouldn't happen; keep waiting
        set_status(string.format("Transcribing with %s... %ds", _poll_model, _poll_secs))
        _poll_tmr:schedule(POLL_US)
        return
    end

    local last_line = nil
    for line in f:lines() do last_line = line end
    f:close()

    if not last_line or last_line == "init" then
        -- Python hasn't written output yet
        set_status(string.format("Loading model / starting... %ds", _poll_secs))
        _poll_tmr:schedule(POLL_US)
        return
    end

    local d = parse_json(last_line)
    if d and (d.type == "done" or d.type == "error") then
        -- Python finished — process results
        _poll_tmr = nil
        process_results(_poll_tmp, _poll_mode)
    else
        set_status(string.format("Transcribing with %s... %ds", _poll_model, _poll_secs))
        _poll_tmr:schedule(POLL_US)
    end
end

----------------------------------------------------------------
-- Process results from temp file
----------------------------------------------------------------

function process_results(tmp_file, mode)
    local f = io.open(tmp_file, "r")
    if not f then
        set_status("Error: Whisper produced no output. Check VLC logs.")
        return
    end

    local srt_path  = nil
    local seg_count = 0

    for line in f:lines() do
        local d = parse_json(line)
        if d then
            if d.type == "error" then
                set_status("Error: " .. (d.msg or "unknown"))
                f:close()
                pcall(function() os.remove(tmp_file) end)
                return
            elseif d.type == "sub" then
                seg_count = seg_count + 1
                if mode == "realtime" then
                    local dur = 3000000
                    if d.start and d["end"] then
                        dur = math.max((d["end"] - d.start) * 1000000, 1500000)
                    end
                    osd_channel = osd_channel or register_osd()
                    show_osd(d.text, dur)
                end
            elseif d.type == "done" then
                srt_path  = d.srt_path
                seg_count = d.segments or seg_count
            end
        end
    end
    f:close()
    pcall(function() os.remove(tmp_file) end)

    if not srt_path then
        set_status("Error: transcription failed. Check VLC logs for details.")
        return
    end

    if mode == "srt" then
        load_subtitle(srt_path)
        set_status("Done! " .. seg_count .. " segments. Subtitles loaded.")
    else
        set_status("Done! " .. seg_count .. " segments. SRT: " .. srt_path)
    end
end

----------------------------------------------------------------
-- Helpers
----------------------------------------------------------------

function load_subtitle(srt_path)
    local f = io.open(srt_path, "r")
    if not f then return end
    f:close()
    if add_subtitle_track(srt_path) then
        vlc.msg.info("[AI Subs] Loaded: " .. srt_path)
    else
        vlc.msg.warn("[AI Subs] Auto-load failed. Add manually: " .. srt_path)
    end
end

function set_status(text)
    if status_label then status_label:set_text(text) end
    if dlg then dlg:update() end
end

function parse_json(str)
    if not str then return nil end
    local j = string.match(str, "%b{}")
    if not j then return nil end
    local r = {}
    for k, v in string.gmatch(j, '"([^"]+)"%s*:%s*"(.-)"') do
        v = string.gsub(v, "\\n", "\n")
        v = string.gsub(v, "\\t", "\t")
        v = string.gsub(v, '\\"', '"')
        v = string.gsub(v, "\\\\", "\\")
        r[k] = v
    end
    for k, v in string.gmatch(j, '"([^"]+)"%s*:%s*([%d%.%-]+)') do
        if not r[k] then r[k] = tonumber(v) end
    end
    return r
end
